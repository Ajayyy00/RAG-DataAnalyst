"""
AI Insights Engine
==================
Generates structured, clinically-relevant insights from SQL query results
using Llama 3 (served via an OpenAI-compatible endpoint).

Output contract
---------------
For every query the engine produces an **InsightReport** containing:
  - summary              Plain-English 1-2 sentence overview
  - trends               Key statistical/clinical trends observed
  - anomalies            Outliers, unexpected values, data concerns
  - recommendations      Prioritised, actionable next steps
  - follow_up_questions  Suggested deeper queries the analyst may want to ask
  - data_quality_notes   Coverage gaps, nulls, suspiciously uniform data
  - confidence           "high" / "medium" / "low" based on data richness

Architecture
------------
  DataProfiler      → statistical characterisation of the result set
  PromptBuilder     → assembles the Llama 3 system + user prompt
  LlamaClient       → async HTTP to the OpenAI-compatible LLM endpoint
  ResponseParser    → extracts structured JSON from the raw LLM reply
  InsightsEngine    → orchestrates the above; public API
  FallbackEngine    → rule-based fallback when LLM is unavailable
"""

from __future__ import annotations

import json
import re
import statistics
import textwrap
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.schemas.chat import InsightReport, Recommendation

logger = structlog.get_logger(__name__)
settings = get_settings()

# ──────────────────────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────────────────────

MAX_PREVIEW_ROWS = 30  # rows sent to LLM (avoid context overflow)
MAX_DISTINCT_SHOWN = 10  # distinct values shown per column in profile
INSIGHT_MAX_TOKENS = 1200
INSIGHT_TEMPERATURE = 0.25  # Low temp → consistent, factual clinical output


SYSTEM_PROMPT = textwrap.dedent("""\
You are an expert clinical data analyst and healthcare quality improvement specialist.
Your role is to analyse SQL query results and produce **structured, actionable insights**
for clinical administrators, data scientists, and hospital leadership.

Core principles:
- Be specific: use exact numbers and percentages from the data.
- Be clinically relevant: relate findings to patient safety, quality, and cost.
- Be conservative: only flag anomalies you can support with the data.
- Never fabricate data or make clinical diagnoses.
- Confidence should reflect data richness (more rows → higher confidence).

You MUST respond with ONLY a valid JSON object matching this exact schema:
{
  "summary": "<1-2 sentences plain-English overview of what the data shows>",
  "trends": ["<trend 1>", "<trend 2>", ...],
  "anomalies": ["<anomaly 1>", ...],
  "recommendations": [
    {
      "priority": "high|medium|low",
      "action": "<imperative verb phrase>",
      "rationale": "<clinical / operational justification>",
      "metric": "<specific KPI or figure from data>"
    }
  ],
  "follow_up_questions": ["<question 1>", "<question 2>", ...],
  "data_quality_notes": ["<note 1>", ...],
  "confidence": "high|medium|low"
}

Output ONLY the JSON. No markdown fences, no preamble, no trailing text.
""")


# ──────────────────────────────────────────────────────────────
#  Data Profiler — statistical characterisation of result set
# ──────────────────────────────────────────────────────────────


@dataclass
class ColumnProfile:
    name: str
    dtype: str  # "numeric" | "temporal" | "categorical" | "mixed"
    count: int
    null_count: int
    null_pct: float
    # Numeric stats (if applicable)
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    mean_val: Optional[float] = None
    median_val: Optional[float] = None
    stdev_val: Optional[float] = None
    # Categorical stats
    distinct_count: int = 0
    top_values: List[Any] = field(default_factory=list)
    # Temporal
    date_range: Optional[str] = None


@dataclass
class DataProfile:
    row_count: int
    col_count: int
    columns: List[ColumnProfile]
    has_nulls: bool
    is_empty: bool


