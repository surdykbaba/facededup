"""Add api_events table for analytics/reporting.

Revision ID: 0002
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("api_key_hash", sa.String(16), nullable=False),
        sa.Column("record_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("duration_ms", sa.BigInteger, nullable=True),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_api_events_type_created",
        "api_events",
        ["event_type", "created_at"],
    )
    op.create_index(
        "ix_api_events_created",
        "api_events",
        ["created_at"],
    )
    op.create_index(
        "ix_api_events_api_key",
        "api_events",
        ["api_key_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_events_api_key", table_name="api_events")
    op.drop_index("ix_api_events_created", table_name="api_events")
    op.drop_index("ix_api_events_type_created", table_name="api_events")
    op.drop_table("api_events")
