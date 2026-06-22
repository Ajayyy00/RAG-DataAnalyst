#!/usr/bin/env python
"""
Generate the Supabase SQL bundle directly from the SQLAlchemy models.
=====================================================================
This is the single source of truth for the hand-runnable Supabase schema, so
the SQL can never drift from the ORM / Alembic definitions.

Outputs (repo-root ``supabase/``):
    migration.sql      — extensions + tables + indexes + RLS + least-privilege role
    rollback.sql       — drops everything created by migration.sql
    rls_policies.sql   — just the Row-Level Security policies (apply standalone)

Usage:
    python scripts/emit_supabase_sql.py

The DDL is emitted with the PostgreSQL dialect and ``IF NOT EXISTS`` so the
bundle is idempotent and safe to paste into the Supabase SQL editor or run via
``supabase db push`` / ``psql``.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import Boolean, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable, DefaultClause

import app.db.models  # noqa: F401  — registers every table on Base.metadata
from app.db.base import Base

PG = postgresql.dialect()


def _inject_server_defaults() -> None:
    """Add Postgres server defaults so the schema is usable from raw SQL too.

    The ORM applies these defaults client-side (Python ``uuid.uuid4`` / bools),
    which leaves the emitted DDL without DEFAULTs. Adding them is additive — the
    ORM keeps sending its own values — but lets manual INSERTs and the Supabase
    SQL editor work without supplying every column.
    """
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if col.server_default is not None:
                continue
            if col.name == "id" and col.primary_key:
                col.server_default = DefaultClause(text("gen_random_uuid()"))
            elif isinstance(col.type, Boolean) and getattr(
                col.default, "is_scalar", False
            ):
                col.server_default = DefaultClause(
                    text("true" if col.default.arg else "false")
                )


# RLS configuration — mirrors alembic/versions/b2c3d4e5f6a7_enable_row_level_security.py
CLINICAL_TABLES = [
    "patients",
    "encounters",
    "diagnoses",
    "procedures",
    "medications",
    "lab_results",
    "vital_signs",
    "readmissions",
    "providers",
]
FINANCIAL_TABLES = ["claims"]
RLS_TABLES = CLINICAL_TABLES + FINANCIAL_TABLES
CLINICAL_ROLES = "('admin','doctor','nurse','analyst')"
FINANCIAL_ROLES = "('admin','analyst')"
ROLE_GUC = "current_setting('app.current_user_role', true)"

# Tables holding PHI / secrets that must NEVER be exposed through PostgREST.
PHI_TABLES = RLS_TABLES + [
    "users",
    "audit_logs",
    "copilot_sessions",
    "copilot_messages",
]

HEADER = """\
-- ============================================================================
--  Healthcare Copilot — Supabase schema bundle (AUTO-GENERATED)
--  Source of truth: SQLAlchemy models (regenerate via
--  backend/scripts/emit_supabase_sql.py). Do not hand-edit.
--
--  Apply:  paste into Supabase SQL editor, or
--          psql "$SUPABASE_DB_URL" -f supabase/migration.sql
--
--  Security model preserved from the self-hosted deployment:
--    * Transaction-local GUC `app.current_user_role` drives RLS. The trusted
--      backend (GUC unset) keeps full access; AI-generated SQL runs under the
--      read-only role with the GUC set => SELECT-only, role-gated.
--    * PHI columns on `users` stay TEXT (Fernet ciphertext, encrypted by the app).
--    * PostgREST roles (anon, authenticated) are REVOKED from all PHI tables.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

