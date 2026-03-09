import logging
import os
import platform
import time
from datetime import datetime, timezone

import httpx
import psutil
from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.core.security import verify_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/admin/system-health")
async def system_health(
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Get detailed system health: CPU, memory, disk, load, processes."""

    # --- CPU ---
    cpu_percent_total = psutil.cpu_percent(interval=0.5)
    cpu_percent_per_core = psutil.cpu_percent(interval=0, percpu=True)
    cpu_freq = psutil.cpu_freq()
    cpu_count_physical = psutil.cpu_count(logical=False) or 0
    cpu_count_logical = psutil.cpu_count(logical=True) or 0

    cpu_info = {
        "physical_cores": cpu_count_physical,
        "logical_cores": cpu_count_logical,
        "total_percent": cpu_percent_total,
        "per_core_percent": cpu_percent_per_core,
        "frequency_mhz": round(cpu_freq.current, 0) if cpu_freq else None,
        "frequency_max_mhz": round(cpu_freq.max, 0) if cpu_freq and cpu_freq.max else None,
    }

    # --- Memory ---
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    memory_info = {
        "total_bytes": mem.total,
        "available_bytes": mem.available,
        "used_bytes": mem.used,
        "percent": mem.percent,
        "total_gb": round(mem.total / (1024**3), 1),
        "available_gb": round(mem.available / (1024**3), 1),
        "used_gb": round(mem.used / (1024**3), 1),
        "swap_total_gb": round(swap.total / (1024**3), 1),
        "swap_used_gb": round(swap.used / (1024**3), 1),
        "swap_percent": swap.percent,
    }

    # --- Disk ---
    disk = psutil.disk_usage("/")
    disk_io = psutil.disk_io_counters()

    disk_info = {
        "total_bytes": disk.total,
        "used_bytes": disk.used,
        "free_bytes": disk.free,
        "percent": disk.percent,
        "total_gb": round(disk.total / (1024**3), 1),
        "used_gb": round(disk.used / (1024**3), 1),
        "free_gb": round(disk.free / (1024**3), 1),
        "io_read_gb": round(disk_io.read_bytes / (1024**3), 1) if disk_io else None,
        "io_write_gb": round(disk_io.write_bytes / (1024**3), 1) if disk_io else None,
    }

    # --- Load Average ---
    load_1, load_5, load_15 = os.getloadavg()

    # --- Network ---
    net_io = psutil.net_io_counters()
    network_info = {
        "bytes_sent_gb": round(net_io.bytes_sent / (1024**3), 2),
        "bytes_recv_gb": round(net_io.bytes_recv / (1024**3), 2),
        "packets_sent": net_io.packets_sent,
        "packets_recv": net_io.packets_recv,
        "errors_in": net_io.errin,
        "errors_out": net_io.errout,
    }

    # --- Process Info ---
    gunicorn_workers = 0
    total_processes = 0
    try:
        for proc in psutil.process_iter(["name", "cmdline"]):
            total_processes += 1
            try:
                cmdline = proc.info.get("cmdline") or []
                cmdline_str = " ".join(cmdline)
                if "gunicorn" in cmdline_str and "worker" in cmdline_str:
                    gunicorn_workers += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except Exception:
        pass

    # --- System Info ---
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = int(time.time() - psutil.boot_time())
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime_str = f"{days}d {hours}h {minutes}m"

    return {
        "cpu": cpu_info,
        "memory": memory_info,
        "disk": disk_info,
        "load_average": {
            "load_1m": round(load_1, 2),
            "load_5m": round(load_5, 2),
            "load_15m": round(load_15, 2),
        },
        "network": network_info,
        "processes": {
            "gunicorn_workers": gunicorn_workers,
            "total": total_processes,
        },
        "system": {
            "hostname": platform.node(),
            "os": f"{platform.system()} {platform.release()}",
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "boot_time": boot_time.isoformat(),
            "uptime": uptime_str,
            "uptime_seconds": uptime_seconds,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/admin/cluster-health")
async def cluster_health(
    request: Request,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Get health status of all servers in the cluster.

    Returns the local server's health plus health from configured worker nodes.
    Worker URLs are configured via the WORKER_URLS environment variable.
    """
    settings = get_settings()
    api_key = request.headers.get("X-API-Key", "")
    servers = []

    # Local server health
    try:
        local_health = await _get_local_health(request)
        local_health["server_name"] = platform.node()
        local_health["server_url"] = "local"
        local_health["server_role"] = "primary"
        servers.append(local_health)
    except Exception as e:
        logger.error("Failed to get local health: %s", e)
        servers.append({
            "server_name": platform.node(),
            "server_url": "local",
            "server_role": "primary",
            "status": "error",
            "error": str(e),
        })

    # Worker server health (fetch in parallel)
    worker_urls = settings.worker_url_list
    if worker_urls:
        async with httpx.AsyncClient(timeout=5.0) as client:
            for url in worker_urls:
                try:
                    resp = await client.get(
                        f"{url}/api/v1/health",
                        headers={"X-API-Key": api_key},
                    )
                    data = resp.json()
                    # Also get system info for hostname
                    sys_resp = await client.get(
                        f"{url}/api/v1/admin/system-health",
                        headers={"X-API-Key": api_key},
                    )
                    sys_data = sys_resp.json() if sys_resp.status_code == 200 else {}
                    hostname = sys_data.get("system", {}).get("hostname", url)
                    data["server_name"] = hostname
                    data["server_url"] = url
                    data["server_role"] = "worker"
                    data["system"] = sys_data.get("system")
                    data["cpu"] = sys_data.get("cpu")
                    data["memory"] = sys_data.get("memory")
                    data["load_average"] = sys_data.get("load_average")
                    data["processes"] = sys_data.get("processes")
                    # Full system-health for System Health page rendering
                    if sys_data:
                        data["system_health"] = sys_data
                    servers.append(data)
                except Exception as e:
                    logger.error("Failed to fetch health from %s: %s", url, e)
                    servers.append({
                        "server_name": url,
                        "server_url": url,
                        "server_role": "worker",
                        "status": "unreachable",
                        "error": str(e),
                    })

    return {
        "total_servers": len(servers),
        "healthy_count": sum(
            1 for s in servers if s.get("status") == "healthy"
        ),
        "servers": servers,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _get_local_health(request: Request) -> dict:
    """Get local server health data (same as /health endpoint)."""
    from sqlalchemy import text

    settings = get_settings()
    result = {}

    # Database
    db_status = "healthy"
    try:
        async with request.app.state.async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {e}"

    # Redis
    redis_status = "healthy"
    try:
        await request.app.state.redis.ping()
    except Exception as e:
        redis_status = f"unhealthy: {e}"

    # Face model
    model_status = "loaded" if hasattr(request.app.state, "face_analyzer") else "not loaded"
    gpu_enabled = getattr(request.app.state, "gpu_enabled", False)
    anti_spoof_loaded = getattr(request.app.state, "anti_spoof", None) is not None

    overall = "healthy" if db_status == "healthy" and redis_status == "healthy" and model_status == "loaded" else "degraded"

    return {
        "status": overall,
        "database": db_status,
        "redis": redis_status,
        "face_model": model_status,
        "gpu_enabled": gpu_enabled,
        "anti_spoof_loaded": anti_spoof_loaded,
        "version": settings.APP_VERSION,
    }
