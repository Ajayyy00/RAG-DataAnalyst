"""Startup database-security validation.

Run during application lifespan startup to prove — not assume — that the
read-only execution path is actually incapable of mutating data, and that a
dedicated least-privilege role is configured when required (production).

Design:
  * A *write succeeding* on the read-only path is a hard failure (raises).
  * Infrastructure being unreachable is a soft failure (warns) so the app can
    still boot in degraded environments, matching the rest of the lifespan.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text

from app.config import get_settings
from app.db.session import ReadOnlySessionLocal

logger = structlog.get_logger(__name__)
settings = get_settings()


class DatabaseSecurityError(RuntimeError):
    """Raised when the database security posture is unsafe for serving traffic."""


async def validate_readonly_execution_path() -> None:
    """Confirm the read-only session cannot perform writes.

    Opens the same kind of transaction the QueryExecutionService uses
    (``SET TRANSACTION READ ONLY``) and attempts a write. PostgreSQL must reject
    it. If the write *succeeds*, the isolation guarantee is broken and we refuse
    to start.
    """
    try:
        async with ReadOnlySessionLocal() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            who = (await session.execute(text("SELECT current_user"))).scalar()
            try:
                # TEMP table creation is a write; it must fail in a RO transaction.
                await session.execute(text("CREATE TEMP TABLE _ro_probe (x int)"))
            except Exception:
                logger.info(
                    "Read-only execution path verified — writes are rejected",
                    db_user=who,
                    dedicated_role=settings.has_dedicated_readonly_role,
                )
                return
            # If we got here the write was NOT rejected → critical.
            raise DatabaseSecurityError(
                "Read-only DB session accepted a write — execution isolation is "
                f"broken (connected as '{who}'). Refusing to start."
            )
    except DatabaseSecurityError:
        raise
    except Exception as exc:  # DB unreachable — degrade, do not crash boot
        logger.warning(
            "Could not verify read-only execution path (DB unreachable?)",
            error=str(exc),
        )


async def validate_readonly_role_privileges() -> None:
    """Warn (or fail in prod) on an over-privileged executor role."""
    if settings.require_readonly_role and not settings.has_dedicated_readonly_role:
        raise DatabaseSecurityError(
            "REQUIRE_READONLY_ROLE is set but no dedicated READONLY_POSTGRES_USER "
            "is configured. Provision the read-only role (see "
            "scripts/sql/create_readonly_role.sql) before starting."
        )

    if settings.is_production and not settings.has_dedicated_readonly_role:
        logger.warning(
            "Production is using the PRIMARY DB credentials to run AI-generated "
            "SQL. Configure READONLY_POSTGRES_USER/PASSWORD for defense-in-depth.",
        )

    try:
        async with ReadOnlySessionLocal() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT rolsuper, rolbypassrls, rolcreatedb "
                        "FROM pg_roles WHERE rolname = current_user"
                    )
                )
            ).first()
            if row is None:
                return
            rolsuper, rolbypassrls, rolcreatedb = row
            if rolsuper or rolbypassrls:
                msg = (
                    "Read-only executor role is SUPERUSER or has BYPASSRLS — RLS "
                    "policies will NOT be enforced for AI-generated SQL."
                )
                if settings.is_production:
                    raise DatabaseSecurityError(msg)
                logger.warning(msg, rolsuper=rolsuper, rolbypassrls=rolbypassrls)
            elif rolcreatedb:
                logger.warning("Read-only executor role can CREATE DATABASE")
    except DatabaseSecurityError:
        raise
    except Exception as exc:
        logger.warning("Could not inspect read-only role privileges", error=str(exc))


async def run_startup_security_checks() -> None:
    """Entry point called from the FastAPI lifespan."""
    await validate_readonly_role_privileges()
    await validate_readonly_execution_path()
