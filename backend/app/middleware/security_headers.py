"""Global security-response-headers middleware.

Adds the standard hardening headers to every response: CSP, HSTS (https only),
X-Frame-Options, X-Content-Type-Options, Referrer-Policy and Permissions-Policy.

The default CSP intentionally allows the jsDelivr CDN and inline styles/scripts
ONLY for the Swagger/ReDoc documentation routes (which bootstrap from a CDN);
all other responses get a strict 'self'-only policy.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import get_settings

settings = get_settings()

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

# Strict policy for API/JSON responses and the SPA-consumed endpoints.
_STRICT_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

# Relaxed policy so the bundled Swagger UI / ReDoc (CDN + inline init) still load.
_DOCS_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:; "
    "frame-ancestors 'none'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        path = request.url.path
        is_docs = any(path.startswith(p) for p in _DOCS_PATHS)
        response.headers["Content-Security-Policy"] = (
            _DOCS_CSP if is_docs else _STRICT_CSP
        )

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=()"
        )
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # HSTS only over HTTPS / in production (never on plain-http dev).
        if settings.is_production or request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        return response
