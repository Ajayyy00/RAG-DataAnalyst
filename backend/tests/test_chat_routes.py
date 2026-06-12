"""Integration tests for /chat/validate — all external services mocked."""

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import create_access_token
from app.db.models.user import User


@pytest.fixture
def analyst():
    return User(
        id=uuid.uuid4(),
        email="analyst@hospital.com",
        username="analyst1",
        hashed_password="hashed",
        role="analyst",
        is_active=True,
    )


@pytest.fixture
def analyst_token(analyst):
    return create_access_token({"sub": str(analyst.id), "role": analyst.role})


def make_client(app, analyst, analyst_token):
    """Helper to create an authenticated async client with mocked deps."""
    from app.dependencies import get_db, get_redis, get_current_user
    mock_db = AsyncMock()
    mock_redis = AsyncMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_redis] = lambda: mock_redis
    app.dependency_overrides[get_current_user] = lambda: analyst
    return AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )


# ── /chat/validate — good SQL ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_good_sql(analyst, analyst_token):
    from app.main import app
    async with make_client(app, analyst, analyst_token) as client:
        response = await client.post(
            "/api/v1/chat/validate",
            json={"sql": "SELECT id, first_name FROM patients LIMIT 10;"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["violations"] == []
    assert data["normalized_sql"] is not None


# ── /chat/validate — bad SQL ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_dml_returns_violations(analyst, analyst_token):
    from app.main import app
    async with make_client(app, analyst, analyst_token) as client:
        response = await client.post(
            "/api/v1/chat/validate",
            json={"sql": "DROP TABLE patients;"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert len(data["violations"]) > 0


@pytest.mark.asyncio
async def test_validate_unauthorized_table(analyst, analyst_token):
    from app.main import app
    async with make_client(app, analyst, analyst_token) as client:
        response = await client.post(
            "/api/v1/chat/validate",
            json={"sql": "SELECT * FROM users;"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["valid"] is False


# ── /chat/validate — auth guard ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_requires_auth():
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
            response = await client.post(
                "/api/v1/chat/validate",
                json={"sql": "SELECT 1;"},
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.clear()


# ── Parametrized SQL black-box tests via HTTP ─────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("sql,expected_valid", [
    ("SELECT * FROM patients LIMIT 10;", True),
    ("SELECT COUNT(*) FROM encounters;", True),
    ("SELECT p.id, d.icd10_code FROM patients p JOIN diagnoses d ON d.patient_id = p.id LIMIT 20;", True),
    ("DELETE FROM patients WHERE id='1';", False),
    ("SELECT * FROM users;", False),
    ("INSERT INTO patients (id) VALUES ('x');", False),
    ("UPDATE encounters SET discharge_date = NOW();", False),
    ("SELECT * FROM patients; DROP TABLE patients;", False),
])
async def test_validate_parametrized(analyst, analyst_token, sql, expected_valid):
    from app.main import app
    async with make_client(app, analyst, analyst_token) as client:
        resp = await client.post("/api/v1/chat/validate", json={"sql": sql})
    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["valid"] == expected_valid


# ── /health endpoint (no auth) ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_endpoint_returns_200():
    from app.main import app
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
