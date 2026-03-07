import logging
import time
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.config import get_settings
from app.core.exceptions import RecordNotFoundError
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.models.face_record import FaceRecord
from app.schemas.records import RecordDeleteResponse, RecordResponse
from app.services.analytics_service import log_event
from app.services.image_service import delete_image

_MIME_TYPES = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/records/{record_id}", response_model=RecordResponse)
async def get_record(
    request: Request,
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> RecordResponse:
    """Retrieve a specific face record by ID."""
    start_time = time.time()
    result = await db.execute(
        select(FaceRecord).where(FaceRecord.id == record_id)
    )
    record = result.scalar_one_or_none()

    if record is None:
        raise RecordNotFoundError(f"Record {record_id} not found")

    duration_ms = int((time.time() - start_time) * 1000)
    log_event(
        request,
        event_type="record_get",
        status="success",
        api_key=_api_key,
        record_id=record_id,
        duration_ms=duration_ms,
    )

    return RecordResponse(
        id=record.id,
        name=record.name,
        external_id=record.external_id,
        metadata=record.metadata_,
        image_path=record.image_path,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/records/{record_id}/image")
async def get_record_image(
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> Response:
    """Serve the face image for a specific record."""
    result = await db.execute(
        select(FaceRecord).where(FaceRecord.id == record_id)
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise RecordNotFoundError(f"Record {record_id} not found")

    settings = get_settings()
    image_path = Path(settings.IMAGE_STORAGE_PATH) / record.image_path
    if not image_path.exists():
        raise RecordNotFoundError(f"Image file not found for record {record_id}")

    suffix = image_path.suffix.lstrip(".")
    content_type = _MIME_TYPES.get(suffix, "application/octet-stream")

    return Response(
        content=image_path.read_bytes(),
        media_type=content_type,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete("/records/{record_id}", response_model=RecordDeleteResponse)
async def delete_record(
    request: Request,
    record_id: UUID,
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> RecordDeleteResponse:
    """Delete a face record and its associated image."""
    start_time = time.time()
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

    duration_ms = int((time.time() - start_time) * 1000)
    log_event(
        request,
        event_type="record_delete",
        status="success",
        api_key=_api_key,
        record_id=record_id,
        duration_ms=duration_ms,
    )

    return RecordDeleteResponse(id=record_id, deleted=True)
