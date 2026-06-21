"""FastAPI dependency injection: DB session, current user, Redis client."""

from typing import Annotated, AsyncGenerator, Optional

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import verify_token
from app.db.models.user import User
from app.db.session import AsyncSessionLocal

logger = structlog.get_logger(__name__)
settings = get_settings()
# auto_error=False so we can ALSO accept the token from the HttpOnly cookie.
security = HTTPBearer(auto_error=False)


# ── Database ──────────────────────────────────────────────────────────────────


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async SQLAlchemy session, committing on success and rolling back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Redis ─────────────────────────────────────────────────────────────────────


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Yield an async Redis client."""
    client: aioredis.Redis = aioredis.from_url(
        settings.redis_url,
        encoding="utf-8",
        decode_responses=True,
    )
    try:
        yield client
    finally:
        await client.aclose()


# ── Authentication ────────────────────────────────────────────────────────────


DENYLIST_PREFIX = "jwt:denylist:"


def _extract_token(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials]
) -> Optional[str]:
    """Prefer the Authorization: Bearer header; fall back to the HttpOnly cookie."""
    if credentials and credentials.credentials:
        return credentials.credentials
    return request.cookies.get(settings.cookie_access_name)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
) -> User:
    """Validate JWT (cookie or bearer) and return the authenticated user."""
    token = _extract_token(request, credentials)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_token(token)

    if not payload or payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject tokens that have been explicitly revoked (logout / forced sign-out)
    jti = payload.get("jti")
    if jti:
        try:
            if await redis.exists(f"{DENYLIST_PREFIX}{jti}"):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        except HTTPException:
            raise
        except Exception:
            # Fail-open on Redis outage would be unsafe for revocation, but
            # fail-closed would take down all auth if Redis blips. We log and
            # allow, matching the app's "Redis is a cache" posture.
            logger.warning("Denylist check skipped — Redis unavailable")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token"
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    return user


class RequireRole:
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = allowed_roles

    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of: {', '.join(self.allowed_roles)}",
            )
        return current_user


async def get_current_admin(
    current_user: User = Depends(RequireRole(["admin"])),
) -> User:
    return current_user


# ── Type Aliases (for cleaner route signatures) ───────────────────────────────

DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisClient = Annotated[aioredis.Redis, Depends(get_redis)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAdmin = Annotated[User, Depends(get_current_admin)]
