import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import verify_api_key
from app.models.api_event import ApiEvent
from app.schemas.analytics import (
    AnalyticsSummary,
    EventListItem,
    EventListResponse,
    EventTypeSummary,
    TimeseriesBucket,
    TimeseriesResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary(
    start: datetime | None = Query(None, description="Start of date range (ISO 8601)"),
    end: datetime | None = Query(None, description="End of date range (ISO 8601)"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> AnalyticsSummary:
    """Get summary analytics grouped by event type.

    Optionally filter by date range. Returns total counts, success/failure
    breakdown, and average duration per event type.
    """
    # Build base filter
    filters = []
    if start:
        filters.append(ApiEvent.created_at >= start)
    if end:
        filters.append(ApiEvent.created_at <= end)

    # Grouped summary query
    stmt = (
        select(
            ApiEvent.event_type,
            func.count().label("total"),
            func.count(case((ApiEvent.status == "success", 1))).label("success"),
            func.count(case((ApiEvent.status == "failed", 1))).label("failed"),
            func.count(case((ApiEvent.status == "error", 1))).label("error"),
            func.avg(ApiEvent.duration_ms).label("avg_duration_ms"),
        )
        .where(*filters)
        .group_by(ApiEvent.event_type)
        .order_by(ApiEvent.event_type)
    )

    result = await db.execute(stmt)
    rows = result.all()

    by_type = []
    total_events = 0
    for row in rows:
        by_type.append(
            EventTypeSummary(
                event_type=row.event_type,
                total=row.total,
                success=row.success,
                failed=row.failed,
                error=row.error,
                avg_duration_ms=round(float(row.avg_duration_ms), 1)
                if row.avg_duration_ms
                else None,
            )
        )
        total_events += row.total

    return AnalyticsSummary(
        period_start=start,
        period_end=end,
        total_events=total_events,
        by_type=by_type,
    )


@router.get("/analytics/events", response_model=EventListResponse)
async def analytics_events(
    event_type: str | None = Query(None, description="Filter by event type"),
    status: str | None = Query(None, description="Filter by status"),
    start: datetime | None = Query(None, description="Start of date range"),
    end: datetime | None = Query(None, description="End of date range"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> EventListResponse:
    """Get a paginated list of API events with optional filters."""
    filters = []
    if event_type:
        filters.append(ApiEvent.event_type == event_type)
    if status:
        filters.append(ApiEvent.status == status)
    if start:
        filters.append(ApiEvent.created_at >= start)
    if end:
        filters.append(ApiEvent.created_at <= end)

    # Total count
    count_stmt = select(func.count()).select_from(ApiEvent).where(*filters)
    total = (await db.execute(count_stmt)).scalar() or 0

    # Paginated results
    stmt = (
        select(ApiEvent)
        .where(*filters)
        .order_by(ApiEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    return EventListResponse(
        events=[
            EventListItem(
                id=e.id,
                event_type=e.event_type,
                status=e.status,
                api_key_hash=e.api_key_hash,
                record_id=e.record_id,
                external_id=e.external_id,
                duration_ms=e.duration_ms,
                error_detail=e.error_detail,
                metadata=e.metadata_,
                created_at=e.created_at,
            )
            for e in events
        ],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get("/analytics/timeseries", response_model=TimeseriesResponse)
async def analytics_timeseries(
    start: datetime | None = Query(None, description="Start of date range (ISO 8601)"),
    end: datetime | None = Query(None, description="End of date range (ISO 8601)"),
    interval: str = Query("hour", description="Bucket size: 'hour' or 'day'"),
    event_type: str | None = Query(None, description="Filter by event type"),
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> TimeseriesResponse:
    """Get time-series analytics bucketed by hour or day.

    Returns event counts and average latency per time bucket.
    Useful for trend charts. Defaults to last 7 days with hourly buckets.
    """
    if interval not in ("hour", "day"):
        interval = "hour"

    now = datetime.now(timezone.utc)
    if not end:
        end = now
    if not start:
        start = now - timedelta(days=7)

    filters = [ApiEvent.created_at >= start, ApiEvent.created_at <= end]
    if event_type:
        filters.append(ApiEvent.event_type == event_type)

    bucket = func.date_trunc(interval, ApiEvent.created_at).label("bucket")
    stmt = (
        select(
            bucket,
            func.count().label("total"),
            func.count(case((ApiEvent.status == "success", 1))).label("success"),
            func.count(case((ApiEvent.status == "failed", 1))).label("failed"),
            func.count(case((ApiEvent.status == "error", 1))).label("error"),
            func.avg(ApiEvent.duration_ms).label("avg_duration_ms"),
        )
        .where(*filters)
        .group_by(bucket)
        .order_by(bucket)
    )

    result = await db.execute(stmt)
    rows = result.all()

    buckets = [
        TimeseriesBucket(
            timestamp=row.bucket,
            total=row.total,
            success=row.success,
            failed=row.failed,
            error=row.error,
            avg_duration_ms=round(float(row.avg_duration_ms), 1)
            if row.avg_duration_ms
            else None,
        )
        for row in rows
    ]

    return TimeseriesResponse(
        interval=interval,
        period_start=start,
        period_end=end,
        buckets=buckets,
    )
