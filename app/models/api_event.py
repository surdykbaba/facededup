import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApiEvent(Base):
    """Tracks every significant API event for reporting and analytics."""

    __tablename__ = "api_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # enroll, match, deduplicate, compare, liveness, multi_frame_liveness, record_get, record_delete, batch_enroll, batch_enroll_embeddings
    status: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # success, failed, error
    api_key_hash: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # first 16 chars of SHA256 hash
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata", JSONB, nullable=True, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("NOW()")
    )

    __table_args__ = (
        Index("ix_api_events_type_created", "event_type", "created_at"),
        Index("ix_api_events_created", "created_at"),
        Index("ix_api_events_api_key", "api_key_hash"),
    )

    def __repr__(self) -> str:
        return f"<ApiEvent id={self.id} type={self.event_type} status={self.status}>"
