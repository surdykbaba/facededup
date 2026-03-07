import asyncio
import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from insightface.app import FaceAnalysis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_face_analyzer, get_redis
from app.config import get_settings
from app.core.rate_limiter import batch_rate_limit_dependency
from app.core.security import verify_api_key
from app.schemas.batch_enroll import (
    BatchEmbeddingEnrollRequest,
    BatchEmbeddingEnrollResponse,
    BatchImageEnrollResponse,
    BatchImageRecordResult,
    BatchRecordResult,
    BulkProgressResponse,
)
from app.services.analytics_service import log_event
from app.services.bulk_insert_service import (
    BulkInsertService,
    get_bulk_progress,
    update_bulk_progress,
)
from app.services.face_service import FaceService
from app.services.image_service import validate_image

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/enroll/batch",
    response_model=BatchImageEnrollResponse,
    status_code=201,
)
async def batch_enroll_images(
    request: Request,
    images: list[UploadFile] = File(
        ..., description="Face images to enroll (up to 50)"
    ),
    names: str | None = Form(
        None, description="JSON array of names (one per image)"
    ),
    external_ids: str | None = Form(
        None, description="JSON array of external IDs (one per image)"
    ),
    metadata_list: str | None = Form(
        None, description="JSON array of metadata objects (one per image)"
    ),
    db: AsyncSession = Depends(get_db),
    face_analyzer: FaceAnalysis = Depends(get_face_analyzer),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(batch_rate_limit_dependency),
) -> BatchImageEnrollResponse:
    """Batch enroll up to 50 face images at once.

    Skips liveness checks (pre-verified batch).
    Runs face detection + embedding extraction on each image,
    then bulk inserts all records.
    """
    start_time = time.time()
    settings = get_settings()

    if len(images) > settings.BATCH_MAX_IMAGES:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"Maximum {settings.BATCH_MAX_IMAGES} images per batch request",
        )

    # Parse optional arrays
    name_list = json.loads(names) if names else [None] * len(images)
    ext_id_list = json.loads(external_ids) if external_ids else [None] * len(images)
    meta_list = json.loads(metadata_list) if metadata_list else [None] * len(images)

    face_svc = FaceService(face_analyzer)
    loop = asyncio.get_event_loop()
    results = []
    records_to_insert = []

    for i, img_file in enumerate(images):
        try:
            image_bytes = await img_file.read()
            validate_image(image_bytes)

            # Face detection in thread pool
            img, face, face_crop = await loop.run_in_executor(
                None, face_svc.detect_face, image_bytes
            )

            record_id = uuid.uuid4()
            embedding = face.normed_embedding
            face_info = FaceService.extract_face_info(face)

            records_to_insert.append(
                {
                    "id": record_id,
                    "name": name_list[i] if i < len(name_list) else None,
                    "external_id": ext_id_list[i] if i < len(ext_id_list) else None,
                    "metadata": meta_list[i] if i < len(meta_list) else {},
                    "embedding": embedding.tolist(),
                    "image_path": "",
                }
            )
            results.append(
                BatchImageRecordResult(
                    index=i,
                    id=record_id,
                    name=name_list[i] if i < len(name_list) else None,
                    status="success",
                    face_info=face_info,
                )
            )
        except Exception as e:
            results.append(
                BatchImageRecordResult(
                    index=i,
                    status="error",
                    error=str(e)[:500],
                )
            )

    # Bulk insert all successful records
    if records_to_insert:
        success_count, insert_errors = await BulkInsertService.bulk_insert_records(
            db, records_to_insert
        )
        # Map insert errors back to results
        for err in insert_errors:
            idx = err["index"]
            results[idx] = BatchImageRecordResult(
                index=idx, status="error", error=err["error"]
            )

    total_success = sum(1 for r in results if r.status == "success")
    total_failed = sum(1 for r in results if r.status == "error")

    duration_ms = int((time.time() - start_time) * 1000)
    log_event(
        request,
        event_type="batch_enroll",
        status="success" if total_failed == 0 else "partial",
        api_key=_api_key,
        duration_ms=duration_ms,
        metadata={
            "total_submitted": len(images),
            "total_success": total_success,
            "total_failed": total_failed,
        },
    )

    return BatchImageEnrollResponse(
        total_submitted=len(images),
        total_success=total_success,
        total_failed=total_failed,
        results=results,
    )


