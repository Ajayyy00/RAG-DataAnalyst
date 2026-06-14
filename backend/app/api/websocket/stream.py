"""WebSocket streaming endpoint for long-running copilot queries."""

import asyncio
import json
import uuid
from datetime import datetime, timezone

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import get_settings
from app.core.security import verify_token
from app.db.session import AsyncSessionLocal
from app.services.chart_generation_service import ChartGenerationService
from app.services.conversation_history_service import ConversationHistoryService
from app.services.llm_explanation_service import LLMExplanationService
from app.services.query_execution_service import QueryExecutionService
from app.services.rag_service import RAGService
from app.services.sql_validation_service import SQLValidationService
from app.services.text_to_sql_service import TextToSQLService

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()


async def _send(ws: WebSocket, event: str, data: dict) -> None:
    """Helper to send a structured WebSocket event."""
    await ws.send_text(json.dumps({"event": event, "data": data}))


@router.websocket("/stream/{session_id}")
async def stream_query(ws: WebSocket, session_id: uuid.UUID) -> None:
    """Stream the full NL→SQL pipeline over a WebSocket connection."""
    await ws.accept()

    # ── Auth via token query param ────────────────────────────
    token = ws.query_params.get("token")
    if not token:
        await _send(ws, "error", {"message": "Missing authentication token"})
        await ws.close(code=4001)
        return

    payload = verify_token(token)
    if not payload:
        await _send(ws, "error", {"message": "Invalid or expired token"})
        await ws.close(code=4001)
        return

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            question = msg.get("question", "").strip()
            options = msg.get("options", {})

            if not question:
                await _send(ws, "error", {"message": "Question is required"})
                continue

            query_id = str(uuid.uuid4())

            async with AsyncSessionLocal() as db:
                redis = aioredis.from_url(settings.redis_url, decode_responses=True)
                try:
                    history_svc = ConversationHistoryService(db, redis)

                    # ── RAG ──────────────────────────────────
                    await _send(ws, "status", {"step": "retrieving_schema"})
                    rag = RAGService()
                    try:
                        schema_context = rag.retrieve_schema_context(question)
                    except Exception:
                        schema_context = ""

                    # ── NL→SQL ───────────────────────────────
                    await _send(ws, "status", {"step": "generating_sql"})
                    history = await history_svc.get_conversation_context(session_id)
                    async with TextToSQLService() as sql_svc:
                        sql = await sql_svc.generate_sql(
                            question, schema_context, history
                        )
                    await _send(ws, "sql_generated", {"sql": sql})

                    # ── Validation ───────────────────────────
                    validator = SQLValidationService()
                    is_valid, violations, normalized = validator.validate(sql)
                    await _send(
                        ws,
                        "sql_validated",
                        {"valid": is_valid, "violations": violations},
                    )

                    if not is_valid:
                        await _send(
                            ws,
                            "done",
                            {"query_id": query_id, "error": "Validation failed"},
                        )
                        continue

                    # ── Execution ────────────────────────────
                    await _send(ws, "status", {"step": "executing_query"})
                    executor = QueryExecutionService(db)
                    results = await executor.execute(
                        normalized, max_rows=options.get("max_rows", 500)
                    )
                    await _send(
                        ws,
                        "results_ready",
                        {
                            "columns": results["columns"],
                            "rows": results["rows"],
                            "row_count": results["row_count"],
                            "execution_ms": results["execution_ms"],
                        },
                    )

                    # ── Chart ────────────────────────────────
                    advisor = ChartGenerationService()
                    chart = advisor.recommend(results["columns"], results["rows"])
                    await _send(ws, "chart_ready", chart)

                    # ── Insights ─────────────────────────────
                    await _send(ws, "status", {"step": "generating_insights"})
                    async with LLMExplanationService() as insight_svc:
                        insights = await insight_svc.generate_insights(
                            question, normalized, results
                        )
                    await _send(ws, "insights_ready", {"insights": insights})

                    await _send(ws, "done", {"query_id": query_id})
                finally:
                    await redis.aclose()
                    await db.close()

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", session_id=str(session_id))
    except Exception as exc:
        logger.exception("WebSocket stream error", error=str(exc))
        try:
            await _send(ws, "error", {"message": str(exc)})
        except Exception:
            pass
