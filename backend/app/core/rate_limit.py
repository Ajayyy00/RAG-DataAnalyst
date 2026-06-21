"""Lightweight Redis fixed-window rate limiter (no extra dependencies).

Usage as a FastAPI dependency::

    @router.post("/login", dependencies=[Depends(RateLimit("login", limit=5, window_seconds=60))])

Keyed by client IP. Fails open if Redis is unavailable so a cache outage never
locks every user out, but logs the degradation.
"""

import structlog
from fastapi import Depends, HTTPException, Request, status

from app.dependencies import get_redis

logger = structlog.get_logger(__name__)


class RateLimit:
    def __init__(self, name: str, limit: int = 10, window_seconds: int = 60) -> None:
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds

    async def __call__(self, request: Request, redis=Depends(get_redis)) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"ratelimit:{self.name}:{client_ip}"
        try:
            current = await redis.incr(key)
            if current == 1:
                await redis.expire(key, self.window_seconds)
            if current > self.limit:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down and try again later.",
                    headers={"Retry-After": str(self.window_seconds)},
                )
        except HTTPException:
            raise
        except Exception as exc:  # Redis down → don't block legitimate traffic
            logger.warning("Rate limit check skipped", error=str(exc))
