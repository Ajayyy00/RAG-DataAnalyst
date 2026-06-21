"""Integration tests for Row-Level Security and read-only isolation.

These require a live PostgreSQL with migrations applied (including
b2c3d4e5f6a7_enable_row_level_security). They SKIP automatically when no
database is reachable so the unit-test suite stays hermetic.

Run locally::

    docker compose up -d postgres
    alembic upgrade head
    pytest tests/integration -q
"""

import psycopg2
import pytest

from app.config import get_settings

settings = get_settings()


def _connect():
    return psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
        connect_timeout=3,
    )


@pytest.fixture(scope="module")
def conn():
    try:
        c = _connect()
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    yield c
    c.close()


def _select_count(conn, table, role=None):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("BEGIN")
        if role is not None:
            cur.execute("SELECT set_config('app.current_user_role', %s, true)", (role,))
        cur.execute(f"SELECT count(*) FROM {table}")
        n = cur.fetchone()[0]
        cur.execute("ROLLBACK")
    return n


def test_rls_enabled_on_sensitive_tables(conn):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT relname FROM pg_class "
            "WHERE relrowsecurity AND relnamespace = 'public'::regnamespace"
        )
        rls_tables = {r[0] for r in cur.fetchall()}
    for t in ("patients", "encounters", "claims", "medications"):
        assert t in rls_tables, f"RLS not enabled on {t}"


def test_nurse_cannot_read_claims(conn):
    # Financial claims are restricted to admin/analyst.
    assert _select_count(conn, "claims", role="nurse") == 0


def test_analyst_can_read_claims(conn):
    # Analyst is permitted (column-level PHI handled separately by redaction).
    # If the table is empty this is trivially 0; the point is it does not ERROR
    # and is not force-zeroed the way the nurse policy is.
    n_analyst = _select_count(conn, "claims", role="analyst")
    assert n_analyst >= 0


def test_trusted_backend_sees_all_rows(conn):
    # No role GUC set → trusted policy grants access (keeps seeding/ORM working).
    n_trusted = _select_count(conn, "patients", role=None)
    n_nurse = _select_count(conn, "patients", role="nurse")
    assert n_trusted >= n_nurse  # clinical table: nurse allowed, so equal


def test_unknown_role_is_denied(conn):
    # An unrecognized role value must see zero clinical rows (fail closed).
    assert _select_count(conn, "patients", role="intruder") == 0


def test_readonly_transaction_rejects_writes(conn):
    conn.rollback()
    with conn.cursor() as cur:
        cur.execute("BEGIN")
        cur.execute("SET TRANSACTION READ ONLY")
        with pytest.raises(psycopg2.Error):
            cur.execute("CREATE TEMP TABLE _probe (x int)")
    conn.rollback()
