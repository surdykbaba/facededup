import asyncio
import logging

from fastapi import APIRouter, Depends, File, Query, UploadFile
from insightface.app import FaceAnalysis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_anti_spoof, get_db, get_face_analyzer
from app.config import get_settings
from app.core.exceptions import LivenessCheckFailedError
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.deduplicate import DeduplicateResponse
from app.services.face_service import FaceService
from app.services.image_service import save_spoof_sample, validate_image
from app.services.liveness_service import LivenessService
from app.services.match_service import MatchService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/deduplicate", response_model=DeduplicateResponse)
async def deduplicate(
    image: UploadFile = File(..., description="Face image to search for duplicates"),
    threshold: float = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for duplicate detection",
    ),
    limit: int = Query(default=50, ge=1, le=500, description="Max results to return"),
    skip_liveness: bool = Query(
        default=False,
        description="Skip liveness check (admin override)",
    ),
    db: AsyncSession = Depends(get_db),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    anti_spoof=Depends(get_anti_spoof),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> DeduplicateResponse:
    """Find duplicate faces in the database for a given image.

    Upload a face image and the system returns all enrolled records
    that look similar (above the similarity threshold).

    Runs liveness/anti-spoof checks on the query image before searching.
    """
    settings = get_settings()
    if threshold is None:
        threshold = settings.SIMILARITY_THRESHOLD

    image_bytes = await image.read()
    validate_image(image_bytes)

    face_svc = FaceService(face_analyzer)
    loop = asyncio.get_event_loop()

    # Single detection pass (shared between liveness + embedding)
    img, face, face_crop = await loop.run_in_executor(
        None, face_svc.detect_face, image_bytes
    )

    # Liveness gate
    liveness_info = None
    if settings.LIVENESS_MATCH_REQUIRED and not skip_liveness:
        liveness_svc = LivenessService(face_analyzer, anti_spoof=anti_spoof)
        liveness_info = liveness_svc.check_liveness_from_face(img, face, face_crop)

        if not liveness_info["is_live"]:
            await save_spoof_sample([image_bytes], liveness_info, "/deduplicate")
            raise LivenessCheckFailedError(
                f"Image failed liveness check "
                f"(score: {liveness_info['liveness_score']:.2f}, "
                f"passed {liveness_info['checks_passed']}/{liveness_info['checks_total']})",
                liveness_info=liveness_info,
            )

    embedding = face.normed_embedding
    face_info = FaceService.extract_face_info(face)

    match_svc = MatchService()
    duplicates = await match_svc.find_matches(
        db, embedding, threshold=threshold, limit=limit
    )

    logger.info(
        "Deduplicate query: %d similar faces found above threshold %.2f",
        len(duplicates),
        threshold,
    )

    return DeduplicateResponse(
        query_face_info=face_info,
        duplicates=duplicates,
        threshold=threshold,
        total_duplicates=len(duplicates),
    )
