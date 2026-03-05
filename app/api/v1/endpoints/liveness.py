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
    """Passive liveness detection on a single face image.

    Analyzes image quality, texture, color, and face geometry to determine
    if the face is from a live person or a spoof (photo, screen, mask).

    Checks performed:
    - Detection confidence
    - Image sharpness (blur detection)
    - Texture analysis (LBP variance)
    - Color distribution
    - Face-to-image size ratio
    - Glare/reflection detection

    Must pass at least 5 of 6 checks to be considered live.
    """
    image_bytes = await image.read()
    validate_image(image_bytes)

    liveness_svc = LivenessService(face_analyzer)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, liveness_svc.check_liveness, image_bytes
    )

    return LivenessResponse(**result)
