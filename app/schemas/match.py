from uuid import UUID

from pydantic import BaseModel, Field


class MatchResult(BaseModel):
    record_id: UUID
    name: str | None
    external_id: str | None
    similarity: float = Field(ge=0.0, le=1.0)
    metadata: dict | None


class MatchResponse(BaseModel):
    query_face_info: dict
    matches: list[MatchResult]
    threshold: float
    total_matches: int
