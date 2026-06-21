"""Enable production Row-Level Security on healthcare-sensitive tables.

Identity propagation: QueryExecutionService sets two transaction-local GUCs
before running any AI-generated SQL::

    SELECT set_config('app.current_user_role', <role>, true);
    SELECT set_config('app.current_user_id',   <uuid>, true);

Policy model (policies for the same command are OR-combined by PostgreSQL):

  * ``*_trusted``  — when NO role GUC is set (NULL), the caller is a trusted
                     backend operation (migrations, seeding, ORM writes). Full
                     access. This is what keeps existing functionality working.
  * ``*_role_read``— when a role GUC IS set (i.e. AI-generated SQL via the
                     read-only executor), SELECT is allowed only for the roles
                     permitted on that table. Financial ``claims`` are limited
                     to admin/analyst; clinical tables to all clinical roles.

FORCE ROW LEVEL SECURITY is used so the policies apply even when the executor
falls back to the table-owner credentials (i.e. before a dedicated read-only
role is provisioned) — RLS is therefore effective by default.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Clinical tables readable by every authenticated clinical role.
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
# Financial tables restricted to admin + analyst.
FINANCIAL_TABLES = ["claims"]

ALL_TABLES = CLINICAL_TABLES + FINANCIAL_TABLES

_CLINICAL_ROLES = "('admin','doctor','nurse','analyst')"
_FINANCIAL_ROLES = "('admin','analyst')"

_ROLE_GUC = "current_setting('app.current_user_role', true)"


def _enable(table: str, allowed_roles_sql: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')

    op.execute(f'DROP POLICY IF EXISTS "{table}_trusted" ON "{table}"')
    op.execute(f'DROP POLICY IF EXISTS "{table}_role_read" ON "{table}"')

    # Trusted backend (no role GUC set) → full access for all commands.
    op.execute(
        f'CREATE POLICY "{table}_trusted" ON "{table}" '
        f"FOR ALL USING ({_ROLE_GUC} IS NULL) "
        f"WITH CHECK ({_ROLE_GUC} IS NULL)"
    )
    # AI-generated SQL (role GUC set) → SELECT only, role-gated.
    op.execute(
        f'CREATE POLICY "{table}_role_read" ON "{table}" '
        f"FOR SELECT USING ({_ROLE_GUC} IN {allowed_roles_sql})"
    )


def upgrade() -> None:
    for t in CLINICAL_TABLES:
        _enable(t, _CLINICAL_ROLES)
    for t in FINANCIAL_TABLES:
        _enable(t, _FINANCIAL_ROLES)


def downgrade() -> None:
    for t in ALL_TABLES:
        op.execute(f'DROP POLICY IF EXISTS "{t}_role_read" ON "{t}"')
        op.execute(f'DROP POLICY IF EXISTS "{t}_trusted" ON "{t}"')
        op.execute(f'ALTER TABLE "{t}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY')
