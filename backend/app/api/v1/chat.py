"""Chat query routes: main NL→SQL pipeline and SQL validation."""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, status

from app.core.exceptions import QueryExecutionError, SQLValidationError
from app.dependencies import CurrentUser, DbSession, RedisClient
from app.schemas.chat import (
    ChatQueryRequest,
    ChatQueryResponse,
    ChartConfig,
    InsightReport,
    QueryMeta,
    QueryResultData,
    SQLResult,
    SQLValidateRequest,
    SQLValidateResponse,
)
from app.services.chart_generation_service import ChartGenerationService
from app.services.conversation_history_service import ConversationHistoryService
from app.services.insights_engine import InsightsEngine
from app.services.query_execution_service import QueryExecutionService
from app.services.rag_service import RAGService
from app.services.sql_validation_service import SQLValidationService
from app.services.text_to_sql_service import TextToSQLService
from app.config import get_settings

logger = structlog.get_logger(__name__)
router = APIRouter()
settings = get_settings()


@router.post(
    "/query",
    response_model=ChatQueryResponse,
    summary="Convert a natural language question into SQL, execute it, and return insights",
)
async def chat_query(
    request: ChatQueryRequest,
    current_user: CurrentUser,
    db: DbSession,
    redis: RedisClient,
) -> ChatQueryResponse:
    """Main pipeline: NL → RAG → SQL → Validation → Execution → Chart → Insights."""
    query_id = uuid.uuid4()
    history_svc = ConversationHistoryService(db, redis)

    # ── 1. Session resolution ─────────────────────────────────
    if request.session_id:
        session = await history_svc.get_session(request.session_id, current_user.id)
    else:
        session = await history_svc.create_session(
            current_user.id,
            title=request.question[:80],
        )

    # ── 2. Save user message ──────────────────────────────────
    await history_svc.save_message(
        session_id=session.id,
        role="user",
        content=request.question,
    )

    # ── 3. Retrieve schema context (RAG) ──────────────────────
    rag_svc = RAGService()
    try:
        retrieved_tables, schema_context = rag_svc.retrieve(
            question=request.question,
            top_k=settings.rag_top_k,
        )
        schema_chunks_used = len(retrieved_tables)
        logger.info(
            "RAG retrieval complete",
            tables=[r.name for r in retrieved_tables],
            question_preview=request.question[:60],
        )
    except Exception as exc:
        logger.warning("RAG retrieval failed — using empty context", error=str(exc))
        schema_context = ""
        schema_chunks_used = 0

    # ── 4. Conversation history ───────────────────────────────
    conversation_history = await history_svc.get_conversation_context(session.id)

    # ── 5. NL → SQL ─────────────────────────────────────────
    async with TextToSQLService() as sql_svc:
        generated_sql = await sql_svc.generate_sql(
            question=request.question,
            schema_context=schema_context,
            conversation_history=conversation_history,
        )

    # ── 6. SQL Validation ─────────────────────────────────────
    validator = SQLValidationService()
    validation = validator.validate(generated_sql)
    is_valid = validation.is_valid
    violations = validation.violations
    normalized_sql = validation.normalized_sql

    sql_result = SQLResult(
        generated=generated_sql,
        validated=is_valid,
        validation_notes=violations,
    )

    if not is_valid:
        # Save assistant failure message and return early
        await history_svc.save_message(
            session_id=session.id,
            role="assistant",
            content=f"SQL validation failed: {'; '.join(violations)}",
            generated_sql=generated_sql,
            sql_valid=False,
        )
        return ChatQueryResponse(
            query_id=query_id,
            session_id=session.id,
            question=request.question,
            sql=sql_result,
            insights=["The generated SQL did not pass safety validation. Please rephrase your question."],
            metadata=QueryMeta(
                model=settings.llm_model,
                schema_chunks_used=schema_chunks_used,
                created_at=datetime.now(timezone.utc),
                query_id=query_id,
            ),
        )

    # ── 7. Query Execution ────────────────────────────────────
    executor = QueryExecutionService(db)
    result_data = await executor.execute(normalized_sql, max_rows=request.options.max_rows)

    query_result = QueryResultData(
        columns=result_data["columns"],
        rows=result_data["rows"],
        row_count=result_data["row_count"],
        execution_ms=result_data["execution_ms"],
    )

    # ── 8. Chart Advisor ──────────────────────────────────────
    chart_config_dict = None
    chart_type = None
    if request.options.chart_auto:
        advisor = ChartGenerationService()
        chart_config_dict = advisor.recommend(
            columns=result_data["columns"],
            rows=result_data["rows"],
        )
        chart_type = chart_config_dict.get("type")

    # ── 9. AI Insights Engine ────────────────────────────────
    insight_report: InsightReport | None = None
    insights: list = []
    if request.options.include_insights:
        engine = InsightsEngine()
        insight_report = await engine.generate(
            question=request.question,
            sql=normalized_sql,
            columns=result_data["columns"],
            rows=result_data["rows"],
        )
        insights = engine.to_flat_list(insight_report)

    # ── 10. Save assistant message ────────────────────────────
    summary = f"Returned {result_data['row_count']} rows in {result_data['execution_ms']}ms."
    await history_svc.save_message(
        session_id=session.id,
        role="assistant",
        content=summary,
        generated_sql=normalized_sql,
        sql_valid=True,
        execution_ms=result_data["execution_ms"],
        row_count=result_data["row_count"],
        chart_type=chart_type,
    )

    # ── 11. Assemble response ─────────────────────────────────
    chart = None
    if chart_config_dict:
        chart = ChartConfig(
            type=chart_config_dict["type"],
            x_key=chart_config_dict.get("x_key"),
            y_key=chart_config_dict.get("y_key"),
            title=chart_config_dict.get("title", ""),
            color=chart_config_dict.get("color", "#3B82F6"),
            multi_series=chart_config_dict.get("multi_series", False),
            series_keys=chart_config_dict.get("series_keys", []),
            config=chart_config_dict.get("config", {}),
        )

    return ChatQueryResponse(
        query_id=query_id,
        session_id=session.id,
        question=request.question,
        sql=sql_result if request.options.include_sql else None,
        results=query_result,
        chart=chart,
        insights=insights,
        insight_report=insight_report,
        metadata=QueryMeta(
            model=settings.llm_model,
            schema_chunks_used=schema_chunks_used,
            created_at=datetime.now(timezone.utc),
            query_id=query_id,
        ),
    )


@router.post(
    "/validate",
    response_model=SQLValidateResponse,
    summary="Validate a SQL query without executing it",
)
async def validate_sql(
    request: SQLValidateRequest,
    current_user: CurrentUser,
) -> SQLValidateResponse:
    validator = SQLValidationService()
    result = validator.validate(request.sql)
    return SQLValidateResponse(
        valid=result.is_valid,
        violations=result.violations,
        normalized_sql=result.normalized_sql if result.is_valid else None,
    )
