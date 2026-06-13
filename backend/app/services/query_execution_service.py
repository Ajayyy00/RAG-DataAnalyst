"""Query execution service: runs validated SQL on PostgreSQL with timeout control."""

import time
from typing import Any, Dict, List, Tuple

import structlog
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import QueryExecutionError

logger = structlog.get_logger(__name__)
settings = get_settings()


class QueryExecutionService:
    """Executes SQL queries on a read-only PostgreSQL session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def execute(
        self, sql: str, max_rows: int | None = None
    ) -> Dict[str, Any]:
        """
        Execute a validated SQL query and return structured results.

        Returns a dict with: columns, rows, row_count, execution_ms
        """
        limit = max_rows or settings.max_rows
        timeout_ms = settings.query_timeout_seconds * 1000

        start = time.monotonic()
        try:
            # Set statement_timeout at session level for this query
            await self.db.execute(
                text(f"SET LOCAL statement_timeout = '{timeout_ms}ms'")
            )
            # Enforce Read-Only transaction to prevent SQL injection data mutation
            await self.db.execute(text("SET TRANSACTION READ ONLY"))

            result = await self.db.execute(text(sql))
            rows_raw = result.fetchmany(limit)

        except OperationalError as exc:
            msg = str(exc.orig) if exc.orig else str(exc)
            if "statement_timeout" in msg or "canceling statement" in msg.lower():
                raise QueryExecutionError(
                    f"Query exceeded timeout of {settings.query_timeout_seconds}s"
                ) from exc
            raise QueryExecutionError(f"Database error: {msg}") from exc
        except ProgrammingError as exc:
            msg = str(exc.orig) if exc.orig else str(exc)
            raise QueryExecutionError(f"SQL execution error: {msg}") from exc
        except Exception as exc:
            raise QueryExecutionError(f"Unexpected error during execution: {exc}") from exc

        elapsed_ms = int((time.monotonic() - start) * 1000)

        columns: List[str] = list(result.keys())
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
