import logging
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from insightface.app import FaceAnalysis

from app.api.v1.router import v1_router
from app.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.exceptions import FaceDeduplicationError, face_error_handler
from app.core.logging import setup_logging

logger = logging.getLogger(__name__)


def _detect_providers() -> list[str]:
    """Auto-detect available ONNX execution providers. Prefer GPU if available."""
    try:
        import onnxruntime as ort

        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            logger.info("CUDA GPU detected, using GPU acceleration")
            return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    except Exception:
        pass
    return ["CPUExecutionProvider"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.LOG_LEVEL)

    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # 1. Load InsightFace model (auto-detect GPU)
    providers = _detect_providers()
    logger.info("Loading face model: %s (providers: %s)", settings.FACE_MODEL_NAME, providers)
    face_analyzer = FaceAnalysis(
        name=settings.FACE_MODEL_NAME,
        providers=providers,
    )
    ctx_id = 0 if "CUDAExecutionProvider" in providers else -1
    face_analyzer.prepare(ctx_id=ctx_id, det_size=settings.det_size_tuple)
    app.state.face_analyzer = face_analyzer
    app.state.gpu_enabled = "CUDAExecutionProvider" in providers
    logger.info("Face model loaded successfully (GPU: %s)", app.state.gpu_enabled)

    # 2. Initialize async DB engine
    engine = create_db_engine()
    app.state.db_engine = engine
    app.state.async_session = create_session_factory(engine)
    logger.info("Database engine initialized")

    # 3. Initialize Redis
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    logger.info("Redis connection initialized")

    yield

    # Shutdown
    logger.info("Shutting down...")
    await app.state.db_engine.dispose()
    await app.state.redis.close()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Face Deduplication API - detect and match duplicate faces across a database",
        lifespan=lifespan,
        docs_url="/docs" if settings.DEBUG else None,
        redoc_url="/redoc" if settings.DEBUG else None,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Exception handlers
    app.add_exception_handler(FaceDeduplicationError, face_error_handler)

    # Routes
    app.include_router(v1_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
