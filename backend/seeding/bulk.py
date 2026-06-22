"""
Bulk COPY loader (raw asyncpg).
===============================
Uses PostgreSQL's binary COPY protocol via ``copy_records_to_table`` — the
fastest way to load millions of rows. Connects directly with asyncpg (bypassing
the SQLAlchemy/ORM layer) and is Supabase-aware (TLS).

For bulk seeding prefer the *direct connection* or *session pooler* (:5432).
The transaction pooler (:6543) also works for COPY but caps throughput.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Iterable, Sequence

import asyncpg

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import get_settings

settings = get_settings()


async def connect() -> asyncpg.Connection:
    """Open a single asyncpg connection from the resolved DB settings."""
    user, password, host, port, db = settings.db_components
    return await asyncpg.connect(
        user=user,
        password=password,
        host=host,
        port=port,
        database=db,
        ssl=settings.asyncpg_ssl,
        # COPY does not use prepared statements; safe on the transaction pooler.
        statement_cache_size=0,
        command_timeout=600,
    )


async def copy_chunks(
    conn: asyncpg.Connection,
    table: str,
    columns: Sequence[str],
    chunks: Iterable[list[tuple]],
    *,
    label: str | None = None,
) -> int:
    """COPY an iterable of row-chunks into ``table``; returns total rows loaded.

    ``chunks`` yields lists of tuples whose order matches ``columns``. Columns
    omitted from ``columns`` fall back to their server DEFAULT (e.g. created_at).
    """
    label = label or table
    total = 0
    started = time.perf_counter()
    for chunk in chunks:
        if not chunk:
            continue
        await conn.copy_records_to_table(table, records=chunk, columns=list(columns))
        total += len(chunk)
        elapsed = time.perf_counter() - started
        rate = total / elapsed if elapsed else 0
        print(
            f"  [{label}] {total:>12,} rows  ({rate:,.0f}/s)",
            end="\r",
            flush=True,
        )
    elapsed = time.perf_counter() - started
    rate = total / elapsed if elapsed else 0
    print(f"  [{label}] {total:>12,} rows  in {elapsed:6.1f}s  ({rate:,.0f}/s)")
    return total


async def truncate_all(conn: asyncpg.Connection) -> None:
    """Truncate clinical + reference tables (CASCADE). Leaves users/auth intact."""
    tables = [
        "readmissions",
        "claims",
        "vital_signs",
        "lab_results",
        "medications",
        "procedures",
        "diagnoses",
        "encounters",
        "patients",
        "providers",
        "departments",
        "facilities",
    ]
    await conn.execute(f"TRUNCATE TABLE {', '.join(tables)} CASCADE")
    print(f"  Truncated {len(tables)} tables")
