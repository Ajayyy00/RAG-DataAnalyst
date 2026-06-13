"""
Dashboard Generation Engine
============================
Converts a single natural-language request into a multi-panel, AI-curated
dashboard containing SQL queries, data, charts, and an executive summary.

Pipeline
--------
  1. QueryPlanner      – LLM decomposes the request into 3-5 focused sub-queries
  2. Parallel Executor – runs each sub-query through the full NL→SQL→data pipeline
  3. LayoutEngine      – assigns panel sizes and grid positions based on chart types
  4. SummaryComposer   – LLM writes a cohesive executive summary across all panels
  5. FallbackPlanner   – rule-based panel plan when LLM is unavailable
"""

from __future__ import annotations

import asyncio
import json
import re
import textwrap
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import structlog
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.schemas.dashboard import (
    DashboardPanel, DashboardLayout, DashboardResponse, PanelSize, DashboardFilter
)
from sqlalchemy import text
from app.services.chart_generation_service import ChartGenerationService
from app.services.insights_engine import InsightsEngine
from app.services.query_execution_service import QueryExecutionService
from app.services.rag_service import RAGService
from app.services.sql_validation_service import SQLValidationService
from app.services.text_to_sql_service import TextToSQLService
from app.services.schema_extractor import SchemaExtractor

logger = structlog.get_logger(__name__)
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# Chart type → grid span mapping
# ─────────────────────────────────────────────────────────────────────────────
CHART_SPANS: Dict[str, PanelSize] = {
    "kpi":     PanelSize(col_span=1, row_span=1),
    "pie":     PanelSize(col_span=1, row_span=2),
    "bar":     PanelSize(col_span=2, row_span=2),
    "line":    PanelSize(col_span=2, row_span=2),
    "area":    PanelSize(col_span=2, row_span=2),
    "scatter": PanelSize(col_span=2, row_span=2),
    "heatmap": PanelSize(col_span=3, row_span=2),
    "table":   PanelSize(col_span=3, row_span=2),
}
DEFAULT_SPAN = PanelSize(col_span=2, row_span=2)

GRID_COLS = 6  # total grid columns (CSS grid)

# ─────────────────────────────────────────────────────────────────────────────
# Query Planner — LLM decomposes request into 3-5 targeted sub-queries
# ─────────────────────────────────────────────────────────────────────────────

PLANNER_SYSTEM = textwrap.dedent("""\
You are a healthcare data analyst decomposing a dashboard request into specific
analytical sub-questions that together provide a comprehensive view of the topic.

Rules:
- Generate 3 to 5 focused sub-questions.
- Each must be answerable by a single SQL query on a healthcare database.
- Vary the analytical angles: trends over time, breakdowns by category, KPIs, comparisons.
- Make sub-questions concrete and specific (e.g. "last 90 days", "by department").
- Suggest the best chart type for each: line, bar, pie, scatter, heatmap, kpi, table.

Available data: patients, encounters, diagnoses, procedures, medications,
lab_results, vital_signs, claims, readmissions, providers, departments, facilities.

Respond ONLY with a valid JSON array, no markdown fences:
[
  {"title": "<panel title>", "question": "<specific sub-question>", "chart_hint": "<chart type>"},
  ...
]
""")


