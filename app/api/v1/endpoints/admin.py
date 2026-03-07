"""Admin endpoints for index management during bulk operations.

For a 50M record import, the workflow is:
1. POST /admin/index/drop — drop the HNSW index
2. Run batch enrollment loop (much faster without incremental index updates)
3. POST /admin/index/create — rebuild the HNSW index in one pass
4. POST /admin/vacuum — VACUUM ANALYZE the table
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.security import verify_api_key

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/admin/index/status")
async def index_status(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Check if the HNSW index exists on face_records.embedding."""
    result = await db.execute(
        text(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE tablename = 'face_records' AND indexname LIKE '%hnsw%'"
        )
    )
    indexes = [{"name": row[0], "definition": row[1]} for row in result.fetchall()]

    # Also get the table row count
    count_result = await db.execute(
        text("SELECT COUNT(*) FROM face_records")
    )
    row_count = count_result.scalar()

    return {
        "hnsw_indexes": indexes,
        "index_exists": len(indexes) > 0,
        "total_records": row_count,
    }


@router.post("/admin/index/drop")
async def drop_index(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Drop the HNSW index on face_records.embedding.

    Call this BEFORE a large bulk import. Without the index,
    inserts are ~10-100x faster. Rebuild the index after import.
    """
    logger.warning("Dropping HNSW index ix_face_records_embedding_hnsw")

    # Must use raw connection for DDL that can't run inside a transaction
    raw_conn = await db.connection()
    await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
    await raw_conn.execute(
        text("DROP INDEX IF EXISTS ix_face_records_embedding_hnsw")
    )

    logger.info("HNSW index dropped successfully")
    return {"status": "dropped", "index": "ix_face_records_embedding_hnsw"}


@router.post("/admin/index/create")
async def create_index(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Rebuild the HNSW index on face_records.embedding.

    Call this AFTER completing a large bulk import. Building the index
    in one pass is much faster than incremental updates during insert.

    WARNING: This can take hours for 50M+ records. The request will
    return quickly — the index is built CONCURRENTLY so it doesn't lock
    the table. Check /admin/index/status to see when it's done.
    """
    logger.warning("Creating HNSW index (CONCURRENTLY) — this may take a while")

    raw_conn = await db.connection()
    await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
    await raw_conn.execute(
        text(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_face_records_embedding_hnsw "
            "ON face_records USING hnsw (embedding vector_cosine_ops) "
            "WITH (m = 16, ef_construction = 200)"
        )
    )

    logger.info("HNSW index creation initiated (CONCURRENTLY)")
    return {
        "status": "creating",
        "index": "ix_face_records_embedding_hnsw",
        "note": "Index is being built CONCURRENTLY. Check /admin/index/status to monitor.",
    }


@router.post("/admin/vacuum")
async def vacuum_analyze(
    db: AsyncSession = Depends(get_db),
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Run VACUUM ANALYZE on face_records to update query planner statistics.

    Call this after a large bulk import to ensure optimal query performance.
    """
    logger.warning("Running VACUUM ANALYZE on face_records")

    raw_conn = await db.connection()
    await raw_conn.execution_options(isolation_level="AUTOCOMMIT")
    await raw_conn.execute(text("VACUUM ANALYZE face_records"))

    logger.info("VACUUM ANALYZE completed")
    return {"status": "completed", "table": "face_records"}
