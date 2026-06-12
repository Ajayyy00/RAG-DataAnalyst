"""
text_to_sql_service.py  (updated)
==================================
Builds a structured, schema-grounded prompt and calls the LLM.

Prompt architecture (layered):
  [SYSTEM]   Role + hard rules + allowed tables
  [SYSTEM]   Retrieved schema context (RAG output)
  [SYSTEM]   Few-shot SQL examples (domain-specific, 4 examples)
  [HISTORY]  Last N conversation turns (multi-turn context)
  [USER]     Current question with CoT instruction
"""

from __future__ import annotations

from typing import List, Optional

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.core.exceptions import LLMServiceError

log = structlog.get_logger(__name__)
settings = get_settings()


# ── Allowed tables (must match sql_validation_service.py allowlist) ────────────
ALLOWED_TABLES: list[str] = [
    "patients", "encounters", "diagnoses", "procedures",
    "medications", "lab_results", "vital_signs", "claims",
    "readmissions", "providers", "departments", "facilities",
    "insurance_plans", "allergies", "immunizations",
    "care_plans", "observations",
]


# ── System prompt ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are an expert PostgreSQL query engineer for a healthcare analytics data warehouse.
Your role is to convert natural language clinical questions into syntactically correct, optimised, read-only PostgreSQL queries.

## Hard Rules
- Output ONLY the raw SQL query — no markdown fences, no explanation, no comments.
- Never use DROP, INSERT, UPDATE, DELETE, TRUNCATE, ALTER, CREATE, or GRANT.
- Every query MUST include a LIMIT clause (default: LIMIT 100).
- Use explicit JOIN ... ON syntax (never implicit comma joins).
- Always alias tables with short, meaningful aliases (p for patients, e for encounters, etc.).
- Prefer CTEs (WITH ...) over deeply nested subqueries for readability.
- Use DATE_TRUNC('month', col) for time-series grouping.
- Use EXTRACT(YEAR FROM AGE(date_of_birth)) for patient age calculations.
- Use ILIKE for case-insensitive text searches.
- Use COALESCE to handle NULL values in aggregations.
- Cast types explicitly: CAST(col AS NUMERIC) when mixing types.
- For ICD-10 code pattern matching use: diagnosis_code ILIKE 'E11%' for diabetes.
- Queryable tables: {allowed_tables}
"""

# ── Few-shot examples ──────────────────────────────────────────────────────────
# These are embedded in the system prompt as authoritative examples.
# They demonstrate correct aliasing, JOIN patterns, and clinical domain idioms.
FEW_SHOT_EXAMPLES = """
## Example SQL Queries

### Example 1 — Age-filtered diagnosis search
Question: Show diabetic patients over 60 with high glucose readings.

SQL:
WITH diabetic_patients AS (
    SELECT DISTINCT p.id, p.first_name, p.last_name,
           EXTRACT(YEAR FROM AGE(p.date_of_birth)) AS age
    FROM patients p
    JOIN encounters e ON e.patient_id = p.id
    JOIN diagnoses  d ON d.encounter_id = e.id
    WHERE d.icd10_code ILIKE 'E11%'           -- Type 2 diabetes
      AND EXTRACT(YEAR FROM AGE(p.date_of_birth)) > 60
),
high_glucose AS (
    SELECT lr.patient_id, AVG(lr.result_value) AS avg_glucose
    FROM lab_results lr
    WHERE lr.loinc_code = '2345-7'            -- Glucose [Mass/volume] in Serum/Plasma
      AND lr.result_value::NUMERIC > 126       -- ADA threshold for diabetes
    GROUP BY lr.patient_id
)
SELECT dp.first_name, dp.last_name, dp.age, hg.avg_glucose
FROM diabetic_patients dp
JOIN high_glucose hg ON hg.patient_id = dp.id
ORDER BY hg.avg_glucose DESC
LIMIT 100;

---

### Example 2 — 30-day readmission rate by department
Question: What is the 30-day readmission rate by department for the last 6 months?

SQL:
WITH index_encounters AS (
    SELECT e.id, e.patient_id, e.department_id, e.discharge_date
    FROM encounters e
    WHERE e.discharge_date >= CURRENT_DATE - INTERVAL '6 months'
      AND e.encounter_type = 'inpatient'
),
readmitted AS (
    SELECT ie.id AS index_id
    FROM index_encounters ie
    JOIN encounters re ON re.patient_id = ie.patient_id
                       AND re.admit_date > ie.discharge_date
                       AND re.admit_date <= ie.discharge_date + INTERVAL '30 days'
                       AND re.encounter_type = 'inpatient'
)
SELECT
    d.name                                                     AS department,
    COUNT(ie.id)                                               AS total_encounters,
    COUNT(r.index_id)                                          AS readmissions,
    ROUND(COUNT(r.index_id)::NUMERIC / NULLIF(COUNT(ie.id), 0) * 100, 1) AS readmission_rate_pct
FROM index_encounters ie
JOIN departments d ON d.id = ie.department_id
LEFT JOIN readmitted r ON r.index_id = ie.id
GROUP BY d.name
ORDER BY readmission_rate_pct DESC
LIMIT 50;

---

### Example 3 — Average length of stay
Question: Average length of stay by department?

