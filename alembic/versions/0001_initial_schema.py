"""Initial schema with face_records table and HNSW index

Revision ID: 0001
Revises:
Create Date: 2026-03-05

"""
from typing import Sequence, Union

import pgvector
import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "face_records",
        sa.Column("id", sa.UUID(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column("image_path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # B-tree index on external_id
    op.create_index("ix_face_records_external_id", "face_records", ["external_id"])

    # HNSW index for fast approximate nearest neighbor search
    op.execute("""
        CREATE INDEX ix_face_records_embedding_hnsw
        ON face_records
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 200)
    """)


def downgrade() -> None:
    op.drop_index("ix_face_records_embedding_hnsw", table_name="face_records")
    op.drop_index("ix_face_records_external_id", table_name="face_records")
    op.drop_table("face_records")
    op.execute("DROP EXTENSION IF EXISTS vector")
