"""HttpOnly auth-cookie helpers.

Tokens are delivered to browsers as HttpOnly cookies so client-side JavaScript
(and therefore XSS) cannot read them. The refresh cookie is additionally scoped
to the refresh endpoint path to limit its exposure surface.
"""

from __future__ import annotations

from fastapi import Response

from app.config import get_settings

settings = get_settings()

_ACCESS_MAX_AGE = settings.access_token_expire_minutes * 60
_REFRESH_MAX_AGE = settings.refresh_token_expire_days * 24 * 3600
_REFRESH_PATH = f"{settings.api_prefix}/auth/refresh"


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    """Attach HttpOnly access + refresh cookies to the response."""
    common = dict(
        httponly=True,
        secure=settings.cookie_secure_effective,
        samesite=settings.cookie_samesite,
        domain=settings.cookie_domain,
    )
    response.set_cookie(
        settings.cookie_access_name,
        access_token,
        max_age=_ACCESS_MAX_AGE,
        path="/",
        **common,
    )
    # Refresh cookie is only ever sent to the refresh endpoint.
    response.set_cookie(
        settings.cookie_refresh_name,
        refresh_token,
        max_age=_REFRESH_MAX_AGE,
        path=_REFRESH_PATH,
        **common,
    )


def clear_auth_cookies(response: Response) -> None:
    """Remove the auth cookies (logout)."""
    response.delete_cookie(
        settings.cookie_access_name, path="/", domain=settings.cookie_domain
    )
    response.delete_cookie(
        settings.cookie_refresh_name,
        path=_REFRESH_PATH,
        domain=settings.cookie_domain,
    )
