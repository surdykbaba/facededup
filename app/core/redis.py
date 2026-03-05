import redis.asyncio as aioredis

from app.config import get_settings


def create_redis_pool() -> aioredis.Redis:
    settings = get_settings()
    return aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
    )
