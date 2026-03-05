from pydantic import BaseModel


class RecordSummary(BaseModel):
    id: str
    name: str | None
    external_id: str | None


class DuplicatePair(BaseModel):
    record_a: RecordSummary
    record_b: RecordSummary
    similarity: float


class DeduplicateResponse(BaseModel):
    total_records: int
    duplicate_pairs: list[DuplicatePair]
    total_duplicates: int
    threshold: float
