import logging

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.face_record import FaceRecord
from app.services.match_service import MatchService

logger = logging.getLogger(__name__)


class DedupService:
    def __init__(self):
        self.match_service = MatchService()

    async def find_all_duplicates(
        self,
        session: AsyncSession,
        threshold: float = 0.6,
        batch_size: int = 100,
    ) -> dict:
        """Scan all records and return duplicate pairs.

        Uses batched nearest-neighbor search to avoid N^2 complexity.
        """
        # Get total count
        count_result = await session.execute(
            select(func.count()).select_from(FaceRecord)
        )
        total_records = count_result.scalar()

        duplicate_pairs = []
        seen_pairs: set[tuple[str, str]] = set()

        offset = 0
        processed = 0

        while True:
            stmt = (
                select(FaceRecord)
                .order_by(FaceRecord.created_at)
                .offset(offset)
                .limit(batch_size)
            )
            result = await session.execute(stmt)
            records = result.scalars().all()
            if not records:
                break

            for record in records:
                embedding = np.array(record.embedding, dtype=np.float32)
                matches = await self.match_service.find_matches(
                    session,
                    embedding,
                    threshold=threshold,
                    limit=50,
                    exclude_id=record.id,
                )
                for match in matches:
                    pair_key = tuple(sorted([str(record.id), match["record_id"]]))
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        duplicate_pairs.append(
                            {
                                "record_a": {
                                    "id": str(record.id),
                                    "name": record.name,
                                    "external_id": record.external_id,
                                },
                                "record_b": {
                                    "id": match["record_id"],
                                    "name": match["name"],
                                    "external_id": match["external_id"],
                                },
                                "similarity": match["similarity"],
                            }
                        )

                processed += 1

            offset += batch_size
            logger.info("Dedup progress: %d/%d records processed", processed, total_records)

        return {
            "total_records": total_records,
            "duplicate_pairs": duplicate_pairs,
            "total_duplicates": len(duplicate_pairs),
            "threshold": threshold,
        }
