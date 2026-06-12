"""Fine-tuning feedback and dataset schemas."""

import uuid
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class FeedbackRequest(BaseModel):
    message_id: uuid.UUID
    is_correct: bool
    corrected_sql: Optional[str] = None
    difficulty: Optional[Literal["simple", "medium", "complex"]] = None
    query_type: Optional[str] = None


class NLSQLPairResponse(BaseModel):
    id: uuid.UUID
    nl_question: str
    generated_sql: str
    corrected_sql: Optional[str]
    is_validated: bool
    is_correct: Optional[bool]
    difficulty: Optional[str]
    query_type: Optional[str]
    split: str
    created_at: datetime

    model_config = {"from_attributes": True}


class FinetuneStatsResponse(BaseModel):
    total_pairs: int
    validated_pairs: int
    correct_pairs: int
    incorrect_pairs: int
    pending_review: int
    split_distribution: dict
    difficulty_distribution: dict


class ExportRequest(BaseModel):
    format: Literal["alpaca", "sharegpt", "jsonl"] = "alpaca"
    split: Optional[Literal["train", "val", "test"]] = None
    only_correct: bool = True
