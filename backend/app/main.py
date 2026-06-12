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

    yield

    # ── Shutdown ──────────────────────────────────────────────
    logger.info("Shutting down Healthcare Copilot API")


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
        allow_origins=["*"] if settings.app_debug else ["https://healthcopilot.internal"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Exception Handlers ────────────────────────────────────
    setup_exception_handlers(app)

    # ── Prometheus Metrics ────────────────────────────────────
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
