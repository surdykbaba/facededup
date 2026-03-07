import base64
import json
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from insightface.app import FaceAnalysis

from app.api.v1.router import v1_router
from app.config import get_settings
from app.core.database import create_db_engine, create_session_factory
from app.core.exceptions import FaceDeduplicationError, face_error_handler
from app.core.logging import setup_logging
from app.services.anti_spoof_service import AntiSpoofService

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


def _check_basic_auth(request: Request, password: str, realm: str) -> Response | None:
    """Verify HTTP Basic Auth. Returns an error Response or None if auth passes."""
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Basic "):
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{realm}"'},
            content="Authentication required",
        )
    try:
        decoded = base64.b64decode(auth[6:]).decode("utf-8")
        _, provided_pw = decoded.split(":", 1)
    except Exception:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{realm}"'},
            content="Invalid credentials",
        )
    if not secrets.compare_digest(provided_pw, password):
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{realm}"'},
            content="Invalid password",
        )
    return None


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

    # 1b. Load Silent-Face-Anti-Spoofing models
    logger.info("Loading anti-spoofing models...")
    try:
        anti_spoof = AntiSpoofService(providers=providers)
        app.state.anti_spoof = anti_spoof
        logger.info("Anti-spoofing models loaded (2-model ensemble)")
    except FileNotFoundError as e:
        logger.warning("Anti-spoofing models not found: %s — running without ML anti-spoof", e)
        app.state.anti_spoof = None

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

    # Documentation page (password-protected via HTTP Basic Auth)
    from app.docs_page import get_docs_html

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def docs_page(request: Request):
        docs_pw = settings.DOCS_PASSWORD
        if docs_pw:
            auth_error = _check_basic_auth(request, docs_pw, "FaceDedup Docs")
            if auth_error:
                return auth_error
        return get_docs_html()

    # Dashboard page (password-protected via HTTP Basic Auth)
    from app.dashboard_page import get_dashboard_html

    @app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard_page(request: Request):
        docs_pw = settings.DOCS_PASSWORD
        if docs_pw:
            auth_error = _check_basic_auth(request, docs_pw, "FaceDedup Dashboard")
            if auth_error:
                return auth_error
        return get_dashboard_html()

    @app.get("/api/v1/postman", include_in_schema=False)
    async def postman_collection():
        """Serve the Postman collection JSON for download."""
        collection_path = Path(__file__).parent.parent / "FaceDedup_API.postman_collection.json"
        if not collection_path.exists():
            return Response(status_code=404, content="Collection not found")
        data = json.loads(collection_path.read_text())
        return JSONResponse(
            content=data,
            headers={
                "Content-Disposition": "attachment; filename=FaceDedup_API.postman_collection.json"
            },
        )

    return app


app = create_app()
