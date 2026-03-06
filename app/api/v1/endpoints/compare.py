import asyncio
import logging

import numpy as np
from fastapi import APIRouter, Depends, File, Query, UploadFile
from insightface.app import FaceAnalysis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_anti_spoof, get_face_analyzer
from app.config import get_settings
from app.core.exceptions import LivenessCheckFailedError
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.compare import CompareResponse
from app.services.face_service import FaceService
from app.services.image_service import validate_image
from app.services.liveness_service import LivenessService

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
    skip_liveness: bool = Query(
        default=False,
        description="Skip liveness check (admin override)",
    ),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    anti_spoof=Depends(get_anti_spoof),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> CompareResponse:
    """Compare two face images directly and return similarity score.

    Runs liveness/anti-spoof checks on both images before comparing.
    Rejects cartoons, printed photos, and non-face images.

    No database lookup — just a 1:1 face comparison.
    """
    settings = get_settings()
    if threshold is None:
        threshold = settings.SIMILARITY_THRESHOLD

    bytes_a = await image_a.read()
    bytes_b = await image_b.read()
    validate_image(bytes_a)
    validate_image(bytes_b)

    face_svc = FaceService(face_analyzer)
    loop = asyncio.get_event_loop()

    # Detect faces in both images
    img_a, face_a, crop_a = await loop.run_in_executor(
        None, face_svc.detect_face, bytes_a
    )
    img_b, face_b, crop_b = await loop.run_in_executor(
        None, face_svc.detect_face, bytes_b
    )

    # Liveness gate on both images — reject cartoons and non-real faces
    if settings.LIVENESS_COMPARE_REQUIRED and not skip_liveness:
        liveness_svc = LivenessService(face_analyzer, anti_spoof=anti_spoof)

        result_a = liveness_svc.check_liveness_from_face(img_a, face_a, crop_a)
        if not result_a["is_live"]:
            raise LivenessCheckFailedError(
                f"Image A failed liveness check "
                f"(score: {result_a['liveness_score']:.2f}, "
                f"passed {result_a['checks_passed']}/{result_a['checks_total']})",
                liveness_info=result_a,
            )

        result_b = liveness_svc.check_liveness_from_face(img_b, face_b, crop_b)
        if not result_b["is_live"]:
            raise LivenessCheckFailedError(
                f"Image B failed liveness check "
                f"(score: {result_b['liveness_score']:.2f}, "
                f"passed {result_b['checks_passed']}/{result_b['checks_total']})",
                liveness_info=result_b,
            )

    # Extract embeddings and compute similarity
    embedding_a = face_a.normed_embedding
    embedding_b = face_b.normed_embedding
    info_a = FaceService.extract_face_info(face_a)
    info_b = FaceService.extract_face_info(face_b)

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
