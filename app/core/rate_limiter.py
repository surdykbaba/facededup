import time

from fastapi import HTTPException, Request

from app.config import get_settings


async def rate_limit_dependency(request: Request) -> None:
    redis = request.app.state.redis
    settings = get_settings()

    identifier = request.headers.get("X-API-Key") or request.client.host
    key = f"ratelimit:{identifier}"
    now = time.time()
    window = settings.RATE_LIMIT_WINDOW_SECONDS

    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window)
    results = await pipe.execute()

    request_count = results[2]
    if request_count > settings.RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(window)},
        )
