import asyncio
import logging

from fastapi import APIRouter, Depends, File, Query, UploadFile
from insightface.app import FaceAnalysis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_face_analyzer
from app.config import get_settings
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.match import MatchResponse
from app.services.face_service import FaceService
from app.services.image_service import validate_image
from app.services.match_service import MatchService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/match", response_model=MatchResponse)
async def match_face(
    image: UploadFile = File(..., description="Query face image"),
    threshold: float = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Minimum similarity threshold (0-1)",
    ),
    limit: int = Query(default=10, ge=1, le=100, description="Max results"),
    db: AsyncSession = Depends(get_db),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> MatchResponse:
    """Match a face image against enrolled records.

    Returns ranked list of matching records with similarity scores.
    """
    if threshold is None:
        threshold = get_settings().SIMILARITY_THRESHOLD

    image_bytes = await image.read()
    validate_image(image_bytes)

    face_svc = FaceService(face_analyzer)
    loop = asyncio.get_event_loop()
    embedding, face_info = await loop.run_in_executor(
        None, face_svc.detect_and_embed, image_bytes
    )

    match_svc = MatchService()
    matches = await match_svc.find_matches(
        db, embedding, threshold=threshold, limit=limit
    )

    logger.info(
        "Match query: %d results above threshold %.2f", len(matches), threshold
    )

    return MatchResponse(
        query_face_info=face_info,
        matches=matches,
        threshold=threshold,
        total_matches=len(matches),
    )
