import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import RecordNotFoundError
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.models.face_record import FaceRecord
from app.schemas.records import RecordDeleteResponse, RecordResponse
from app.services.image_service import delete_image

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/records/{record_id}", response_model=RecordResponse)
async def get_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> RecordResponse:
    """Retrieve a specific face record by ID."""
    result = await db.execute(
        select(FaceRecord).where(FaceRecord.id == record_id)
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise RecordNotFoundError(f"Record {record_id} not found")

    return RecordResponse(
        id=record.id,
        name=record.name,
        external_id=record.external_id,
        metadata=record.metadata_,
        image_path=record.image_path,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.delete("/records/{record_id}", response_model=RecordDeleteResponse)
async def delete_record(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> RecordDeleteResponse:
    """Delete a face record and its associated image."""
    result = await db.execute(
        select(FaceRecord).where(FaceRecord.id == record_id)
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise RecordNotFoundError(f"Record {record_id} not found")

    # Delete associated image
    await delete_image(record.image_path)

    await db.delete(record)

    logger.info("Deleted face record: id=%s", record_id)

    return RecordDeleteResponse(id=record_id, deleted=True)
