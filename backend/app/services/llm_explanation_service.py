"""LLM explanation service: generates clinical insights from query results."""

import json
from typing import Any, Dict, List

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.exceptions import LLMServiceError

logger = structlog.get_logger(__name__)
settings = get_settings()

INSIGHT_SYSTEM_PROMPT = """You are a clinical data analyst with expertise in healthcare analytics.
Your task is to provide 3-5 concise, actionable clinical insights from the given data.

Guidelines:
- Write in clear, professional language suitable for clinicians and administrators.
- Each insight should be 1-2 sentences maximum.
- Focus on clinically relevant patterns, outliers, and improvement opportunities.
- Use percentages and specific numbers from the data when relevant.
- Do NOT make definitive clinical diagnoses or treatment recommendations.
- Output ONLY a JSON array of insight strings: ["insight 1", "insight 2", ...]
"""


class LLMExplanationService:
    """Generates natural language insights from structured query results."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            timeout=settings.llm_timeout_seconds,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self._client.aclose()

    def _build_context(self, question: str, sql: str, results: Dict[str, Any]) -> str:
        """Format query context for the LLM insight prompt."""
        columns = results.get("columns", [])
        rows = results.get("rows", [])
        row_count = results.get("row_count", 0)

        # Preview only the first 20 rows for the LLM
        preview_rows = rows[:20]
        rows_text = "\n".join(
            "  | ".join(str(v) for v in row) for row in preview_rows
        )

        return (
            f"Question: {question}\n\n"
            f"SQL: {sql}\n\n"
            f"Result columns: {', '.join(columns)}\n"
            f"Total rows: {row_count}\n\n"
            f"Data preview ({min(20, row_count)} rows):\n"
            f"{' | '.join(columns)}\n"
            f"{rows_text}"
        )

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        reraise=True,
    )
    async def generate_insights(
        self,
        question: str,
        sql: str,
        results: Dict[str, Any],
    ) -> List[str]:
        """Call LLM and return a list of insight strings."""
        if not results.get("rows"):
            return ["The query returned no results. This may indicate no matching data exists for the specified criteria."]

        context = self._build_context(question, sql, results)

        try:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {"role": "system", "content": INSIGHT_SYSTEM_PROMPT},
                        {"role": "user", "content": context},
                    ],
                    "max_tokens": 800,
                    "temperature": 0.3,
                    "stream": False,
                },
            )
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                lines = raw.split("\n")
                inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
                raw = "\n".join(inner).strip()

            # Parse JSON array from response
            try:
                insights = json.loads(raw)
                if isinstance(insights, list):
                    return [str(i) for i in insights[:5]]
            except json.JSONDecodeError:
                pass

            # Fallback: return raw response as single insight
            return [raw]

        except httpx.HTTPStatusError as exc:
            logger.error("LLM insight API error", status=exc.response.status_code)
            raise LLMServiceError(f"Insight generation failed: {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            logger.warning("LLM insight request failed", error=str(exc))
            return ["Insights could not be generated at this time."]