class DataProfiler:
    """Compute lightweight statistics on query result arrays."""

    def profile(self, columns: List[str], rows: List[List[Any]]) -> DataProfile:
        if not columns or not rows:
            return DataProfile(
                row_count=0,
                col_count=len(columns),
                columns=[],
                has_nulls=False,
                is_empty=True,
            )

        n = len(rows)
        col_profiles: List[ColumnProfile] = []

        for i, col_name in enumerate(columns):
            raw_vals = [row[i] for row in rows if i < len(row)]
            non_null = [v for v in raw_vals if v is not None and v != ""]
            null_count = n - len(non_null)

            cp = ColumnProfile(
                name=col_name,
                dtype="categorical",
                count=n,
                null_count=null_count,
                null_pct=round(null_count / n * 100, 1) if n else 0,
            )

            # Try to coerce to float
            floats: List[float] = []
            for v in non_null:
                try:
                    floats.append(float(str(v).replace(",", "")))
                except (ValueError, TypeError):
                    pass

            if len(floats) >= len(non_null) * 0.7 and floats:
                cp.dtype = "numeric"
                cp.min_val = round(min(floats), 4)
                cp.max_val = round(max(floats), 4)
                cp.mean_val = round(statistics.mean(floats), 4)
                cp.median_val = round(statistics.median(floats), 4)
                if len(floats) > 1:
                    cp.stdev_val = round(statistics.stdev(floats), 4)
            else:
                str_vals = [str(v) for v in non_null]
                distinct = list(dict.fromkeys(str_vals))  # ordered-unique
                cp.distinct_count = len(distinct)
                cp.top_values = distinct[:MAX_DISTINCT_SHOWN]

                # Detect temporal column
                if col_name.lower() in {
                    "date",
                    "month",
                    "year",
                    "quarter",
                    "week",
                    "period",
                    "timestamp",
                    "dt",
                }:
                    cp.dtype = "temporal"
                    if non_null:
                        cp.date_range = f"{non_null[0]} → {non_null[-1]}"

            col_profiles.append(cp)

        return DataProfile(
            row_count=n,
            col_count=len(columns),
            columns=col_profiles,
            has_nulls=any(cp.null_count > 0 for cp in col_profiles),
            is_empty=False,
        )

    def to_text(self, profile: DataProfile) -> str:
        """Render profile as compact text for inclusion in the prompt."""
        if profile.is_empty:
            return "Dataset is empty — no rows returned."

        lines = [f"Dataset: {profile.row_count} rows × {profile.col_count} columns"]
        if profile.has_nulls:
            lines.append("(Some columns contain null values — see below)")

        for cp in profile.columns:
            if cp.dtype == "numeric":
                lines.append(
                    f"  [{cp.name}] numeric | "
                    f"min={cp.min_val}, max={cp.max_val}, "
                    f"mean={cp.mean_val}, median={cp.median_val}"
                    + (f", stdev={cp.stdev_val}" if cp.stdev_val else "")
                    + (f" | {cp.null_pct}% null" if cp.null_count else "")
                )
            elif cp.dtype == "temporal":
                lines.append(
                    f"  [{cp.name}] temporal | range: {cp.date_range}"
                    + (f" | {cp.null_pct}% null" if cp.null_count else "")
                )
            else:
                top_str = ", ".join(str(v) for v in cp.top_values)
                lines.append(
                    f"  [{cp.name}] categorical | "
                    f"{cp.distinct_count} distinct values | top: {top_str}"
                    + (f" | {cp.null_pct}% null" if cp.null_count else "")
                )

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
#  Prompt Builder
# ──────────────────────────────────────────────────────────────


class PromptBuilder:
    """Assembles the user message for the Llama 3 insights call."""

    def __init__(self, profiler: DataProfiler) -> None:
        self._profiler = profiler

    def build(
        self,
        question: str,
        sql: str,
        columns: List[str],
        rows: List[List[Any]],
    ) -> str:
        profile = self._profiler.profile(columns, rows)
        profile_text = self._profiler.to_text(profile)

        # Preview rows (first N)
        preview_rows = rows[:MAX_PREVIEW_ROWS]
        header = " | ".join(columns)
        body = "\n".join(
            " | ".join(str(v) if v is not None else "NULL" for v in row)
            for row in preview_rows
        )
        shown = f"Showing {len(preview_rows)} of {profile.row_count} rows"

        return textwrap.dedent(f"""\
            CLINICAL QUESTION:
            {question}

            GENERATED SQL:
            {sql.strip()}

            STATISTICAL PROFILE:
            {profile_text}

            RAW DATA PREVIEW ({shown}):
            {header}
            {body}

            Analyse the data above and return your JSON insight report.
            Remember: output ONLY valid JSON, no markdown fences.
        """)


# ──────────────────────────────────────────────────────────────
#  Llama 3 Client
# ──────────────────────────────────────────────────────────────


