"""Query execution service: runs validated SQL on PostgreSQL with timeout control."""

import time
from typing import Any, Dict, List

import structlog
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import QueryExecutionError
from app.db.session import ReadOnlySessionLocal

logger = structlog.get_logger(__name__)
settings = get_settings()


class QueryExecutionService:
    """Executes analyst-generated SQL on a dedicated, fresh read-only session.

    The session passed to the constructor (if any) is retained only for backward
    compatibility; the actual query always runs on a brand-new read-only
    transaction so ``SET TRANSACTION READ ONLY`` is guaranteed to precede any
    statement and so execution is isolated from the request's main session.
    """

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db

    async def execute(
        self,
        sql: str,
        max_rows: int | None = None,
        user_role: str | None = None,
        user_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Execute a validated SQL query and return structured results.

        Returns a dict with: columns, rows, row_count, execution_ms
        """
        limit = max_rows or settings.max_rows
        timeout_ms = settings.query_timeout_seconds * 1000

        start = time.monotonic()
        try:
            async with ReadOnlySessionLocal() as session:
                # Enforce a read-only transaction FIRST, before any statement runs,
                # to block any data mutation even if validation is somehow bypassed.
                await session.execute(text("SET TRANSACTION READ ONLY"))
                await session.execute(
                    text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'")
                )

                # GUCs consumed by PostgreSQL Row-Level Security policies.
                if user_role:
                    await session.execute(
                        text("SELECT set_config('app.current_user_role', :role, true)"),
                        {"role": str(user_role)},
                    )
                if user_id:
                    await session.execute(
                        text("SELECT set_config('app.current_user_id', :uid, true)"),
                        {"uid": str(user_id)},
                    )

                result = await session.execute(text(sql))
                rows_raw = result.fetchmany(limit)
                columns: List[str] = list(result.keys())

        except OperationalError as exc:
            msg = str(exc.orig) if exc.orig else str(exc)
            if "statement_timeout" in msg or "canceling statement" in msg.lower():
                raise QueryExecutionError(
                    f"Query exceeded the {settings.query_timeout_seconds}s time limit"
                ) from exc
            # Do NOT echo raw DB internals back to the client (schema disclosure).
            logger.warning("Query execution operational error", error=msg)
            raise QueryExecutionError("The query could not be executed.") from exc
        except ProgrammingError as exc:
            msg = str(exc.orig) if exc.orig else str(exc)
            logger.warning("Query execution programming error", error=msg)
            raise QueryExecutionError(
                "The generated SQL was invalid and could not be executed."
            ) from exc
        except Exception as exc:
            logger.error("Unexpected query execution error", error=str(exc))
            raise QueryExecutionError(
                "An unexpected error occurred while executing the query."
            ) from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        rows: List[List[Any]] = [list(row) for row in rows_raw]

        logger.info(
            "Query executed",
            row_count=len(rows),
            execution_ms=elapsed_ms,
            columns=columns,
        )

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "execution_ms": elapsed_ms,
        }
