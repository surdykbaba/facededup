import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.deduplicate import DeduplicateResponse
from app.services.dedup_service import DedupService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/deduplicate", response_model=DeduplicateResponse)
async def deduplicate(
    threshold: float = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for duplicate detection",
    ),
    batch_size: int = Query(default=100, ge=10, le=1000, description="Batch size"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> DeduplicateResponse:
    """Run a full deduplication pass on all enrolled records.

    Scans every record and finds pairs exceeding the similarity threshold.
    This operation can be slow for large datasets.
    """
    if threshold is None:
        threshold = get_settings().SIMILARITY_THRESHOLD

    logger.info("Starting deduplication pass: threshold=%.2f batch_size=%d", threshold, batch_size)

    dedup_svc = DedupService()
    result = await dedup_svc.find_all_duplicates(
        db, threshold=threshold, batch_size=batch_size
    )

    logger.info(
        "Deduplication complete: %d records, %d duplicate pairs found",
        result["total_records"],
        result["total_duplicates"],
    )

    return DeduplicateResponse(**result)
