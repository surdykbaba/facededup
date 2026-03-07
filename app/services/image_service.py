import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiofiles

from app.config import get_settings
from app.core.exceptions import ImageTooLargeError, InvalidImageError

logger = logging.getLogger(__name__)

# Magic bytes for supported image formats
IMAGE_SIGNATURES = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG": "png",
    b"RIFF": "webp",  # WebP starts with RIFF
}


def validate_image(image_bytes: bytes, max_size_mb: int | None = None) -> str:
    """Validate image bytes and return detected format.

    Raises:
        InvalidImageError: Not a recognized image format.
        ImageTooLargeError: Exceeds size limit.
    """
    if max_size_mb is None:
        max_size_mb = get_settings().MAX_IMAGE_SIZE_MB

    size_mb = len(image_bytes) / (1024 * 1024)
    if size_mb > max_size_mb:
        raise ImageTooLargeError(f"Image is {size_mb:.1f}MB, max is {max_size_mb}MB")

    if len(image_bytes) < 4:
        raise InvalidImageError("Image data too small")

    for signature, fmt in IMAGE_SIGNATURES.items():
        if image_bytes[: len(signature)] == signature:
            return fmt

    raise InvalidImageError("Unsupported image format; use JPEG, PNG, or WebP")


async def save_image(image_bytes: bytes, record_id: uuid.UUID) -> str:
    """Save image bytes to disk, return relative path."""
    settings = get_settings()
    fmt = validate_image(image_bytes)

    # Organize in subdirectories by first 2 chars of UUID
    sub_dir = str(record_id)[:2]
    dir_path = Path(settings.IMAGE_STORAGE_PATH) / sub_dir
    dir_path.mkdir(parents=True, exist_ok=True)

    filename = f"{record_id}.{fmt}"
    file_path = dir_path / filename

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(image_bytes)

    relative_path = f"{sub_dir}/{filename}"
    logger.info("Saved image: %s (%d bytes)", relative_path, len(image_bytes))
    return relative_path


async def delete_image(image_path: str) -> None:
    """Delete an image file from disk."""
    settings = get_settings()
    full_path = Path(settings.IMAGE_STORAGE_PATH) / image_path
    if full_path.exists():
        os.remove(full_path)
        logger.info("Deleted image: %s", image_path)


def _detect_format(image_bytes: bytes) -> str:
    """Detect image format from magic bytes (defaults to jpeg)."""
    for signature, fmt in IMAGE_SIGNATURES.items():
        if image_bytes[: len(signature)] == signature:
            return fmt
    return "jpeg"


async def save_spoof_sample(
    image_bytes_list: list[bytes],
    liveness_info: dict,
    endpoint: str,
) -> str | None:
    """Save failed spoof images + metadata for future model training.

    Args:
        image_bytes_list: One or more image byte arrays (single frame or multi-frame).
        liveness_info: Full liveness check results dict.
        endpoint: Which API endpoint detected the spoof (e.g. "/enroll").

    Returns:
        The sample ID if saved, or None if storage is disabled.
    """
    settings = get_settings()
    if not settings.SPOOF_SAMPLE_STORAGE_ENABLED:
        return None

    try:
        sample_id = str(uuid.uuid4())[:8]
        date_dir = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        dir_path = Path(settings.SPOOF_SAMPLE_STORAGE_PATH) / date_dir
        dir_path.mkdir(parents=True, exist_ok=True)

        # Save image(s)
        saved_files = []
        for i, img_bytes in enumerate(image_bytes_list):
            fmt = _detect_format(img_bytes)
            if len(image_bytes_list) == 1:
                filename = f"{sample_id}.{fmt}"
            else:
                filename = f"{sample_id}_frame{i}.{fmt}"
            async with aiofiles.open(dir_path / filename, "wb") as f:
                await f.write(img_bytes)
            saved_files.append(filename)

        # Save metadata
        metadata = {
            "sample_id": sample_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "endpoint": endpoint,
            "frame_count": len(image_bytes_list),
            "files": saved_files,
            "liveness_info": liveness_info,
        }
        async with aiofiles.open(dir_path / f"{sample_id}.json", "w") as f:
            await f.write(json.dumps(metadata, indent=2, default=str))

        logger.info(
            "Saved spoof sample %s (%d frames) from %s to %s",
            sample_id, len(image_bytes_list), endpoint, date_dir,
        )
        return sample_id

    except Exception:
        # Never let spoof storage failure break the API flow
        logger.exception("Failed to save spoof sample (non-fatal)")
        return None
