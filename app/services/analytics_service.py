"""Fire-and-forget analytics event logging.

Every API call is recorded in the api_events table for reporting.
Logging runs as a background task and never blocks the API response.
All exceptions are swallowed — analytics must never break the API.
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime

from fastapi import Request

from app.models.api_event import ApiEvent

logger = logging.getLogger(__name__)


def _hash_api_key(api_key: str) -> str:
    """Hash an API key to a 16-char hex string for grouping without storing raw keys."""
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


async def _persist_event(
    session_factory,
    event_type: str,
    status: str,
    api_key: str | None,
    record_id: uuid.UUID | None = None,
    external_id: str | None = None,
    duration_ms: int | None = None,
    error_detail: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Insert an ApiEvent row using its own session (not the request session)."""
    try:
        async with session_factory() as session:
            event = ApiEvent(
                event_type=event_type,
                status=status,
                api_key_hash=_hash_api_key(api_key) if api_key else "unknown",
                record_id=record_id,
                external_id=external_id,
                duration_ms=duration_ms,
                error_detail=str(error_detail)[:2000] if error_detail else None,
                metadata_=metadata,
            )
            session.add(event)
            await session.commit()
    except Exception:
        logger.warning("Failed to log analytics event (non-fatal)", exc_info=True)


def log_event(
    request: Request,
    *,
    event_type: str,
    status: str,
    api_key: str | None = None,
    record_id: uuid.UUID | None = None,
    external_id: str | None = None,
    duration_ms: int | None = None,
    error_detail: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Fire-and-forget analytics logging. Safe to call from any endpoint.

    Uses asyncio.create_task to run the DB insert in the background.
    The request handler returns immediately without waiting.
    """
    session_factory = request.app.state.async_session
    asyncio.create_task(
        _persist_event(
            session_factory,
            event_type=event_type,
            status=status,
            api_key=api_key,
            record_id=record_id,
            external_id=external_id,
            duration_ms=duration_ms,
            error_detail=error_detail,
            metadata=metadata,
        )
    )
