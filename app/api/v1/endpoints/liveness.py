import asyncio
import logging

from fastapi import APIRouter, Depends, File, UploadFile
from insightface.app import FaceAnalysis

from app.api.deps import get_anti_spoof, get_face_analyzer
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
    anti_spoof=Depends(get_anti_spoof),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> LivenessResponse:
    """Passive liveness detection with anti-spoof analysis.

    Runs ML anti-spoof model (Silent-Face ensemble) plus heuristic checks:
    - ML anti-spoof: CNN classifies face as Real or Fake
    - 9 mandatory heuristic checks (all must pass)
    - 4 optional heuristic checks (tolerance configurable)

    Catches: cartoons, printed photo attacks, screen replay attacks.
    """
    image_bytes = await image.read()
    validate_image(image_bytes)

    liveness_svc = LivenessService(face_analyzer, anti_spoof=anti_spoof)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, liveness_svc.check_liveness, image_bytes
    )

    return LivenessResponse(**result)