class LlamaClient:
    """
    Async client for any OpenAI-compatible inference endpoint
    (llama.cpp server, vLLM, Ollama, Groq, OpenRouter, etc.)
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_seconds,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "LlamaClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    @retry(
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def complete(self, user_message: str) -> str:
        """Send a chat completion request and return the raw assistant reply."""
        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "max_tokens": INSIGHT_MAX_TOKENS,
            "temperature": INSIGHT_TEMPERATURE,
            "stream": False,
        }

        resp = await self._client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()


# ──────────────────────────────────────────────────────────────
#  Response Parser
# ──────────────────────────────────────────────────────────────


class ResponseParser:
    """
    Extracts a valid InsightReport from the raw LLM text.
    Handles:
      - Clean JSON
      - JSON wrapped in markdown fences
      - Partial / truncated JSON (best-effort recovery)
    """

    _FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
    _BRACE_RE = re.compile(r"\{.*\}", re.DOTALL)

    def parse(self, raw: str) -> InsightReport:
        json_str = self._extract_json(raw)
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # Attempt to fix common LLM JSON mistakes
            data = self._repair_and_load(json_str)

        return self._to_report(data)

    def _extract_json(self, raw: str) -> str:
        # 1. Try fenced block first
        m = self._FENCE_RE.search(raw)
        if m:
            return m.group(1).strip()
        # 2. Try bare JSON object
        m = self._BRACE_RE.search(raw)
        if m:
            return m.group(0).strip()
        return raw.strip()

    def _repair_and_load(self, text: str) -> dict:
        """Best-effort repairs for common LLM JSON problems."""
        # Trailing commas
        text = re.sub(r",\s*([}\]])", r"\1", text)
        # Single quotes instead of double
        text = text.replace("'", '"')
        # Unquoted keys
        text = re.sub(r"(\b\w+\b)\s*:", r'"\1":', text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("JSON repair failed — returning empty report")
            return {}

    def _to_report(self, data: dict) -> InsightReport:
        recs = []
        for r in data.get("recommendations", []):
            if isinstance(r, dict):
                recs.append(
                    Recommendation(
                        priority=r.get("priority", "medium"),
                        action=r.get("action", ""),
                        rationale=r.get("rationale", ""),
                        metric=r.get("metric"),
                    )
                )
            elif isinstance(r, str):
                recs.append(Recommendation(priority="medium", action=r, rationale=""))

        confidence = data.get("confidence", "medium")
        if confidence not in {"high", "medium", "low"}:
            confidence = "medium"

        return InsightReport(
            summary=data.get("summary", "No summary generated."),
            trends=self._as_str_list(data.get("trends", [])),
            anomalies=self._as_str_list(data.get("anomalies", [])),
            recommendations=recs,
            follow_up_questions=self._as_str_list(data.get("follow_up_questions", [])),
            data_quality_notes=self._as_str_list(data.get("data_quality_notes", [])),
            confidence=confidence,
        )

    @staticmethod
    def _as_str_list(val) -> List[str]:
        if isinstance(val, list):
            return [str(v) for v in val if v]
        if isinstance(val, str):
            return [val] if val else []
        return []


# ──────────────────────────────────────────────────────────────
#  Rule-based Fallback Engine
# ──────────────────────────────────────────────────────────────


class FallbackInsightEngine:
    """
    Generates basic insights using statistical rules when the LLM
    is unavailable or times out.  No network calls required.
    """

    def __init__(self) -> None:
        self._profiler = DataProfiler()

    def generate(
        self,
        question: str,
        columns: List[str],
        rows: List[List[Any]],
    ) -> InsightReport:
        if not rows:
            return InsightReport(
                summary="The query returned no results. This may indicate no matching data for the specified criteria.",
                confidence="low",
                follow_up_questions=[
                    "Is the date range correct?",
                    "Are the filters too restrictive?",
                    "Does this data exist in the system yet?",
                ],
            )

        profile = self._profiler.profile(columns, rows)
        trends: List[str] = []
        anomalies: List[str] = []
        recs: List[Recommendation] = []
        quality: List[str] = []
        follow_ups: List[str] = []

        for cp in profile.columns:
            # Numeric analysis
            if cp.dtype == "numeric" and cp.mean_val is not None:
                if cp.stdev_val and cp.stdev_val > cp.mean_val * 0.5:
                    anomalies.append(
                        f"'{cp.name}' shows high variability "
                        f"(mean={cp.mean_val}, stdev={cp.stdev_val}) — "
                        "consider investigating outlier cases."
                    )
                    recs.append(
                        Recommendation(
                            priority="medium",
                            action=f"Investigate high variability in {cp.name}",
                            rationale="Large spread may indicate inconsistent practice or data quality issues.",
                            metric=f"stdev={cp.stdev_val}",
                        )
                    )
                if cp.min_val is not None and cp.max_val is not None:
                    trends.append(
                        f"'{cp.name}' ranges from {cp.min_val} to {cp.max_val} "
                        f"(mean {cp.mean_val}, median {cp.median_val})."
                    )
                if cp.min_val == cp.max_val and cp.count > 1:
                    anomalies.append(
                        f"'{cp.name}' has an identical value ({cp.min_val}) "
                        "for all rows — potential data quality issue."
                    )

            # Null analysis
            if cp.null_pct > 20:
                quality.append(
                    f"'{cp.name}' has {cp.null_pct}% missing values — "
                    "results may be incomplete."
                )
                recs.append(
                    Recommendation(
                        priority="high",
                        action=f"Investigate missing data in '{cp.name}'",
                        rationale=f"{cp.null_pct}% nulls may bias aggregations.",
                        metric=f"{cp.null_count} null rows out of {cp.count}",
                    )
                )

            # Categorical
            if cp.dtype == "categorical" and cp.distinct_count == 1:
                anomalies.append(
                    f"'{cp.name}' contains only one distinct value "
                    f"('{cp.top_values[0] if cp.top_values else 'N/A'}') "
                    "— this column may not be discriminating."
                )

        # Row count feedback
        if profile.row_count < 5:
            quality.append(
                f"Only {profile.row_count} rows returned. "
                "Statistical conclusions may not be reliable."
            )
        if profile.row_count > 1000:
            trends.append(
                f"Large dataset ({profile.row_count:,} rows) provides "
                "high statistical confidence."
            )

        # Generic follow-up questions
        follow_ups = [
            f"How does this trend compare to the same period last year?",
            f"Which patient subgroups drive the largest share of these results?",
            f"Can we break this down by department or provider?",
            f"What is the 30-day trend for the top metric?",
        ]

        confidence = (
            "high"
            if profile.row_count >= 100
            else "medium" if profile.row_count >= 10 else "low"
        )

        summary_parts = [f"The query returned {profile.row_count:,} rows."]
        if trends:
            summary_parts.append(trends[0])

        return InsightReport(
            summary=" ".join(summary_parts),
            trends=trends[:5],
            anomalies=anomalies[:5],
            recommendations=recs[:4],
            follow_up_questions=follow_ups[:4],
            data_quality_notes=quality[:4],
            confidence=confidence,
        )


# ──────────────────────────────────────────────────────────────
#  Main Insights Engine — public API
# ──────────────────────────────────────────────────────────────


class InsightsEngine:
    """
    Orchestrates the full pipeline:
      DataProfiler → PromptBuilder → LlamaClient → ResponseParser

    Falls back to FallbackInsightEngine on any LLM error.
    """

    def __init__(self) -> None:
        self._profiler = DataProfiler()
        self._builder = PromptBuilder(self._profiler)
        self._parser = ResponseParser()
        self._fallback = FallbackInsightEngine()

    async def generate(
        self,
        question: str,
        sql: str,
        columns: List[str],
        rows: List[List[Any]],
    ) -> InsightReport:
        """
        Generate an InsightReport for the given query result.

        Always returns a valid InsightReport — never raises.
        """
        if not rows:
            return InsightReport(
                summary="The query returned no results. "
                "This may indicate no matching data for the specified criteria.",
                confidence="low",
                follow_up_questions=[
                    "Is the date range correct?",
                    "Are the filter criteria too restrictive?",
                    "Has this data been captured in the source system?",
                ],
            )

        user_message = self._builder.build(question, sql, columns, rows)

        try:
            async with LlamaClient() as llm:
                raw = await llm.complete(user_message)
            report = self._parser.parse(raw)
            logger.info(
                "AI insight report generated",
                question_preview=question[:60],
                confidence=report.confidence,
                trends=len(report.trends),
                recommendations=len(report.recommendations),
            )
            return report

        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            logger.warning(
                "LLM unavailable — using rule-based fallback", error=str(exc)
            )
            return self._fallback.generate(question, columns, rows)

        except httpx.HTTPStatusError as exc:
            logger.error("LLM API error", status=exc.response.status_code)
            return self._fallback.generate(question, columns, rows)

        except Exception as exc:
            logger.error("Unexpected insight engine error", error=str(exc))
            return self._fallback.generate(question, columns, rows)

    def to_flat_list(self, report: InsightReport) -> List[str]:
        """
        Backward-compatible flat list of insight strings for the legacy
        ``ChatQueryResponse.insights`` field.
        """
        items: List[str] = []
        if report.summary:
            items.append(report.summary)
        items.extend(report.trends)
        items.extend(report.anomalies)
        for rec in report.recommendations:
            items.append(f"[{rec.priority.upper()}] {rec.action} — {rec.rationale}")
        return items[:8]  # Cap to keep the UI clean
