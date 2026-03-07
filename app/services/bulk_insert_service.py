"""Bulk insert service for high-volume face record enrollment.

Uses SQLAlchemy Core insert().values() for batch inserts, which is
~50x faster than ORM session.add() for large batches.

Also provides Redis-based progress tracking for long-running bulk jobs.
"""

import logging
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.face_record import FaceRecord

logger = logging.getLogger(__name__)


class BulkInsertService:
    @staticmethod
    async def bulk_insert_records(
        session: AsyncSession,
        records: list[dict],
        batch_size: int = 500,
    ) -> tuple[int, list[dict]]:
        """Insert records using Core bulk insert.

        Each record dict should have: id, name, external_id, metadata_,
        embedding, image_path.

        Returns (success_count, errors).
        On batch failure, falls back to individual inserts.
        """
        errors = []
        success = 0

        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            try:
                stmt = pg_insert(FaceRecord.__table__).values(batch)
                await session.execute(stmt)
                success += len(batch)
            except Exception as batch_err:
                logger.warning(
                    "Batch insert failed for rows %d-%d, falling back to individual: %s",
                    i,
                    i + len(batch),
                    batch_err,
                )
                # Fallback: insert one at a time to isolate bad records
                for j, record in enumerate(batch):
                    try:
                        stmt = pg_insert(FaceRecord.__table__).values([record])
                        await session.execute(stmt)
                        success += 1
                    except Exception as row_err:
                        errors.append(
                            {"index": i + j, "error": str(row_err)[:500]}
                        )

        # Commit everything that succeeded
        await session.commit()
        return success, errors

    @staticmethod
    def prepare_record(
        embedding: list[float],
        name: str | None = None,
        external_id: str | None = None,
        metadata: dict | None = None,
        image_path: str | None = None,
    ) -> dict:
        """Prepare a record dict for bulk insert."""
        record_id = uuid.uuid4()
        return {
            "id": record_id,
            "name": name,
            "external_id": external_id,
            "metadata": metadata or {},
            "embedding": embedding,
            "image_path": image_path or "",
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }


async def update_bulk_progress(
    redis: Redis,
    job_id: str,
    batches_completed: int,
    total_success: int,
    total_failed: int,
) -> None:
    """Update Redis hash with bulk job progress."""
    try:
        key = f"bulk_progress:{job_id}"
        await redis.hset(
            key,
            mapping={
                "batches_completed": str(batches_completed),
                "total_success": str(total_success),
                "total_failed": str(total_failed),
                "last_updated": datetime.now(timezone.utc).isoformat(),
            },
        )
        await redis.expire(key, 86400)  # TTL 24 hours
    except Exception:
        logger.debug("Failed to update bulk progress (non-fatal)", exc_info=True)


async def get_bulk_progress(redis: Redis, job_id: str) -> dict | None:
    """Retrieve bulk job progress from Redis."""
    key = f"bulk_progress:{job_id}"
    data = await redis.hgetall(key)
    if not data:
        return None
    return {
        "job_id": job_id,
        "batches_completed": int(data.get("batches_completed", 0)),
        "total_success": int(data.get("total_success", 0)),
        "total_failed": int(data.get("total_failed", 0)),
        "last_updated": data.get("last_updated"),
    }
