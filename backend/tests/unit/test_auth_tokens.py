"""Unit tests for PyJWT tokens and HttpOnly auth cookies."""

from datetime import timedelta

from fastapi import Response

from app.core import security
from app.core.cookies import clear_auth_cookies, set_auth_cookies


def test_access_token_roundtrip_has_required_claims():
    tok = security.create_access_token({"sub": "u1", "role": "doctor"})
    payload = security.verify_token(tok)
    assert payload is not None
    assert payload["type"] == "access"
    assert payload["sub"] == "u1"
    assert payload["role"] == "doctor"
    assert payload["jti"]  # revocable


def test_refresh_token_type_and_helper():
    tok = security.create_refresh_token({"sub": "u1"})
    assert security.verify_refresh_token(tok) is not None
    # An access token must NOT validate as a refresh token.
    access = security.create_access_token({"sub": "u1"})
    assert security.verify_refresh_token(access) is None


def test_expired_token_is_rejected():
    tok = security.create_access_token(
        {"sub": "u1"}, expires_delta=timedelta(seconds=-1)
    )
    assert security.verify_token(tok) is None


def test_garbage_and_empty_tokens_rejected():
    assert security.verify_token("not-a-jwt") is None
    assert security.verify_token("") is None


def test_tampered_signature_rejected():
    tok = security.create_access_token({"sub": "u1"})
    tampered = tok[:-3] + ("aaa" if not tok.endswith("aaa") else "bbb")
    assert security.verify_token(tampered) is None


def test_set_auth_cookies_are_httponly():
    resp = Response()
    set_auth_cookies(resp, "access-jwt", "refresh-jwt")
    cookies = resp.headers.getlist("set-cookie")
    assert any("access_token=access-jwt" in c and "HttpOnly" in c for c in cookies)
    assert any("refresh_token=refresh-jwt" in c and "HttpOnly" in c for c in cookies)
    # SameSite present on every auth cookie.
    assert all("SameSite" in c for c in cookies)


def test_clear_auth_cookies_expires_them():
    resp = Response()
    clear_auth_cookies(resp)
    cookies = resp.headers.getlist("set-cookie")
    assert any("access_token=" in c for c in cookies)
    assert any("Max-Age=0" in c or "expires=" in c.lower() for c in cookies)
