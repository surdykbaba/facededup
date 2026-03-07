import asyncio
import logging
import time

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from insightface.app import FaceAnalysis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_anti_spoof, get_db, get_face_analyzer
from app.config import get_settings
from app.core.exceptions import LivenessCheckFailedError
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.match import MatchResponse
from app.services.analytics_service import log_event
from app.services.face_service import FaceService
from app.services.image_service import save_spoof_sample, validate_image
from app.services.liveness_service import LivenessService
from app.services.match_service import MatchService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/match", response_model=MatchResponse)
async def match_face(
    request: Request,
    image: UploadFile = File(..., description="Query face image"),
    threshold: float = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold (0-1)",
    ),
    limit: int = Query(default=10, ge=1, le=100, description="Max results"),
    skip_liveness: bool = Query(
        default=False,
        description="Skip liveness check (admin override)",
    ),
    db: AsyncSession = Depends(get_db),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    anti_spoof=Depends(get_anti_spoof),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> MatchResponse:
    """Match a face image against enrolled records.

    Runs liveness/anti-spoof checks on the query image before matching.
    Rejects cartoons, printed photos, and non-face images.

    Returns ranked list of matching records with similarity scores.
    """
    start_time = time.time()
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

    # Liveness gate — reject cartoons and non-real faces
    liveness_info = None
    if settings.LIVENESS_MATCH_REQUIRED and not skip_liveness:
        liveness_svc = LivenessService(face_analyzer, anti_spoof=anti_spoof)
        liveness_info = liveness_svc.check_liveness_from_face(img, face, face_crop)

        if not liveness_info["is_live"]:
            await save_spoof_sample([image_bytes], liveness_info, "/match")
            raise LivenessCheckFailedError(
                f"Query image failed liveness check "
                f"(score: {liveness_info['liveness_score']:.2f}, "
                f"passed {liveness_info['checks_passed']}/{liveness_info['checks_total']})",
                liveness_info=liveness_info,
            )

    embedding = face.normed_embedding
    face_info = FaceService.extract_face_info(face)

    match_svc = MatchService()
    matches = await match_svc.find_matches(
        db, embedding, threshold=threshold, limit=limit
    )

    logger.info(
        "Match query: %d results above threshold %.2f", len(matches), threshold
    )

    duration_ms = int((time.time() - start_time) * 1000)
    log_event(
        request,
        event_type="match",
        status="success",
        api_key=_api_key,
        duration_ms=duration_ms,
        metadata={"match_count": len(matches), "threshold": threshold},
    )

    return MatchResponse(
        query_face_info=face_info,
        matches=matches,
        threshold=threshold,
        total_matches=len(matches),
    )