@router.post(
    "/enroll/batch-embeddings",
    response_model=BatchEmbeddingEnrollResponse,
    status_code=201,
)
async def batch_enroll_embeddings(
    request: Request,
    body: BatchEmbeddingEnrollRequest,
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
    _api_key: str = Depends(verify_api_key),
    _rate_limit: None = Depends(batch_rate_limit_dependency),
) -> BatchEmbeddingEnrollResponse:
    """Bulk enroll pre-computed embeddings. Designed for high-volume imports.

    Accepts up to 1000 records per request. Skips face detection and liveness.
    For 50M imports, call this endpoint in a loop with batches of 500-1000.

    Optionally pass a job_id (via body or X-Bulk-Job-Id header) for progress
    tracking — query progress via GET /enroll/batch-progress/{job_id}.
    """
    start_time = time.time()
    settings = get_settings()

    if len(body.records) > settings.BATCH_MAX_EMBEDDINGS:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=400,
            detail=f"Maximum {settings.BATCH_MAX_EMBEDDINGS} embeddings per request",
        )

    # Prepare records for bulk insert
    records_to_insert = []
    results = []
    for i, rec in enumerate(body.records):
        try:
            record_id = uuid.uuid4()
            records_to_insert.append(
                {
                    "id": record_id,
                    "name": rec.name,
                    "external_id": rec.external_id,
                    "metadata": rec.metadata or {},
                    "embedding": rec.embedding,
                    "image_path": rec.image_path or "",
                }
            )
            results.append(
                BatchRecordResult(index=i, id=record_id, status="success")
            )
        except Exception as e:
            results.append(
                BatchRecordResult(index=i, status="error", error=str(e)[:500])
            )

    # Bulk insert
    if records_to_insert:
        success_count, insert_errors = await BulkInsertService.bulk_insert_records(
            db, records_to_insert
        )
        for err in insert_errors:
            idx = err["index"]
            results[idx] = BatchRecordResult(
                index=idx, status="error", error=err["error"]
            )

    total_success = sum(1 for r in results if r.status == "success")
    total_failed = sum(1 for r in results if r.status == "error")

    # Update progress tracking if job_id provided
    job_id = body.job_id or request.headers.get("X-Bulk-Job-Id")
    if job_id:
        # Accumulate progress
        existing = await get_bulk_progress(redis, job_id)
        prev_success = existing["total_success"] if existing else 0
        prev_failed = existing["total_failed"] if existing else 0
        prev_batches = existing["batches_completed"] if existing else 0
        await update_bulk_progress(
            redis,
            job_id,
            batches_completed=prev_batches + 1,
            total_success=prev_success + total_success,
            total_failed=prev_failed + total_failed,
        )

    duration_ms = int((time.time() - start_time) * 1000)
    log_event(
        request,
        event_type="batch_enroll_embeddings",
        status="success" if total_failed == 0 else "partial",
        api_key=_api_key,
        duration_ms=duration_ms,
        metadata={
            "total_submitted": len(body.records),
            "total_success": total_success,
            "total_failed": total_failed,
            "job_id": job_id,
        },
    )

    return BatchEmbeddingEnrollResponse(
        total_submitted=len(body.records),
        total_success=total_success,
        total_failed=total_failed,
        results=results,
    )


@router.get(
    "/enroll/batch-progress/{job_id}",
    response_model=BulkProgressResponse,
)
async def batch_progress(
    job_id: str,
    redis: Redis = Depends(get_redis),
    _api_key: str = Depends(verify_api_key),
) -> BulkProgressResponse:
    """Check progress of a bulk enrollment operation.

    Returns the cumulative count of records processed across all batches
    for the given job_id. Progress data expires after 24 hours.
    """
    from fastapi import HTTPException

    progress = await get_bulk_progress(redis, job_id)
    if not progress:
        raise HTTPException(
            status_code=404,
            detail=f"No progress found for job_id: {job_id}. "
            "Either the job hasn't started or progress has expired (24h TTL).",
        )
    return BulkProgressResponse(**progress)
