import logging
import os
import platform
import time
from datetime import datetime, timezone

import psutil
from fastapi import APIRouter, Depends

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
