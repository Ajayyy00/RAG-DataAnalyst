"""Integration tests for auth routes — DB/Redis mocked via dependency overrides."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token, hash_password, verify_password
from app.db.models.user import User


@pytest.fixture
def sample_user():
    return User(
        id=uuid.uuid4(),
        email="doctor@hospital.com",
        username="drsmith",
        hashed_password=hash_password("SecurePass1!"),
        role="clinician",
        is_active=True,
    )


@pytest.fixture
def user_token(sample_user):
    return create_access_token({"sub": str(sample_user.id), "role": sample_user.role})


# ── /auth/me ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_me_returns_user_profile(sample_user, user_token):
    from app.main import app
    from app.dependencies import get_db, get_redis, get_current_user

    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_current_user] = lambda: sample_user

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {user_token}"},
        ) as client:
            response = await client.get("/api/v1/auth/me")

        assert response.status_code == 200
        data = response.json()
        assert data["email"] == sample_user.email
        assert data["username"] == sample_user.username
        assert data["role"] == sample_user.role
        # Must never leak the password hash
        assert "hashed_password" not in data
    finally:
        app.dependency_overrides.clear()


# ── Unauthenticated access ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_protected_route_requires_auth():
    from app.main import app
    from app.dependencies import get_db, get_redis

    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_invalid_bearer_token_rejected():
    from app.main import app
    from app.dependencies import get_db, get_redis

    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer totally-invalid-token"},
        ) as client:
            response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ── Security utility tests (pure unit — no HTTP) ──────────────────────────────

class TestSecurityUtils:
    def test_hash_and_verify_password(self):
        pw = "MySecurePassword42!"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)
        assert not verify_password("wrongpassword", hashed)

    def test_different_passwords_produce_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password1")
        # bcrypt salts produce different hashes for same input
        assert h1 != h2
        # but both verify correctly
        assert verify_password("password1", h1)
        assert verify_password("password1", h2)

    def test_access_token_contains_sub_and_type(self):
        from jose import jwt
        from app.config import get_settings
        settings = get_settings()
        uid = str(uuid.uuid4())
        token = create_access_token({"sub": uid, "role": "analyst"})
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        assert payload["sub"] == uid
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_expired_token_fails_verification(self):
        from datetime import timedelta
        from app.core.security import verify_token
        token = create_access_token({"sub": "test"}, expires_delta=timedelta(seconds=-1))
        payload = verify_token(token)
        assert payload is None

    def test_token_with_wrong_secret_fails(self):
        from app.core.security import verify_token
        from jose import jwt
        # Sign with a different key
        bad_token = jwt.encode({"sub": "x", "exp": 9999999999}, "wrong-secret", algorithm="HS256")
        assert verify_token(bad_token) is None
