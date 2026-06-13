"""FastAPI application factory with lifespan, middleware, and router registration."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.config import get_settings
from app.core.exceptions import setup_exception_handlers
from app.core.logging import setup_logging
from app.api.v1.router import api_router

settings = get_settings()
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown hooks."""
    # ── Startup ───────────────────────────────────────────────
    setup_logging(settings.log_level)
    logger.info(
        "Starting Healthcare Copilot API",
        env=settings.app_env,
        debug=settings.app_debug,
    )

    # Schema → ChromaDB indexing (incremental, hash-based; non-fatal)
    try:
        from app.services.rag_service import RAGService
        from app.db.session import AsyncSessionLocal
        rag = RAGService()
        async with AsyncSessionLocal() as db:
            result = await rag.index_schema(db=db, force=False)
        logger.info(
            "Schema indexed into ChromaDB",
            indexed=result.get("indexed", 0),
            skipped=result.get("skipped", 0),
            total_chunks=result.get("total_chunks", 0),
        )
    except Exception as exc:
        logger.warning(
            "Schema indexing skipped on startup — ChromaDB or DB unavailable",
            error=str(exc),
        )

    # Start Kafka Consumer
    from app.services.kafka_service import KafkaService
    from app.db.session import AsyncSessionLocal
    kafka_svc = KafkaService()
    try:
        await kafka_svc.start_consumer(db_session_maker=AsyncSessionLocal)
    except Exception as exc:
        logger.warning("Kafka Consumer failed to start (is Kafka running?)", error=str(exc))

    # Start Mock Event Generator
    from app.services.mock_events import run_mock_event_generator
    import asyncio
    mock_task = asyncio.create_task(run_mock_event_generator())

    # ── APScheduler: Recurring KG sync ────────────────────────
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from app.services.kg_ingestion_service import KGIngestionService
    from app.db.session import AsyncSessionLocal as _ASESL

    async def _run_kg_sync():
        logger.info("APScheduler: Starting scheduled KG sync")
        async with _ASESL() as _db:
            svc = KGIngestionService()
            await svc.sync(_db)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _run_kg_sync,
        trigger="interval",
        minutes=settings.kg_sync_interval_minutes,
        id="kg_sync",
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started", interval_minutes=settings.kg_sync_interval_minutes)

    yield

    # ── Shutdown ──────────────────────────────────────────────
    logger.info("Shutting down Healthcare Copilot API")
    if kafka_svc and kafka_svc.consumer:
        try:
            await kafka_svc.consumer.stop()
        except Exception:
            pass
            
    if 'mock_task' in locals():
        mock_task.cancel()

    if 'scheduler' in locals():
        scheduler.shutdown(wait=False)

    from app.services.neo4j_driver import close_driver
    await close_driver()


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description=(
            "AI-powered natural language interface to healthcare data. "
            "Converts questions into SQL, executes them, and explains results."
        ),
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://healthcopilot.internal"] if not settings.app_debug else [],
        allow_origin_regex=r"http://localhost:\d+" if settings.app_debug else None,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Audit Logging ─────────────────────────────────────────
    from app.middleware.audit import AuditLogMiddleware
    app.add_middleware(AuditLogMiddleware)

    # ── Exception Handlers ────────────────────────────────────
    setup_exception_handlers(app)

    # ── Telemetry & Metrics ───────────────────────────────────
    from app.core.telemetry import setup_telemetry
    setup_telemetry(app)

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics")

    # ── Routers ───────────────────────────────────────────────
    app.include_router(api_router, prefix=settings.api_prefix)

    # ── System Endpoints ──────────────────────────────────────
    @app.get("/health", tags=["System"], summary="Health check")
    async def health_check() -> dict:
        return {
            "status": "healthy",
            "service": settings.app_name,
            "version": "1.0.0",
            "environment": settings.app_env,
        }

    return app


app = create_application()
