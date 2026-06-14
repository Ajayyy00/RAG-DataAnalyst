"""
app/api/v1/rag.py
==================
RAG pipeline admin & debug endpoints.

Routes:
  POST /rag/index            — Trigger full or incremental schema re-indexing
  GET  /rag/health           — ChromaDB connection + collection stats
  GET  /rag/search           — Semantic search debug (shows raw chunk results)
  GET  /rag/context          — Show the full context string for a test question
  GET  /rag/schema/{table}   — Rich schema info for one table (extracted live)
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Query
from fastapi import status as http_status

from app.dependencies import CurrentAdmin, CurrentUser, DbSession
from app.services.rag_service import RAGService
from app.services.schema_extractor import SchemaExtractor

log = structlog.get_logger(__name__)
router = APIRouter()


# ── POST /rag/index ─────────────────────────────────────────────────────────────
@router.post(
    "/index",
    summary="Trigger schema re-indexing into ChromaDB",
    status_code=http_status.HTTP_202_ACCEPTED,
    tags=["RAG"],
)
async def index_schema(
    force: bool = Query(
        default=False, description="Re-index all tables even if unchanged"
    ),
    _admin: CurrentAdmin = None,
    db: DbSession = None,
) -> dict[str, Any]:
    """
    Extract the current PostgreSQL schema and upsert embeddings into ChromaDB.

    Uses hash-based change detection — only tables whose column signatures have
    changed are re-embedded (unless ``force=true``).
    """
    rag = RAGService()
    result = await rag.index_schema(db=db, force=force)
    return {
        "status": "ok",
        "indexed_tables": result.get("indexed_tables", []),
        "skipped_tables": result.get("skipped_tables", []),
        "total_chunks": result.get("total_chunks", 0),
        "indexed": result.get("indexed", 0),
        "skipped": result.get("skipped", 0),
        "error": result.get("error"),
    }


# ── GET /rag/health ─────────────────────────────────────────────────────────────
@router.get(
    "/health",
    summary="ChromaDB connection health and collection stats",
    tags=["RAG"],
)
async def rag_health(_user: CurrentUser) -> dict[str, Any]:
    """
    Check ChromaDB connectivity and return the total number of indexed chunks.
    """
    rag = RAGService()
    stats = rag.collection_stats()
    return stats


# ── GET /rag/search ─────────────────────────────────────────────────────────────
@router.get(
    "/search",
    summary="Raw semantic search over schema chunks (debug)",
    tags=["RAG"],
)
async def search_chunks(
    q: str = Query(min_length=3, description="Natural language question"),
    n: int = Query(default=10, le=30, description="Number of raw results"),
    _user: CurrentUser = None,
) -> list[dict[str, Any]]:
    """
    Returns raw ChromaDB retrieval results: chunk type, table, distance score, and
    a text preview. Used to evaluate retrieval quality during development.

    Lower distance = higher similarity.
    """
    rag = RAGService()
    return rag.search_debug(q, n=n)


# ── GET /rag/context ─────────────────────────────────────────────────────────────
@router.get(
    "/context",
    summary="Show the full LLM schema context for a test question",
    tags=["RAG"],
)
async def get_context(
    q: str = Query(min_length=3, description="Natural language question"),
    top_k: int = Query(default=5, le=15),
    _user: CurrentUser = None,
) -> dict[str, Any]:
    """
    Returns the complete schema context string that would be injected into the
    LLM system prompt for a given question.

    Useful for:
    - Verifying the RAG pipeline retrieves the right tables
    - Inspecting the DDL and JOIN hints included in context
    - Debugging SQL generation quality
    """
    rag = RAGService()
    retrieved, context = await rag.retrieve(q, top_k=top_k)
    return {
        "question": q,
        "retrieved_tables": [
            {
                "table": r.name,
                "distance": round(r.score, 4),
                "chunks_matched": r.chunks_matched,
                "related_tables": r.related_tables,
            }
            for r in retrieved
        ],
        "context_length_chars": len(context),
        "context": context,
    }


# ── GET /rag/schema/{table} ──────────────────────────────────────────────────────
@router.get(
    "/schema/{table_name}",
    summary="Live schema metadata for a single table",
    tags=["RAG"],
)
async def get_table_schema(
    table_name: str,
    db: DbSession = None,
    _user: CurrentUser = None,
) -> dict[str, Any]:
    """
    Extract and return rich schema metadata for one table directly from PostgreSQL.
    Includes columns, types, PKs, FKs, row count, indexes, and comments.
    """
    extractor = SchemaExtractor(db)
    tables = await extractor.extract_all()
    table = next((t for t in tables if t.name == table_name), None)

    if table is None:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=f"Table '{table_name}' not found in schema.",
        )

    return {
        "name": table.name,
        "schema": table.schema_name,
        "row_count": table.row_count,
        "comment": table.comment,
        "schema_hash": table.schema_hash(),
        "related_tables": table.related_tables,
        "indexes": table.indexes,
        "columns": [
            {
                "name": c.name,
                "data_type": c.data_type,
                "nullable": c.nullable,
                "default": c.default,
                "is_primary_key": c.is_primary_key,
                "is_foreign_key": c.is_foreign_key,
                "fk_table": c.fk_table,
                "fk_column": c.fk_column,
                "comment": c.effective_comment,
                "ordinal": c.ordinal,
            }
            for c in table.columns
        ],
        "ddl": table.to_ddl(),
        "description": table.to_description(),
    }
