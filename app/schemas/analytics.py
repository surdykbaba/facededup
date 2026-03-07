from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EventTypeSummary(BaseModel):
    event_type: str
    total: int
    success: int
    failed: int
    error: int
    avg_duration_ms: float | None


class AnalyticsSummary(BaseModel):
    period_start: datetime | None
    period_end: datetime | None
    total_events: int
    by_type: list[EventTypeSummary]


class EventListItem(BaseModel):
    id: int
    event_type: str
    status: str
    api_key_hash: str
    record_id: UUID | None
    external_id: str | None
    duration_ms: int | None
    error_detail: str | None
    metadata: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    events: list[EventListItem]
    total: int
    offset: int
    limit: int


class TimeseriesBucket(BaseModel):
    timestamp: datetime
    total: int
    success: int
    failed: int
    error: int
    avg_duration_ms: float | None


class TimeseriesResponse(BaseModel):
    interval: str
    period_start: datetime
    period_end: datetime
    buckets: list[TimeseriesBucket]
