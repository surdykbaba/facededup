import asyncio
import logging

import numpy as np
from fastapi import APIRouter, Depends, File, Query, UploadFile
from insightface.app import FaceAnalysis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_face_analyzer
from app.config import get_settings
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.compare import CompareResponse
from app.services.face_service import FaceService
from app.services.image_service import validate_image

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/compare", response_model=CompareResponse)
async def compare_faces(
    image_a: UploadFile = File(..., description="First face image"),
    image_b: UploadFile = File(..., description="Second face image"),
    threshold: float = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Similarity threshold to determine a match",
    ),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> CompareResponse:
    """Compare two face images directly and return similarity score.

    No database lookup — just a 1:1 face comparison.
    """
    if threshold is None:
        threshold = get_settings().SIMILARITY_THRESHOLD

    bytes_a = await image_a.read()
    bytes_b = await image_b.read()
    validate_image(bytes_a)
    validate_image(bytes_b)

    face_svc = FaceService(face_analyzer)
    loop = asyncio.get_event_loop()

    # Run both detections in parallel threads
    embedding_a, info_a = await loop.run_in_executor(
        None, face_svc.detect_and_embed, bytes_a
    )
    embedding_b, info_b = await loop.run_in_executor(
        None, face_svc.detect_and_embed, bytes_b
    )

    # Cosine similarity (embeddings are already L2-normalized)
    similarity = float(np.dot(embedding_a, embedding_b))
    similarity = round(max(0.0, min(1.0, similarity)), 4)

    is_match = similarity >= threshold

    logger.info(
        "Face comparison: similarity=%.4f match=%s threshold=%.2f",
        similarity, is_match, threshold,
    )

    return CompareResponse(
        similarity=similarity,
        match=is_match,
        threshold=threshold,
        face_a_info=info_a,
        face_b_info=info_b,
    )
