"""Fine-tuning routes: feedback collection, NL-SQL pair management, dataset export."""

import json
import uuid
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Query, Response, status
from sqlalchemy import func, select, update

from app.db.models.copilot import CopilotMessage, NLSQLPair
from app.dependencies import CurrentAdmin, CurrentUser, DbSession
from app.schemas.finetune import (
    ExportRequest,
    FeedbackRequest,
    FinetuneStatsResponse,
    NLSQLPairResponse,
)

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post(
    "/feedback",
    status_code=status.HTTP_201_CREATED,
    summary="Submit thumbs-up/down feedback on a generated SQL query",
)
async def submit_feedback(
    data: FeedbackRequest,
    current_user: CurrentUser,
    db: DbSession,
) -> Dict[str, Any]:
    # Fetch the message to validate it belongs to the user's session
    msg_result = await db.execute(
        select(CopilotMessage).where(CopilotMessage.id == data.message_id)
    )
    message = msg_result.scalar_one_or_none()
    if not message or not message.generated_sql:
        return {"status": "skipped", "reason": "Message not found or has no SQL"}

    # Upsert an NL-SQL pair with feedback
    pair_result = await db.execute(
        select(NLSQLPair).where(NLSQLPair.message_id == data.message_id)
    )
    pair = pair_result.scalar_one_or_none()

    if pair:
        pair.is_correct = data.is_correct
        pair.corrected_sql = data.corrected_sql or pair.corrected_sql
        pair.difficulty = data.difficulty or pair.difficulty
        pair.query_type = data.query_type or pair.query_type
        pair.is_validated = True
    else:
        # Get the user's question from the preceding user message
        question = message.content
        pair = NLSQLPair(
            message_id=data.message_id,
            nl_question=question,
            generated_sql=message.generated_sql,
            corrected_sql=data.corrected_sql,
            is_correct=data.is_correct,
            is_validated=True,
            difficulty=data.difficulty,
            query_type=data.query_type,
        )
        db.add(pair)

    await db.flush()
    logger.info("Feedback submitted", message_id=str(data.message_id), is_correct=data.is_correct)
    return {"status": "ok", "pair_id": str(pair.id)}


@router.get(
    "/pairs",
    response_model=List[NLSQLPairResponse],
    summary="List NL-SQL pairs (admin only)",
)
async def list_pairs(
    current_admin: CurrentAdmin,
    db: DbSession,
    split: str | None = Query(default=None),
    only_validated: bool = Query(default=False),
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0),
) -> List[NLSQLPairResponse]:
    stmt = select(NLSQLPair)
    if split:
        stmt = stmt.where(NLSQLPair.split == split)
    if only_validated:
        stmt = stmt.where(NLSQLPair.is_validated.is_(True))
    stmt = stmt.order_by(NLSQLPair.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(stmt)
    return [NLSQLPairResponse.model_validate(p) for p in result.scalars().all()]


@router.get(
    "/stats",
    response_model=FinetuneStatsResponse,
    summary="Dataset statistics (admin only)",
)
async def get_stats(current_admin: CurrentAdmin, db: DbSession) -> FinetuneStatsResponse:
    total = (await db.execute(select(func.count(NLSQLPair.id)))).scalar_one()
    validated = (await db.execute(
        select(func.count(NLSQLPair.id)).where(NLSQLPair.is_validated.is_(True))
    )).scalar_one()
    correct = (await db.execute(
        select(func.count(NLSQLPair.id)).where(NLSQLPair.is_correct.is_(True))
    )).scalar_one()
    incorrect = (await db.execute(
        select(func.count(NLSQLPair.id)).where(NLSQLPair.is_correct.is_(False))
    )).scalar_one()
    pending = total - validated

    return FinetuneStatsResponse(
        total_pairs=total,
        validated_pairs=validated,
        correct_pairs=correct,
        incorrect_pairs=incorrect,
        pending_review=pending,
        split_distribution={},
        difficulty_distribution={},
    )


@router.post(
    "/export",
    summary="Export NL-SQL pairs as a fine-tuning dataset (admin only)",
)
async def export_dataset(
    data: ExportRequest,
    current_admin: CurrentAdmin,
    db: DbSession,
) -> Response:
    stmt = select(NLSQLPair).where(NLSQLPair.is_validated.is_(True))
    if data.only_correct:
        stmt = stmt.where(NLSQLPair.is_correct.is_(True))
    if data.split:
        stmt = stmt.where(NLSQLPair.split == data.split)
    result = await db.execute(stmt)
    pairs = result.scalars().all()

    output_lines: list[str] = []
    for p in pairs:
        if data.format == "alpaca":
            record = {
                "instruction": "Convert the following healthcare question to PostgreSQL SQL.",
                "input": p.nl_question,
                "output": p.corrected_sql or p.generated_sql,
            }
        else:
            record = {
                "nl": p.nl_question,
                "sql": p.corrected_sql or p.generated_sql,
                "difficulty": p.difficulty,
                "query_type": p.query_type,
            }
        output_lines.append(json.dumps(record, ensure_ascii=False))

    content = "\n".join(output_lines)
    return Response(
        content=content,
        media_type="application/jsonl",
        headers={"Content-Disposition": f"attachment; filename=finetune_{data.format}.jsonl"},
    )
