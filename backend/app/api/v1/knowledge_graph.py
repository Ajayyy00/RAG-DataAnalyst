from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.dependencies import CurrentUser, DbSession
from app.services.graph_reasoning_service import GraphReasoningService
from app.services.kg_ingestion_service import KGIngestionService

router = APIRouter()


class KGQueryRequest(BaseModel):
    question: str


class KGQueryResponse(BaseModel):
    question: str
    cypher: str
    graph_data: Any
    answer: str
    error: Optional[str] = None


@router.post(
    "/sync",
    summary="Trigger Knowledge Graph ETL sync (Postgres → Neo4j)",
)
async def trigger_sync(
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
):
    """
    Runs the KG ingestion pipeline as a background task.
    LLM dynamically extracts Disease→Symptom and Medication→Disease relationships.
    """
    from app.db.session import AsyncSessionLocal

    async def _bg_sync():
        async with AsyncSessionLocal() as fresh_db:
            await KGIngestionService().sync(fresh_db)

    background_tasks.add_task(_bg_sync)
    return {
        "status": "sync_started",
        "message": "Knowledge Graph sync triggered in background.",
    }


@router.post(
    "/query",
    response_model=KGQueryResponse,
    summary="Ask a multi-hop question answered by the Knowledge Graph",
)
async def knowledge_graph_query(
    request: KGQueryRequest,
    current_user: CurrentUser,
) -> KGQueryResponse:
    """
    Translates a natural language question into a Cypher query,
    executes it against Neo4j, and returns an LLM-reasoned answer.
    """
    reasoning_svc = GraphReasoningService()
    result = await reasoning_svc.query(request.question)
    return KGQueryResponse(**result)


@router.get(
    "/stats",
    summary="Return basic node and relationship counts from the Knowledge Graph",
)
async def graph_stats(
    current_user: CurrentUser,
) -> Dict[str, Any]:
    from app.services.neo4j_driver import run_query

    try:
        # Count each node label individually (no APOC needed)
        labels = ["Patient", "Disease", "Symptom", "Medication", "LabTest"]
        counts = {}
        for label in labels:
            result = await run_query(f"MATCH (n:{label}) RETURN count(n) AS count")
            counts[label] = result[0]["count"] if result else 0

        rels = await run_query(
            "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) AS count"
        )
        rel_counts = {r["rel"]: r["count"] for r in rels}

        return {"labels": counts, "relTypesCount": rel_counts, "neo4j_available": True}
    except Exception as e:
        # Neo4j is offline — return zeros so the UI can still render gracefully
        return {
            "labels": {
                "Patient": 0,
                "Disease": 0,
                "Symptom": 0,
                "Medication": 0,
                "LabTest": 0,
            },
            "relTypesCount": {},
            "neo4j_available": False,
            "message": "Neo4j is offline. Start Neo4j at bolt://localhost:7687 to enable the knowledge graph.",
        }
