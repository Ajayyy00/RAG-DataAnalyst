"""
Router Service
==============
Classifies natural language queries into 'conversational' or 'clinical_query' intents.
Conversational inputs (e.g., greetings, instructions help, or explanation requests) skip
the expensive database execution and LLM Text-to-SQL generation.
"""

from __future__ import annotations

import re

import httpx
import structlog

from app.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

CONVERSATIONAL_KEYWORDS = [
    r"^(hello|hi|hey|greetings|good\s+morning|good\s+afternoon|good\s+evening)\b",
    r"^(who\s+are\s+you|what\s+is\s+your\s+name|what\s+can\s+you\s+do)\b",
    r"^(help|help\s+me|show\s+help|info|how\s+to\s+use)\b",
    r"^(clear\s+chat|reset|restart|thank\s+you|thanks|bye|goodbye)\b",
]
CONVERSATIONAL_RE = re.compile("|".join(CONVERSATIONAL_KEYWORDS), re.IGNORECASE)


class RouterService:
    """Service to route query intents."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.llm_base_url,
            headers={
                "Authorization": f"Bearer {settings.llm_api_key}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )

    async def classify_intent(self, question: str) -> str:
        """
        Classifies query as 'conversational' or 'clinical_query'.
        """
        stripped = question.strip()
        # Heuristic fast check
        if CONVERSATIONAL_RE.match(stripped) or len(stripped) < 4:
            log.info("Heuristic intent match: conversational", question=stripped)
            return "conversational"

        # LLM fallback check (fast categorization)
        try:
            response = await self._client.post(
                "/chat/completions",
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a routing classification agent for a healthcare analytical dashboard. "
                                "Classify the input question into exactly one category: 'conversational' or 'clinical_query'.\n"
                                "If the question is a greeting, a help request, conversational chit-chat, or asking what you can do, "
                                "classify it as 'conversational'.\n"
                                "If it asks for patient data, clinical statistics, diagnostics, claims, vital signs, readmissions, "
                                "or any clinical information requiring database retrieval, classify it as 'clinical_query'.\n"
                                "Output ONLY the category name. No formatting, no extra text."
                            ),
                        },
                        {"role": "user", "content": stripped},
                    ],
                    "max_tokens": 10,
                    "temperature": 0.0,
                    "stream": False,
                },
            )
            response.raise_for_status()
            intent = response.json()["choices"][0]["message"]["content"].strip().lower()
            if "clinical_query" in intent:
                return "clinical_query"
            return "conversational"
        except Exception as exc:
            log.warning(
                "LLM intent classification failed, falling back to clinical_query",
                error=str(exc),
            )
            return "clinical_query"

    async def close(self) -> None:
        await self._client.aclose()
