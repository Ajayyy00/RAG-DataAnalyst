"""Chat query request and response schemas."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.schemas.sql_explanation import SQLExplanation


class QueryOptions(BaseModel):
    include_sql: bool = True
    include_insights: bool = True
    max_rows: int = Field(default=500, le=10000)
    chart_auto: bool = True


class ChatQueryRequest(BaseModel):
    session_id: Optional[uuid.UUID] = None
    question: str = Field(min_length=5, max_length=2000)
    options: QueryOptions = Field(default_factory=QueryOptions)


class SQLResult(BaseModel):
    generated: str
    validated: bool
    validation_notes: List[str] = []
    optimizations: List[str] = []
    execution_plan: Optional[Dict[str, Any]] = None
    explanation: Optional[SQLExplanation] = None


class QueryResultData(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    execution_ms: int


class ChartConfig(BaseModel):
    type: str  # bar | line | pie | scatter | area | heatmap | table
    x_key: Optional[str] = None
    y_key: Optional[str] = None
    title: str = ""
    color: str = "#3B82F6"
    multi_series: bool = False
    series_keys: List[str] = []
    config: Dict[str, Any] = {}


# ── Rich Insights Schema ──────────────────────────────────────


class Recommendation(BaseModel):
    """A single actionable recommendation with priority context."""

    priority: str  # "high" | "medium" | "low"
    action: str  # Short imperative action
    rationale: str  # Why this matters clinically / operationally
    metric: Optional[str] = None  # Relevant KPI or data point


class InsightReport(BaseModel):
    """Structured AI insight report returned for every query."""

    summary: str  # 1-2 sentence plain-English summary
    trends: List[str] = []  # Key trends observed in the data
    anomalies: List[str] = []  # Outliers / unexpected values
    recommendations: List[Recommendation] = []
    follow_up_questions: List[str] = []  # Suggested next questions
    data_quality_notes: List[str] = []  # Missing data, coverage gaps, etc.
    confidence: str = "medium"  # "high" | "medium" | "low"


# ── API Models ────────────────────────────────────────────────


class QueryMeta(BaseModel):
    model: str
    schema_chunks_used: int
    created_at: datetime
    query_id: uuid.UUID


class ChatQueryResponse(BaseModel):
    query_id: uuid.UUID
    session_id: uuid.UUID
    question: str
    sql: Optional[SQLResult] = None
    results: Optional[QueryResultData] = None
    chart: Optional[ChartConfig] = None
    insights: List[str] = []  # legacy flat list (backward compat)
    insight_report: Optional[InsightReport] = None  # rich structured output
    metadata: QueryMeta


class SQLValidateRequest(BaseModel):
    sql: str


class SQLValidateResponse(BaseModel):
    valid: bool
    violations: List[str] = []
    normalized_sql: Optional[str] = None
