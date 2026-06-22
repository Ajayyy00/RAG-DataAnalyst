"""Async SQLAlchemy engine and session factory."""

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.db.base import Base  # noqa: F401  — import so Base knows all models

logger = structlog.get_logger(__name__)
settings = get_settings()

# Connection arguments are Supabase-aware: TLS for managed hosts, and on the
# transaction pooler (:6543) prepared-statement caching is disabled. See
# Settings.asyncpg_connect_args.
_CONNECT_ARGS = settings.asyncpg_connect_args

# ── Async Engine ──────────────────────────────────────────────────────────────
engine = create_async_engine(
    settings.database_url,
    echo=settings.app_debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=1800,
    connect_args=_CONNECT_ARGS,
)

try:
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine,
    )
except ImportError:
    pass

# ── Session Factory ───────────────────────────────────────────────────────────
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# ── Read-only Engine ──────────────────────────────────────────────────────────
# Analyst-generated SQL is executed here, ideally under a least-privilege role
# (configure READONLY_POSTGRES_USER/PASSWORD). Using a *separate* engine also
# guarantees each generated query runs in its own fresh transaction, so
# `SET TRANSACTION READ ONLY` is always issued before any statement.
readonly_engine = create_async_engine(
    settings.readonly_database_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    connect_args=_CONNECT_ARGS,
)

ReadOnlySessionLocal = async_sessionmaker(
    bind=readonly_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    reraise=True,
)
async def wait_for_database() -> None:
    """Ping the database, retrying with exponential backoff.

    Managed/pooled databases (Supabase) can briefly refuse connections during
    cold starts or pooler restarts; this gives the backend a resilient startup
    instead of crash-looping. Call from the FastAPI lifespan/startup hook.
    """
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    logger.info("database_connectivity_ok", host=settings.db_components[2])


async def create_tables() -> None:
    """Create all tables (used for testing / first-run without Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    """Drop all tables (used in test teardown)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
