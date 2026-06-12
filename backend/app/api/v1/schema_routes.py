"""Schema introspection routes: list tables, columns, trigger re-indexing."""

from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Query, status
from sqlalchemy import text

from app.dependencies import CurrentAdmin, CurrentUser, DbSession
from app.services.rag_service import RAGService

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.get(
    "/tables",
    response_model=List[str],
    summary="List all queryable tables",
)
async def list_tables(current_user: CurrentUser, db: DbSession) -> List[str]:
    result = await db.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
    )
    return [row[0] for row in result.fetchall()]


@router.get(
    "/tables/{table_name}",
    response_model=List[Dict[str, Any]],
    summary="Get column details for a specific table",
)
async def get_table_columns(
    table_name: str,
    current_user: CurrentUser,
    db: DbSession,
) -> List[Dict[str, Any]]:
    result = await db.execute(
        text(
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = :tname AND table_schema = 'public' "
            "ORDER BY ordinal_position"
        ),
        {"tname": table_name},
    )
    rows = result.fetchall()
    return [
        {
            "column_name": r[0],
            "data_type": r[1],
            "is_nullable": r[2],
            "column_default": r[3],
        }
        for r in rows
    ]


@router.post(
    "/reindex",
    summary="Trigger schema re-indexing into ChromaDB (admin only)",
    status_code=status.HTTP_202_ACCEPTED,
)
async def reindex_schema(current_admin: CurrentAdmin) -> Dict[str, Any]:
    rag = RAGService()
    chunk_count = await rag.index_schema()
    return {"status": "reindexed", "chunks_indexed": chunk_count}


@router.get(
    "/search",
    response_model=List[str],
    summary="Semantic search over indexed schema chunks",
)
async def search_schema(
    q: str = Query(min_length=3),
    top_k: int = Query(default=5, le=20),
    current_user: CurrentUser = None,
) -> List[str]:
    rag = RAGService()
    context = rag.retrieve_schema_context(q, top_k=top_k)
    return context.split("\n\n") if context else []
