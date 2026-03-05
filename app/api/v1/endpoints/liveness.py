import asyncio
import logging

from fastapi import APIRouter, Depends, File, UploadFile
from insightface.app import FaceAnalysis

from app.api.deps import get_face_analyzer
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.liveness import LivenessResponse
from app.services.image_service import validate_image
from app.services.liveness_service import LivenessService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/liveness", response_model=LivenessResponse)
async def check_liveness(
    image: UploadFile = File(..., description="Face image to check for liveness"),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> LivenessResponse:
    """Passive liveness detection with anti-spoof analysis.

    Runs 11 checks in two tiers:
    - 5 mandatory checks (all must pass): detection confidence, landmark quality,
      skin tone validation, DCT frequency analysis, glare detection
    - 6 optional checks (allow 1 failure): sharpness, texture, color distribution,
      face size ratio, embedding quality, edge density

    Catches: cartoons, printed photo attacks, screen replay attacks.
    """
    image_bytes = await image.read()
    validate_image(image_bytes)

    liveness_svc = LivenessService(face_analyzer)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, liveness_svc.check_liveness, image_bytes
    )

    return LivenessResponse(**result)
