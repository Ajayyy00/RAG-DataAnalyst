"""Authentication routes: register, login, refresh, me, change-password, logout.

Browsers authenticate via HttpOnly cookies (set on login/refresh, cleared on
logout). Programmatic clients may still use the returned bearer tokens. Refresh
tokens are rotated on every use and the spent token is denylisted.
"""

import time

from fastapi import APIRouter, Depends, Form, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.core.cookies import clear_auth_cookies, set_auth_cookies
from app.core.rate_limit import RateLimit
from app.core.security import verify_token
from app.dependencies import DENYLIST_PREFIX, CurrentUser, DbSession, RedisClient
from app.schemas.auth import (
    ChangePasswordRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter()
settings = get_settings()
_bearer = HTTPBearer(auto_error=False)


async def _denylist_jti(redis, payload: dict) -> None:
    """Add a token's jti to the Redis denylist until its natural expiry."""
    jti = payload.get("jti")
    exp = payload.get("exp")
    if not jti:
        return
    ttl = max(int(exp - time.time()), 1) if exp else 3600
    await redis.setex(f"{DENYLIST_PREFIX}{jti}", ttl, "revoked")


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    dependencies=[Depends(RateLimit("register", limit=5, window_seconds=300))],
)
async def register(data: UserRegisterRequest, db: DbSession) -> UserResponse:
    service = AuthService(db)
    user = await service.register_user(data)
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive JWT tokens (also set as HttpOnly cookies)",
    dependencies=[Depends(RateLimit("login", limit=10, window_seconds=60))],
)
async def login(
    response: Response,
    db: DbSession,
    username: str = Form(...),
    password: str = Form(...),
) -> TokenResponse:
    service = AuthService(db)
    tokens = await service.authenticate_user(username, password)
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and receive a fresh access token",
    dependencies=[Depends(RateLimit("refresh", limit=30, window_seconds=60))],
)
async def refresh_token(
    request: Request,
    response: Response,
    db: DbSession,
    redis: RedisClient,
    data: RefreshTokenRequest | None = None,
) -> TokenResponse:
    # Prefer the HttpOnly cookie; fall back to a JSON body for API clients.
    raw = request.cookies.get(settings.cookie_refresh_name)
    if not raw and data is not None:
        raw = data.refresh_token

    payload = verify_token(raw) if raw else None
    if not payload or payload.get("type") != "refresh":
        clear_auth_cookies(response)
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Invalid or expired refresh token")

    # Reject already-rotated / revoked refresh tokens (replay protection).
    jti = payload.get("jti")
    if jti and await redis.exists(f"{DENYLIST_PREFIX}{jti}"):
        clear_auth_cookies(response)
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError("Refresh token has already been used")

    service = AuthService(db)
    tokens = await service.refresh_access_token(raw)

    # Rotation: invalidate the spent refresh token.
    await _denylist_jti(redis, payload)
    set_auth_cookies(response, tokens.access_token, tokens.refresh_token)
    return tokens


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current authenticated user profile",
)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.post(
    "/change-password",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Change current user password",
)
async def change_password(
    data: ChangePasswordRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> None:
    service = AuthService(db)
    await service.change_password(
        current_user, data.current_password, data.new_password
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current tokens and clear auth cookies",
)
async def logout(
    request: Request,
    response: Response,
    current_user: CurrentUser,
    redis: RedisClient,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> None:
    """Denylist the presented access (and refresh) tokens and clear cookies."""
    access_raw = (
        credentials.credentials
        if credentials
        else request.cookies.get(settings.cookie_access_name)
    )
    if access_raw:
        payload = verify_token(access_raw)
        if payload:
            await _denylist_jti(redis, payload)

    refresh_raw = request.cookies.get(settings.cookie_refresh_name)
    if refresh_raw:
        rpayload = verify_token(refresh_raw)
        if rpayload:
            await _denylist_jti(redis, rpayload)

    clear_auth_cookies(response)
