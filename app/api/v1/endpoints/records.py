import io
import logging
import time
from pathlib import Path
from uuid import UUID

import aiofiles
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from PIL import Image
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

_THUMB_MAX_PX = 300
_THUMB_QUALITY = 80

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
    thumb: int = Query(0, description="Set to 1 for a 300px thumbnail"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> Response:
    """Serve the face image for a specific record.

    Pass ?thumb=1 to get a small JPEG thumbnail (max 300px) instead of
    the full-resolution original. Thumbnails are cached on disk.
    """
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

    # --- Thumbnail mode ---
    if thumb:
        thumb_dir = Path(settings.IMAGE_STORAGE_PATH) / ".thumbs" / str(record_id)[:2]
        thumb_path = thumb_dir / f"{record_id}.jpg"

        # Serve cached thumbnail if it exists
        if thumb_path.exists():
            async with aiofiles.open(thumb_path, "rb") as f:
                data = await f.read()
            return Response(
                content=data,
                media_type="image/jpeg",
                headers={"Cache-Control": "private, max-age=86400"},
            )

        # Generate thumbnail
        async with aiofiles.open(image_path, "rb") as f:
            raw = await f.read()
        img = Image.open(io.BytesIO(raw))
        img.thumbnail((_THUMB_MAX_PX, _THUMB_MAX_PX), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=_THUMB_QUALITY)
        thumb_bytes = buf.getvalue()

        # Cache to disk (fire-and-forget)
        try:
            thumb_dir.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(thumb_path, "wb") as f:
                await f.write(thumb_bytes)
        except Exception:
            logger.debug("Could not cache thumbnail for %s", record_id)

        return Response(
            content=thumb_bytes,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, max-age=86400"},
        )

    # --- Full image mode (async read) ---
    async with aiofiles.open(image_path, "rb") as f:
        data = await f.read()
    suffix = image_path.suffix.lstrip(".")
    content_type = _MIME_TYPES.get(suffix, "application/octet-stream")

    return Response(
        content=data,
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
