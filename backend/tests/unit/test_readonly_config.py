"""Unit tests for read-only database isolation configuration."""

from app.config import Settings


def _settings(**overrides) -> Settings:
    base = dict(
        postgres_host="db",
        postgres_port=5432,
        postgres_db="hc",
        postgres_user="hc_user",
        postgres_password="pw",
    )
    base.update(overrides)
    # _env_file=None prevents .env from leaking into the unit test.
    return Settings(_env_file=None, **base)


def test_readonly_url_falls_back_to_primary_when_unset():
    s = _settings()
    assert s.readonly_database_url == ("postgresql+asyncpg://hc_user:pw@db:5432/hc")
    assert s.has_dedicated_readonly_role is False


def test_dedicated_readonly_role_detected():
    s = _settings(readonly_postgres_user="hc_readonly", readonly_postgres_password="ro")
    assert s.has_dedicated_readonly_role is True
    assert s.readonly_database_url == ("postgresql+asyncpg://hc_readonly:ro@db:5432/hc")


def test_same_user_is_not_a_dedicated_role():
    # Supplying the SAME user as primary does not count as isolation.
    s = _settings(readonly_postgres_user="hc_user")
    assert s.has_dedicated_readonly_role is False


def test_readonly_can_point_at_separate_host_and_db():
    s = _settings(
        readonly_postgres_host="replica",
        readonly_postgres_port=5433,
        readonly_postgres_db="hc_ro",
        readonly_postgres_user="hc_readonly",
        readonly_postgres_password="ro",
    )
    assert s.readonly_database_url == (
        "postgresql+asyncpg://hc_readonly:ro@replica:5433/hc_ro"
    )


def test_primary_url_unaffected_by_readonly_settings():
    s = _settings(readonly_postgres_user="hc_readonly", readonly_postgres_password="ro")
    assert s.database_url == "postgresql+asyncpg://hc_user:pw@db:5432/hc"
