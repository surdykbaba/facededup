from collections.abc import AsyncGenerator

from fastapi import Request
from insightface.app import FaceAnalysis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_face_analyzer(request: Request) -> FaceAnalysis:
    return request.app.state.face_analyzer


async def get_redis(request: Request) -> Redis:
    return request.app.state.redis
