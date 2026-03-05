import logging

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.config import get_settings
from app.schemas.common import HealthResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    settings = get_settings()

    # Check database
    db_status = "healthy"
    try:
        async with request.app.state.async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {e}"
        logger.error("Database health check failed: %s", e)

    # Check Redis
    redis_status = "healthy"
    try:
        await request.app.state.redis.ping()
    except Exception as e:
        redis_status = f"unhealthy: {e}"
        logger.error("Redis health check failed: %s", e)

    # Check face model
    model_status = "loaded" if hasattr(request.app.state, "face_analyzer") else "not loaded"
    gpu_enabled = getattr(request.app.state, "gpu_enabled", False)

    overall = "healthy" if db_status == "healthy" and redis_status == "healthy" and model_status == "loaded" else "degraded"

    return HealthResponse(
        status=overall,
        database=db_status,
        redis=redis_status,
        face_model=model_status,
        gpu_enabled=gpu_enabled,
        version=settings.APP_VERSION,
    )
