import asyncio
import logging

from fastapi import APIRouter, Depends, File, UploadFile
from insightface.app import FaceAnalysis

from app.api.deps import get_face_analyzer
from app.config import get_settings
from app.core.exceptions import InsufficientFramesError
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.multi_frame_liveness import MultiFrameLivenessResponse
from app.services.image_service import validate_image
from app.services.multi_frame_liveness_service import MultiFrameLivenessService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/liveness/multi-frame", response_model=MultiFrameLivenessResponse)
async def check_multi_frame_liveness(
    frames: list[UploadFile] = File(
        ..., description="3-5 sequential face images for active liveness detection"
    ),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> MultiFrameLivenessResponse:
    """Multi-frame active liveness detection.

    Accepts 3-5 sequential face images and verifies:
    1. Each frame passes all 11 passive liveness checks
    2. Inter-frame motion analysis detects real movement:
       - Identity consistency (same person across all frames)
       - Landmark displacement (facial features move between frames)
       - Head pose variation (head angle changes)
       - Optical flow (pixel-level motion between frames)
       - Bounding box shift (natural micro-sway)

    A static image (cartoon, printed photo, screen replay) cannot produce
    genuine inter-frame motion and will be rejected.
    """
    settings = get_settings()

    if not settings.MULTIFRAME_LIVENESS_ENABLED:
        raise InsufficientFramesError("Multi-frame liveness is disabled")

    # Read and validate all frames
    frames_bytes = []
    for i, f in enumerate(frames):
        data = await f.read()
        validate_image(data)
        frames_bytes.append(data)

    if len(frames_bytes) < settings.MULTIFRAME_MIN_FRAMES:
        raise InsufficientFramesError(
            f"Need at least {settings.MULTIFRAME_MIN_FRAMES} frames, got {len(frames_bytes)}"
        )
    if len(frames_bytes) > settings.MULTIFRAME_MAX_FRAMES:
        raise InsufficientFramesError(
            f"Maximum {settings.MULTIFRAME_MAX_FRAMES} frames, got {len(frames_bytes)}"
        )

    svc = MultiFrameLivenessService(face_analyzer)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, svc.check_multi_frame_liveness, frames_bytes
    )

    return MultiFrameLivenessResponse(**result)