"""


def _ddl(stmt) -> str:
    return str(stmt.compile(dialect=PG)).strip()


def emit_tables() -> str:
    chunks: list[str] = [
        "-- ── Tables ────────────────────────────────────────────────────────────────"
    ]
    for table in Base.metadata.sorted_tables:  # FK-dependency order
        chunks.append(_ddl(CreateTable(table, if_not_exists=True)) + ";")
    return "\n\n".join(chunks)


def emit_indexes() -> str:
    chunks: list[str] = [
        "-- ── Indexes ───────────────────────────────────────────────────────────────"
    ]
    for table in Base.metadata.sorted_tables:
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            chunks.append(_ddl(CreateIndex(index, if_not_exists=True)) + ";")
    return "\n".join(chunks)


def emit_rls() -> str:
    lines: list[str] = [
        "-- ── Row-Level Security (GUC-driven, mirrors Alembic b2c3d4e5f6a7) ──────────"
    ]

    def policy(table: str, roles: str) -> None:
        lines.append(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY;')
        lines.append(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY;')
        lines.append(f'DROP POLICY IF EXISTS "{table}_trusted" ON "{table}";')
        lines.append(f'DROP POLICY IF EXISTS "{table}_role_read" ON "{table}";')
        lines.append(
            f'CREATE POLICY "{table}_trusted" ON "{table}" '
            f"FOR ALL USING ({ROLE_GUC} IS NULL) "
            f"WITH CHECK ({ROLE_GUC} IS NULL);"
        )
        lines.append(
            f'CREATE POLICY "{table}_role_read" ON "{table}" '
            f"FOR SELECT USING ({ROLE_GUC} IN {roles});"
        )
        lines.append("")

    for t in CLINICAL_TABLES:
        policy(t, CLINICAL_ROLES)
    for t in FINANCIAL_TABLES:
        policy(t, FINANCIAL_ROLES)

    lines.append(
        "-- Defense in depth: keep PHI out of the PostgREST data API entirely."
    )
    lines.append("DO $$ BEGIN")
    for role in ("anon", "authenticated"):
        for t in PHI_TABLES:
            lines.append(
                f"  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN"
                f' REVOKE ALL ON "{t}" FROM {role}; END IF;'
            )
    lines.append("END $$;")
    return "\n".join(lines)


def emit_readonly_role() -> str:
    grants = "\n".join(
        f'    GRANT SELECT ON "{t}" TO hc_readonly;'
        for t in (RLS_TABLES + ["departments", "facilities"])
    )
    return f"""\
-- ── Least-privilege executor role for AI-generated SQL ─────────────────────
-- Set the password first:  \\set ro_password 'your-strong-password'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hc_readonly') THEN
    CREATE ROLE hc_readonly LOGIN PASSWORD :'ro_password'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO hc_readonly;
{grants}
-- No grants on users / audit_logs / copilot_* => analysts can never read them.
"""


def emit_rollback() -> str:
    lines = [
        "-- ============================================================================",
        "--  Healthcare Copilot — Supabase rollback (AUTO-GENERATED)",
        "--  Drops every object created by migration.sql. DESTRUCTIVE.",
        "-- ============================================================================",
        "",
        "-- Drop RLS policies first (tables dropped below take their policies with them,",
        "-- but we drop explicitly so partial rollbacks are clean).",
    ]
    for t in RLS_TABLES:
        lines.append(f'DROP POLICY IF EXISTS "{t}_role_read" ON "{t}";')
        lines.append(f'DROP POLICY IF EXISTS "{t}_trusted" ON "{t}";')
    lines.append("")
    lines.append("-- Drop tables in reverse FK-dependency order.")
    for table in reversed(Base.metadata.sorted_tables):
        lines.append(f'DROP TABLE IF EXISTS "{table.name}" CASCADE;')
    lines.append("")
    lines.append("DROP ROLE IF EXISTS hc_readonly;")
    return "\n".join(lines)


def main() -> None:
    _inject_server_defaults()
    out_dir = ROOT.parent / "supabase"
    out_dir.mkdir(exist_ok=True)

    migration = (
        "\n\n".join(
            [
                HEADER.rstrip(),
                emit_tables(),
                emit_indexes(),
                emit_rls(),
                emit_readonly_role(),
            ]
        )
        + "\n"
    )
    (out_dir / "migration.sql").write_text(migration, encoding="utf-8")

    rls_only = HEADER.split("CREATE EXTENSION")[0].rstrip() + "\n\n" + emit_rls() + "\n"
    (out_dir / "rls_policies.sql").write_text(rls_only, encoding="utf-8")

    (out_dir / "rollback.sql").write_text(emit_rollback() + "\n", encoding="utf-8")

    print(f"Wrote {out_dir / 'migration.sql'}")
    print(f"Wrote {out_dir / 'rls_policies.sql'}")
    print(f"Wrote {out_dir / 'rollback.sql'}")


if __name__ == "__main__":
    main()
