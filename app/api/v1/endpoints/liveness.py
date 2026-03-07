import asyncio
import logging
import time

from fastapi import APIRouter, Depends, File, Request, UploadFile
from insightface.app import FaceAnalysis

from app.api.deps import get_anti_spoof, get_face_analyzer
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.liveness import LivenessResponse
from app.services.analytics_service import log_event
from app.services.image_service import save_spoof_sample, validate_image
from app.services.liveness_service import LivenessService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/liveness", response_model=LivenessResponse)
async def check_liveness(
    request: Request,
    image: UploadFile = File(..., description="Face image to check for liveness"),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    anti_spoof=Depends(get_anti_spoof),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> LivenessResponse:
    """Passive liveness detection with anti-spoof analysis.

    Runs 15 liveness checks:
    - 7 mandatory heuristic checks (all must pass)
    - 8 optional checks with tolerance of 3 (ML anti-spoof, noise, color
      correlation, sharpness, color distribution, face size, embedding
      norm, gradient smoothness)

    Catches: cartoons, printed photo attacks, screen replay attacks.
    Returns full check-by-check breakdown in the response.
    """
    start_time = time.time()
    image_bytes = await image.read()
    validate_image(image_bytes)

    liveness_svc = LivenessService(face_analyzer, anti_spoof=anti_spoof)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, liveness_svc.check_liveness, image_bytes
    )

    if not result.get("is_live", True):
        await save_spoof_sample([image_bytes], result, "/liveness")

    duration_ms = int((time.time() - start_time) * 1000)
    log_event(
        request,
        event_type="liveness",
        status="success" if result.get("is_live") else "failed",
        api_key=_api_key,
        duration_ms=duration_ms,
        metadata={"is_live": result.get("is_live"), "liveness_score": result.get("liveness_score")},
    )

    return LivenessResponse(**result)
