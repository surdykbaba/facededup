import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, UploadFile
from insightface.app import FaceAnalysis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_anti_spoof, get_db, get_face_analyzer
from app.config import get_settings
from app.core.exceptions import InsufficientFramesError, LivenessCheckFailedError
from app.core.rate_limiter import rate_limit_dependency
from app.core.security import verify_api_key
from app.models.face_record import FaceRecord
from app.schemas.enroll import EnrollResponse
from app.services.face_service import FaceService
from app.services.image_service import save_image, validate_image
from app.services.liveness_service import LivenessService
from app.services.match_service import MatchService
from app.services.multi_frame_liveness_service import MultiFrameLivenessService

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/enroll", response_model=EnrollResponse, status_code=201)
async def enroll_face(
    image: UploadFile = File(..., description="Face image (JPEG/PNG/WebP)"),
    frames: list[UploadFile] | None = File(
        None,
        description="Additional frames for multi-frame liveness (2-4 more images)",
    ),
    name: str | None = Form(None, description="Person name"),
    external_id: str | None = Form(None, description="External reference ID"),
    metadata: str | None = Form(None, description="JSON metadata string"),
    skip_liveness: bool = Form(False, description="Skip liveness check (admin override)"),
    db: AsyncSession = Depends(get_db),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    anti_spoof=Depends(get_anti_spoof),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(rate_limit_dependency),
) -> EnrollResponse:
    """Enroll a new face record.

    Accepts a face image with optional metadata. Detects the face,
    runs liveness/anti-spoof checks, extracts a 512-dim embedding,
    and stores the record.

    For stronger anti-spoof protection, provide additional frames
    for multi-frame active liveness (3-5 total images including primary).
    """
    image_bytes = await image.read()
    validate_image(image_bytes)

    settings = get_settings()
    face_svc = FaceService(face_analyzer)
    loop = asyncio.get_event_loop()

    # Determine if multi-frame liveness should be used
    has_extra_frames = frames and len(frames) > 0
    use_multi_frame = has_extra_frames

    # Check if multi-frame is mandatory for enrollment
    if settings.MULTIFRAME_ENROLL_REQUIRED and not skip_liveness:
        if not has_extra_frames:
            raise InsufficientFramesError(
                f"Multi-frame liveness is required for enrollment. "
                f"Provide {settings.MULTIFRAME_MIN_FRAMES - 1} to "
                f"{settings.MULTIFRAME_MAX_FRAMES - 1} additional frames "
                f"(total {settings.MULTIFRAME_MIN_FRAMES}-{settings.MULTIFRAME_MAX_FRAMES} "
                f"including the primary image). Each frame must be a distinct "
                f"capture showing slight head movement or expression change."
            )

    liveness_info = None
    liveness_mode = None

    if use_multi_frame and not skip_liveness:
        # Multi-frame liveness path
        all_frames_bytes = [image_bytes]
        for f in frames:
            fb = await f.read()
            validate_image(fb)
            all_frames_bytes.append(fb)

        multi_svc = MultiFrameLivenessService(face_analyzer, anti_spoof=anti_spoof)
        liveness_info = await loop.run_in_executor(
            None, multi_svc.check_multi_frame_liveness, all_frames_bytes
        )
        liveness_mode = "multi_frame"

        if not liveness_info["is_live"]:
            raise LivenessCheckFailedError(
                f"Multi-frame liveness failed "
                f"(score: {liveness_info['liveness_score']:.2f}, "
                f"active checks: {liveness_info['active_checks']['checks_passed']}/"
                f"{liveness_info['active_checks']['checks_total']})",
                liveness_info=liveness_info,
            )

        # Get first frame's face data for embedding
        img, face, face_crop = multi_svc.get_primary_frame_data()
    else:
        # Single-frame path (existing behavior)
        img, face, face_crop = await loop.run_in_executor(
            None, face_svc.detect_face, image_bytes
        )

        if settings.LIVENESS_ENROLL_REQUIRED and not skip_liveness:
            liveness_svc = LivenessService(face_analyzer, anti_spoof=anti_spoof)
            liveness_info = liveness_svc.check_liveness_from_face(img, face, face_crop)
            liveness_mode = "single_frame"

            if not liveness_info["is_live"]:
                raise LivenessCheckFailedError(
                    f"Image failed liveness check "
                    f"(score: {liveness_info['liveness_score']:.2f}, "
                    f"passed {liveness_info['checks_passed']}/{liveness_info['checks_total']})",
                    liveness_info=liveness_info,
                )

    embedding = face.normed_embedding
    face_info = FaceService.extract_face_info(face)

    # Duplicate detection
    duplicate_info = None
    if settings.ENROLL_DEDUP_ENABLED:
        match_svc = MatchService()
        matches = await match_svc.find_matches(
            session=db,
            query_embedding=embedding,
            threshold=settings.SIMILARITY_THRESHOLD,
            limit=5,
        )
        if matches:
            duplicate_info = {
                "is_duplicate": True,
                "matches": matches,
            }

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
        liveness_info=liveness_info,
        liveness_mode=liveness_mode,
        duplicate_info=duplicate_info,
        created_at=record.created_at,
    )
