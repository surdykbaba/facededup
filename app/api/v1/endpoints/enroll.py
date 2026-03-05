import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from insightface.app import FaceAnalysis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_face_analyzer
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.models.face_record import FaceRecord
from app.schemas.enroll import EnrollResponse
from app.services.face_service import FaceService
from app.services.image_service import save_image, validate_image

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/enroll", response_model=EnrollResponse, status_code=201)
async def enroll_face(
    image: UploadFile = File(..., description="Face image (JPEG/PNG/WebP)"),
    name: str | None = Form(None, description="Person name"),
    external_id: str | None = Form(None, description="External reference ID"),
    metadata: str | None = Form(None, description="JSON metadata string"),
    db: AsyncSession = Depends(get_db),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> EnrollResponse:
    """Enroll a new face record.

    Accepts a face image with optional metadata. Detects the face,
    extracts a 512-dim embedding, and stores the record.
    """
    image_bytes = await image.read()
    validate_image(image_bytes)

    # Run CPU-bound face detection in thread pool
    face_svc = FaceService(face_analyzer)
    loop = asyncio.get_event_loop()
    embedding, face_info = await loop.run_in_executor(
        None, face_svc.detect_and_embed, image_bytes
    )

    record_id = uuid.uuid4()

    # Save image to disk
    image_path = await save_image(image_bytes, record_id)

    # Parse metadata JSON
    parsed_metadata = {}
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            parsed_metadata = {"raw": metadata}

    # Create DB record
    record = FaceRecord(
        id=record_id,
        name=name,
        external_id=external_id,
        metadata_=parsed_metadata,
        embedding=embedding.tolist(),
        image_path=image_path,
    )
    db.add(record)
    await db.flush()

    logger.info("Enrolled face record: id=%s name=%s", record.id, record.name)

    return EnrollResponse(
        id=record.id,
        name=record.name,
        external_id=record.external_id,
        face_info=face_info,
        created_at=record.created_at,
    )
