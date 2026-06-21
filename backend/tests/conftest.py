"""Shared pytest fixtures for Healthcare Copilot test suite."""

import asyncio
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

# ── Env overrides before app import ──────────────────────────────────────────
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_DB", "test_healthcopilot")
os.environ.setdefault("POSTGRES_USER", "hc_user")
os.environ.setdefault("POSTGRES_PASSWORD", "changeme")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("CHROMADB_HOST", "localhost")
os.environ.setdefault("LLM_BASE_URL", "http://localhost:8080/v1")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-32-chars-minimum!!")
os.environ.setdefault("SECRET_KEY", "test-secret-key-32-chars-minimum!!")

from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db.models.user import User  # noqa: E402


# ── Event loop (session-scoped for pytest-asyncio) ────────────────────────────
@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ── Mock DB session ───────────────────────────────────────────────────────────
@pytest.fixture
def mock_db():
    """AsyncMock behaving like SQLAlchemy AsyncSession."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    db.close = AsyncMock()
    return db


# ── Mock Redis client ─────────────────────────────────────────────────────────
@pytest.fixture
def mock_redis():
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock()
    redis.delete = AsyncMock()
    return redis


# ── Test users ────────────────────────────────────────────────────────────────
@pytest.fixture
def analyst_user():
    return User(
        id=uuid.uuid4(),
        email="analyst@hospital.com",
        username="analyst",
        hashed_password=hash_password("Password123!"),
        role="analyst",
        is_active=True,
    )


@pytest.fixture
def admin_user():
    return User(
        id=uuid.uuid4(),
        email="admin@hospital.com",
        username="admin",
        hashed_password=hash_password("Admin123!"),
        role="admin",
        is_active=True,
    )


# ── JWT tokens ────────────────────────────────────────────────────────────────
@pytest.fixture
def analyst_token(analyst_user):
    return create_access_token({"sub": str(analyst_user.id), "role": analyst_user.role})


@pytest.fixture
def admin_token(admin_user):
    return create_access_token({"sub": str(admin_user.id), "role": admin_user.role})


# ── Async HTTP test client ────────────────────────────────────────────────────
@pytest_asyncio.fixture
async def async_client(mock_db, mock_redis, analyst_user, analyst_token):
    """ASGI test client with DB + Redis + auth dependency-overridden."""
    from httpx import ASGITransport, AsyncClient

    from app.dependencies import get_current_user, get_db, get_redis
    from app.main import app

    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_current_user] = lambda: analyst_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {analyst_token}"},
    ) as client:
        yield client

    app.dependency_overrides.clear()
