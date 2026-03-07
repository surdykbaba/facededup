from uuid import UUID

from pydantic import BaseModel, Field


class DuplicateResult(BaseModel):
    record_id: UUID
    name: str | None
    external_id: str | None
    similarity: float = Field(ge=0.0, le=1.0)
    metadata: dict | None


class DeduplicateResponse(BaseModel):
    query_face_info: dict
    duplicates: list[DuplicateResult]
    threshold: float
    total_duplicates: int
