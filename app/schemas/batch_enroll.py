from uuid import UUID

from pydantic import BaseModel, Field


class BatchEmbeddingRecord(BaseModel):
    """A single record for batch embedding enrollment."""

    embedding: list[float] = Field(
        ..., min_length=512, max_length=512, description="512-dim face embedding"
    )
    name: str | None = None
    external_id: str | None = None
    metadata: dict | None = None
    image_path: str | None = Field(
        None, description="Pre-existing image path (optional)"
    )


class BatchEmbeddingEnrollRequest(BaseModel):
    """Request to batch-enroll pre-computed face embeddings."""

    records: list[BatchEmbeddingRecord] = Field(
        ..., min_length=1, max_length=1000, description="Up to 1000 records per request"
    )
    skip_dedup: bool = Field(
        True, description="Skip duplicate detection for speed (default: true)"
    )
    job_id: str | None = Field(
        None,
        description="Optional bulk job ID for progress tracking. "
        "Also accepted via X-Bulk-Job-Id header.",
    )


class BatchRecordResult(BaseModel):
    """Result for a single record in a batch operation."""

    index: int
    id: UUID | None = None
    status: str  # "success" or "error"
    error: str | None = None


class BatchEmbeddingEnrollResponse(BaseModel):
    """Response from batch embedding enrollment."""

    total_submitted: int
    total_success: int
    total_failed: int
    results: list[BatchRecordResult]


class BatchImageRecordResult(BaseModel):
    """Result for a single image in a batch image enrollment."""

    index: int
    id: UUID | None = None
    name: str | None = None
    status: str  # "success" or "error"
    error: str | None = None
    face_info: dict | None = None


class BatchImageEnrollResponse(BaseModel):
    """Response from batch image enrollment."""

    total_submitted: int
    total_success: int
    total_failed: int
    results: list[BatchImageRecordResult]


class BulkProgressResponse(BaseModel):
    """Progress of a bulk enrollment operation."""

    job_id: str
    batches_completed: int
    total_success: int
    total_failed: int
    last_updated: str | None = None