class QueryPlanner:
    """Uses the LLM to decompose a dashboard request into sub-queries."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "QueryPlanner":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(min=1, max=5),
        reraise=True,
    )
    async def plan(self, request: str) -> List[Dict[str, str]]:
        """Return list of {title, question, chart_hint} dicts."""
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": PLANNER_SYSTEM},
                {"role": "user",   "content": f"Dashboard request: {request}"},
            ],
            "max_tokens": 800,
            "temperature": 0.2,
            "stream": False,
        }
        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()

        # Strip markdown fences if any
        raw = re.sub(r"```(?:json)?\s*|\s*```", "", raw).strip()
        items = json.loads(raw)

        return [
            {
                "title":      str(item.get("title", f"Panel {i+1}")),
                "question":   str(item.get("question", request)),
                "chart_hint": str(item.get("chart_hint", "bar")).lower(),
            }
            for i, item in enumerate(items)
            if isinstance(item, dict)
        ][:5]  # max 5 panels


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Planner — rule-based when LLM is unavailable
# ─────────────────────────────────────────────────────────────────────────────

_TOPIC_PANELS: Dict[str, List[Dict[str, str]]] = {
    "admission": [
        {"title": "Monthly Admissions Trend", "question": "Total hospital admissions per month last 12 months", "chart_hint": "line"},
        {"title": "Admissions by Department",  "question": "Total admissions by department last 90 days", "chart_hint": "bar"},
        {"title": "Admission Type Breakdown",  "question": "Breakdown of inpatient vs outpatient vs emergency encounters", "chart_hint": "pie"},
        {"title": "Avg Length of Stay",        "question": "Average length of stay by department", "chart_hint": "bar"},
    ],
    "readmission": [
        {"title": "30-day Readmission Trend",  "question": "Monthly 30-day readmission count last 12 months", "chart_hint": "line"},
        {"title": "Readmissions by Dept",      "question": "30-day readmission count by department", "chart_hint": "bar"},
        {"title": "Top Readmission Diagnoses", "question": "Top 5 diagnoses associated with readmissions", "chart_hint": "bar"},
    ],
    "diagnosis": [
        {"title": "Top Diagnoses",             "question": "Top 10 diagnoses by frequency this quarter", "chart_hint": "bar"},
        {"title": "Diagnoses by Dept",         "question": "Top diagnoses per department", "chart_hint": "table"},
        {"title": "Diagnosis Trend",           "question": "Monthly diagnosis count last 6 months", "chart_hint": "line"},
    ],
    "medication": [
        {"title": "Most Prescribed Meds",      "question": "Top 10 most prescribed medications", "chart_hint": "bar"},
        {"title": "Medication Trend",          "question": "Monthly medication orders last 6 months", "chart_hint": "line"},
        {"title": "Meds by Department",        "question": "Medication counts by department", "chart_hint": "pie"},
    ],
    "lab": [
        {"title": "Lab Test Volume",           "question": "Total lab tests per month last 6 months", "chart_hint": "line"},
        {"title": "Abnormal Lab Results",      "question": "Count of abnormal lab results by test type", "chart_hint": "bar"},
        {"title": "Lab Results by Dept",       "question": "Lab test counts by department", "chart_hint": "bar"},
    ],
    "default": [
        {"title": "Encounter Trends",          "question": "Monthly encounter count last 12 months", "chart_hint": "line"},
        {"title": "Encounters by Department",  "question": "Total encounters by department last 90 days", "chart_hint": "bar"},
        {"title": "Patient Demographics",      "question": "Patient count by gender", "chart_hint": "pie"},
        {"title": "Encounter Types",           "question": "Breakdown of encounter types", "chart_hint": "pie"},
    ],
}


class FallbackPlanner:
    def plan(self, request: str) -> List[Dict[str, str]]:
        req_lower = request.lower()
        for keyword, panels in _TOPIC_PANELS.items():
            if keyword != "default" and keyword in req_lower:
                return panels
        return _TOPIC_PANELS["default"]


# ─────────────────────────────────────────────────────────────────────────────
# Layout Engine — assigns grid positions to panels
# ─────────────────────────────────────────────────────────────────────────────

class LayoutEngine:
    """Assigns col/row positions using a simple packing algorithm."""

    def assign_positions(self, panels: List[DashboardPanel]) -> List[DashboardPanel]:
        col = 1
        row = 1
        max_row_height = 1

        for panel in panels:
            span = panel.size
            if col + span.col_span - 1 > GRID_COLS:
                # Wrap to next row
                row += max_row_height
                col = 1
                max_row_height = 1

            panel.col_start = col
            panel.row_start = row
            col += span.col_span
            max_row_height = max(max_row_height, span.row_span)

        return panels


# ─────────────────────────────────────────────────────────────────────────────
# Summary Composer — writes an executive-level summary
# ─────────────────────────────────────────────────────────────────────────────

SUMMARY_SYSTEM = textwrap.dedent("""\
You are a senior clinical analyst writing a concise executive summary for a
healthcare dashboard. Based on the panel descriptions provided, write 2-3 sentences
that highlight the most important findings, trends, or concerns.
Be specific, cite numbers where given, and focus on clinical/operational impact.
Respond with plain text only — no bullet points, no markdown.
""")


class SummaryComposer:
    async def compose(
        self, request: str, panels: List[DashboardPanel], client: httpx.AsyncClient
    ) -> str:
        panel_descriptions = "\n".join(
            f"- {p.title}: {p.insight_summary or p.subtitle or 'No data'}"
            for p in panels
        )
        user_msg = (
            f"Dashboard topic: {request}\n\n"
            f"Panel findings:\n{panel_descriptions}\n\n"
            "Write the executive summary now."
        )
        try:
            resp = await client.post("/chat/completions", json={
                "model":       settings.llm_model,
                "messages": [
                    {"role": "system", "content": SUMMARY_SYSTEM},
                    {"role": "user",   "content": user_msg},
                ],
                "max_tokens":  250,
                "temperature": 0.3,
                "stream":      False,
            })
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            logger.warning("Summary composition failed", error=str(exc))
            non_empty = [p for p in panels if p.row_count and p.row_count > 0]
            return (
                f"Dashboard for '{request}' generated with {len(panels)} panels. "
                f"{len(non_empty)} panels returned data. "
                "Review individual panels for detailed findings."
            )


# ─────────────────────────────────────────────────────────────────────────────
# Panel Executor — runs one sub-query through the full pipeline
# ─────────────────────────────────────────────────────────────────────────────

async def _execute_panel(
    plan_item: Dict[str, str],
    panel_index: int,
    db,
    redis,
) -> DashboardPanel:
    """Run a single sub-query through NL→SQL→Chart→Insight pipeline."""
    panel_id   = str(uuid.uuid4())
    title      = plan_item["title"]
    question   = plan_item["question"]
    chart_hint = plan_item.get("chart_hint", "bar")

    # ── 1. RAG schema retrieval ───────────────────────────────
    try:
        rag = RAGService()
        retrieved_tables, schema_context = rag.retrieve(question=question, top_k=5)
    except Exception:
        schema_context = ""

    # ── 2. NL → SQL ───────────────────────────────────────────
    try:
        async with TextToSQLService() as svc:
            sql = await svc.generate_sql(
                question=question,
                schema_context=schema_context,
                conversation_history=[],
            )
    except Exception as exc:
        logger.warning("SQL generation failed for panel", title=title, error=str(exc))
        return DashboardPanel(
            id=panel_id, title=title, subtitle=question,
            error=f"SQL generation failed: {exc}",
            size=CHART_SPANS.get(chart_hint, DEFAULT_SPAN),
        )

    # ── 3. Validation ─────────────────────────────────────────
    validator = SQLValidationService()
    validation = validator.validate(sql)
    if not validation.is_valid:
        return DashboardPanel(
            id=panel_id, title=title, subtitle=question,
            sql=sql, error=f"Validation: {'; '.join(validation.violations[:2])}",
            size=CHART_SPANS.get(chart_hint, DEFAULT_SPAN),
        )

    # ── 4. Query Execution ────────────────────────────────────
    try:
        executor = QueryExecutionService(db)
        result = await executor.execute(validation.normalized_sql, max_rows=200)
        columns: List[str] = result["columns"]
        rows: List[List[Any]] = result["rows"]
        row_count: int = result["row_count"]
    except Exception as exc:
        logger.warning("Query execution failed for panel", title=title, error=str(exc))
        return DashboardPanel(
            id=panel_id, title=title, subtitle=question,
            sql=validation.normalized_sql, error=str(exc),
            size=CHART_SPANS.get(chart_hint, DEFAULT_SPAN),
        )

    # ── 5. Chart selection ────────────────────────────────────
    advisor = ChartGenerationService()
    chart_config = advisor.recommend(columns=columns, rows=rows)

    # Honour the planner's chart hint if the advisor disagrees
    chart_type = chart_config.get("type", chart_hint)
    if chart_hint in {"line", "bar", "pie", "scatter", "heatmap"} and chart_type != chart_hint:
        chart_type = chart_hint
        chart_config["type"] = chart_hint

    # ── 6. Transform rows → objects for Recharts ──────────────
    chart_data = [
        {columns[i]: (float(v) if isinstance(v, str) and _is_numeric(v) else v)
         for i, v in enumerate(row) if i < len(columns)}
        for row in rows
    ]

    # ── 7. Insight summary (fast — uses fallback engine) ──────
    insight_summary = ""
    if rows:
        fallback = InsightsEngine()
        try:
            report = await fallback.generate(question, validation.normalized_sql, columns, rows)
            insight_summary = report.summary
        except Exception:
            pass

    # ── 8. Determine panel size ───────────────────────────────
    size = CHART_SPANS.get(chart_type, DEFAULT_SPAN)

    return DashboardPanel(
        id=panel_id,
        title=title,
        subtitle=question,
        sql=validation.normalized_sql,
        columns=columns,
        rows=rows,
        row_count=row_count,
        chart_type=chart_type,
        chart_data=chart_data,
        x_key=chart_config.get("x_key"),
        y_key=chart_config.get("y_key"),
        series_keys=chart_config.get("series_keys", []),
        insight_summary=insight_summary,
        size=size,
    )


def _is_numeric(s: str) -> bool:
    try:
        float(s.replace(",", ""))
        return True
    except (ValueError, TypeError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Filter Planner — LLM determines global filters for the dashboard
# ─────────────────────────────────────────────────────────────────────────────

FILTER_PLANNER_SYSTEM = textwrap.dedent("""\
You are an expert dashboard designer. Given a natural language dashboard request and the generated panels, determine 1-3 global interactive filters that would be useful for the user to drill down into the data.

