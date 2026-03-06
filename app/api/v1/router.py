from fastapi import APIRouter

from app.api.v1.endpoints import (
    compare, deduplicate, enroll, health, liveness,
    match, multi_frame_liveness, records,
)

v1_router = APIRouter()

# Health check is unauthenticated
v1_router.include_router(health.router, tags=["health"])

# Authenticated endpoints
v1_router.include_router(enroll.router, tags=["enrollment"])
v1_router.include_router(match.router, tags=["matching"])
v1_router.include_router(deduplicate.router, tags=["deduplication"])
v1_router.include_router(compare.router, tags=["comparison"])
v1_router.include_router(liveness.router, tags=["liveness"])
v1_router.include_router(multi_frame_liveness.router, tags=["liveness"])
v1_router.include_router(records.router, tags=["records"])