SQL:
SELECT
    d.name                                                           AS department,
    COUNT(e.id)                                                      AS encounter_count,
    ROUND(AVG(DATE_PART('day', e.discharge_date - e.admit_date))::NUMERIC, 1)                  AS avg_los_days,
    ROUND((EXTRACT(EPOCH FROM PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY e.discharge_date - e.admit_date)) / 86400.0)::NUMERIC, 1) AS median_los_days
FROM encounters e
JOIN departments d ON d.id = e.department_id
WHERE e.encounter_type = 'inpatient'
  AND e.discharge_date IS NOT NULL
  AND e.admit_date IS NOT NULL
GROUP BY d.name
HAVING COUNT(e.id) >= 10
ORDER BY avg_los_days DESC
LIMIT 50;

---

### Example 4 — Top medications for a condition
Question: Most prescribed medications for hypertensive patients this year?

SQL:
SELECT
    m.medication_name,
    m.drug_class,
    COUNT(DISTINCT m.patient_id) AS patient_count,
    COUNT(m.id)                  AS prescription_count
FROM medications m
JOIN diagnoses d ON d.encounter_id = m.encounter_id
WHERE d.icd10_code ILIKE 'I10%'                     -- Essential hypertension
  AND DATE_TRUNC('year', m.prescribed_date) = DATE_TRUNC('year', CURRENT_DATE)
GROUP BY m.medication_name, m.drug_class
ORDER BY patient_count DESC
LIMIT 20;
"""


# ── TextToSQLService ───────────────────────────────────────────────────────────

class TextToSQLService:
    """
    Converts natural language questions to SQL via an OpenAI-compatible LLM.

    Usage (async context manager to ensure httpx client is properly closed):

        async with TextToSQLService() as svc:
            sql = await svc.generate_sql(question, schema_context)
    """

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "HTTP-Referer": "https://healthcare-copilot.app",
                "X-Title": "Healthcare Copilot",
                "Content-Type": "application/json",
            },
            timeout=settings.llm_timeout_seconds,
        )

    async def __aenter__(self) -> "TextToSQLService":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self._client.aclose()

    def _build_messages(
        self,
        question: str,
        schema_context: str,
        conversation_history: list[dict],
    ) -> list[dict]:
        """
        Assemble the messages array with layered system prompts.

        Layer 1: Role + rules
        Layer 2: Schema context (RAG output)
        Layer 3: Few-shot examples
        Layer 4: Conversation history (last 6 turns)
        Layer 5: Current question with chain-of-thought instruction
        """
        # Layer 1 + 2 + 3 in one system message
        system_content = (
            SYSTEM_PROMPT.format(allowed_tables=", ".join(ALLOWED_TABLES))
            + "\n\n"
            + schema_context
            + "\n\n"
            + FEW_SHOT_EXAMPLES
        )

        messages: list[dict] = [{"role": "system", "content": system_content}]

        # Layer 4: recent history (max 6 turns = 12 messages)
        recent = conversation_history[-12:] if len(conversation_history) > 12 else conversation_history
        messages.extend(recent)

        # Layer 5: user question with CoT instruction
        messages.append({
            "role": "user",
            "content": (
                f"Question: {question}\n\n"
                "Think step by step:\n"
                "1. Which tables are needed?\n"
                "2. What JOINs are required?\n"
                "3. What WHERE filters apply?\n"
                "4. What aggregation or ordering is needed?\n\n"
                "Now output ONLY the SQL query:"
            ),
        })

        return messages

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def generate_sql(
        self,
        question: str,
        schema_context: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> str:
        """
        Call the LLM and return a clean SQL string.

        Strips markdown fences, leading/trailing whitespace, and ensures
        the result starts with a SQL keyword.
        """
        history  = conversation_history or []
        messages = self._build_messages(question, schema_context, history)

        try:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model":       settings.llm_model,
                    "messages":    messages,
                    "max_tokens":  settings.llm_max_tokens,
                    "temperature": settings.llm_temperature,
                    "stream":      False,
                },
            )
            response.raise_for_status()
            data = response.json()
            raw  = data["choices"][0]["message"]["content"].strip()

        except httpx.HTTPStatusError as exc:
            log.error("LLM API error", status=exc.response.status_code)
            raise LLMServiceError(f"LLM returned HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            log.error("LLM unreachable", error=str(exc))
            raise LLMServiceError(f"LLM service unreachable: {exc}") from exc

        sql = self._clean_sql(raw)

        log.info(
            "SQL generated",
            question_preview=question[:80],
            sql_preview=sql[:120],
            model=settings.llm_model,
        )
        return sql

    @staticmethod
    def _clean_sql(raw: str) -> str:
        """
        Strip markdown fences and any non-SQL preamble the model may have added.
        """
        # Remove ```sql ... ``` fences
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Drop first line (```sql or ```) and last line (```)
            inner = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
            raw = "\n".join(inner).strip()

        # If the model prepended "SQL:" or "Query:" labels, remove them
        for prefix in ("sql:", "query:", "sql query:"):
            if raw.lower().startswith(prefix):
                raw = raw[len(prefix):].strip()
                break

        # Ensure it starts with a known SQL keyword
        sql_starters = ("SELECT", "WITH", "EXPLAIN")
        if not any(raw.upper().startswith(s) for s in sql_starters):
            # Try to find the first SELECT/WITH in the output
            for line in raw.split("\n"):
                stripped = line.strip()
                if any(stripped.upper().startswith(s) for s in sql_starters):
                    raw = raw[raw.index(stripped):]
                    break

        return raw.strip()