Rules:
- Generate 0 to 3 filters.
- Common filters include date ranges (e.g. admit_date), categorical dropdowns (e.g. department_id, facility_id, patient_gender, diagnosis_code).
- filter_type must be one of: 'date_range', 'dropdown', 'multiselect'
- You MUST specify the exact table_name and column_name that this filter will apply to in the database.
- Use valid table names (patients, encounters, diagnoses, procedures, medications, lab_results, vital_signs, claims, readmissions, providers, departments, facilities).

Respond ONLY with a valid JSON array, no markdown fences:
[
  {"label": "Date Range", "column_name": "admit_date", "table_name": "encounters", "filter_type": "date_range"},
  {"label": "Department", "column_name": "name", "table_name": "departments", "filter_type": "dropdown"}
]
""")

class FilterPlanner:
    async def generate_filters(self, request: str, panels: List[DashboardPanel], db) -> List[DashboardFilter]:
        try:
            async with httpx.AsyncClient(
                base_url=settings.llm_base_url,
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                timeout=30,
            ) as client:
                panel_titles = [p.title for p in panels]
                prompt = f"Request: {request}\nPanels: {json.dumps(panel_titles)}"
                
                response = await client.post(
                    "/chat/completions",
                    json={
                        "model": settings.llm_model,
                        "messages": [
                            {"role": "system", "content": FILTER_PLANNER_SYSTEM},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.1,
                    },
                )
                
                if response.status_code != 200:
                    return []
                    
                content = response.json()["choices"][0]["message"]["content"]
                
                # strip markdown code blocks
                if content.startswith("```json"):
                    content = content[7:-3]
                elif content.startswith("```"):
                    content = content[3:-3]
                
                raw_filters = json.loads(content)
                final_filters = []
                
                for rf in raw_filters:
                    f_type = rf.get("filter_type", "dropdown")
                    col = rf.get("column_name", "")
                    tab = rf.get("table_name", "")
                    
                    options = []
                    # Dynamically fetch options if it's categorical
                    if f_type in ["dropdown", "multiselect"] and col and tab:
                        try:
                            # Safely fetch distinct options (max 50 to avoid huge dropdowns)
                            if tab.isidentifier() and col.isidentifier():
                                # Extra security: ensure table and col exist in our application schema
                                extractor = SchemaExtractor(db)
                                schema = await extractor.extract_schema()
                                table_valid = any(t.name == tab and any(c.name == col for c in t.columns) for t in schema)
                                
                                if table_valid:
                                    # Still parameterizing/identifying carefully just in case
                                    res = await db.execute(text(f"SELECT DISTINCT {col} FROM {tab} WHERE {col} IS NOT NULL LIMIT 50"))
                                    options = [str(row[0]) for row in res.fetchall()]
                                else:
                                    logger.warning(f"Filter requested invalid table/column {tab}.{col}")
                        except Exception as e:
                            logger.warning(f"Failed to fetch filter options for {tab}.{col}", error=str(e))
                            
                    final_filters.append(DashboardFilter(
                        id=str(uuid.uuid4()),
                        label=rf.get("label", "Filter"),
                        column_name=col,
                        filter_type=f_type,
                        options=options
                    ))
                    
                return final_filters
        except Exception as e:
            logger.error("Filter generation failed", error=str(e))
            return []

# ─────────────────────────────────────────────────────────────────────────────
# Main Dashboard Generation Engine
# ─────────────────────────────────────────────────────────────────────────────

class DashboardGenerationEngine:
    """
    Public API::

        engine = DashboardGenerationEngine()
        dashboard = await engine.generate(request="Show hospital admissions trends", db=db, redis=redis)
    """

    def __init__(self) -> None:
        self._layout    = LayoutEngine()
        self._composer  = SummaryComposer()
        self._fallback  = FallbackPlanner()
        self._filter_planner = FilterPlanner()

    async def generate(
        self,
        request: str,
        db,
        redis,
    ) -> DashboardResponse:
        dashboard_id = str(uuid.uuid4())
        logger.info("Dashboard generation started", request_preview=request[:60])

        # ── Step 1: Query Planning ────────────────────────────
        plan_items: List[Dict[str, str]] = []
        llm_available = True

        try:
            async with QueryPlanner() as planner:
                plan_items = await planner.plan(request)
            logger.info("LLM query plan complete", panels=len(plan_items))
        except Exception as exc:
            logger.warning("LLM planner unavailable — using fallback", error=str(exc))
            plan_items = self._fallback.plan(request)
            llm_available = False

        # ── Step 2: Parallel Panel Execution ─────────────────
        tasks = [
            _execute_panel(item, i, db, redis)
            for i, item in enumerate(plan_items)
        ]
        panels: List[DashboardPanel] = list(
            await asyncio.gather(*tasks, return_exceptions=False)
        )

        # ── Step 3: Layout Assignment ─────────────────────────
        panels = self._layout.assign_positions(panels)

        # ── Step 4: Executive Summary ─────────────────────────
        summary = ""
        if llm_available:
            try:
                async with httpx.AsyncClient(
                    base_url=settings.llm_base_url,
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    timeout=30,
                ) as client:
                    summary = await self._composer.compose(request, panels, client)
            except Exception as exc:
                logger.warning("Summary composition failed", error=str(exc))

        if not summary:
            non_empty = sum(1 for p in panels if not p.error and p.row_count)
            summary = (
                f"Generated {len(panels)} analytical panels for '{request}'. "
                f"{non_empty} of {len(panels)} panels returned data successfully."
            )

        # ── Step 5: Generate Dynamic Filters ──────────────────
        filters: List[DashboardFilter] = []
        if llm_available:
            filters = await self._filter_planner.generate_filters(request, panels, db)

        # ── Step 6: Dashboard Metadata ────────────────────────
        total_rows = sum(p.row_count or 0 for p in panels)
        success    = sum(1 for p in panels if not p.error)

        logger.info(
            "Dashboard generation complete",
            panels=len(panels),
            success=success,
            total_rows=total_rows,
        )

        return DashboardResponse(
            id=dashboard_id,
            title=_title_from_request(request),
            request=request,
            summary=summary,
            panels=panels,
            layout=DashboardLayout(
                grid_cols=GRID_COLS,
                panel_count=len(panels),
                success_count=success,
            ),
            filters=filters,
            total_rows=total_rows,
        )


def _title_from_request(request: str) -> str:
    """Convert 'Show hospital admissions trends' → 'Hospital Admissions Trends'."""
    stop_words = {"show", "me", "the", "a", "an", "of", "for", "by", "with", "and", "or"}
    words = request.strip().rstrip(".?!").split()
    return " ".join(
        w.capitalize() for w in words if w.lower() not in stop_words
    ) or request[:60]
