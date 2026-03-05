import uuid

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.face_record import FaceRecord


class MatchService:
    async def find_matches(
        self,
        session: AsyncSession,
        query_embedding: np.ndarray,
        threshold: float = 0.6,
        limit: int = 10,
        exclude_id: uuid.UUID | None = None,
    ) -> list[dict]:
        """Find face records with cosine similarity >= threshold.

        pgvector cosine_distance = 1 - cosine_similarity,
        so similarity >= threshold means distance <= (1 - threshold).
        """
        distance_threshold = 1.0 - threshold
        embedding_list = query_embedding.tolist()

        stmt = (
            select(
                FaceRecord,
                FaceRecord.embedding.cosine_distance(embedding_list).label("distance"),
            )
            .where(
                FaceRecord.embedding.cosine_distance(embedding_list)
                <= distance_threshold
            )
            .order_by("distance")
            .limit(limit)
        )

        if exclude_id:
            stmt = stmt.where(FaceRecord.id != exclude_id)

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "record_id": str(row.FaceRecord.id),
                "name": row.FaceRecord.name,
                "external_id": row.FaceRecord.external_id,
                "similarity": round(1.0 - row.distance, 4),
                "metadata": row.FaceRecord.metadata_,
            }
            for row in rows
        ]
