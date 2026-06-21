"""Unit tests for the global security-headers middleware."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.security_headers import SecurityHeadersMiddleware


def _client():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/thing")
    def thing():
        return {"ok": True}

    return TestClient(app)


def test_core_security_headers_present():
    r = _client().get("/thing")
    h = r.headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in h["Permissions-Policy"]
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]


def test_strict_csp_on_api_routes():
    r = _client().get("/thing")
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp
    assert "script-src 'self'" in csp
    # No CDN allowance on non-docs routes.
    assert "jsdelivr" not in csp
