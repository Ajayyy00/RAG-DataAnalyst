import structlog
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.schemas.sql_explanation import SQLExplanation

log = structlog.get_logger(__name__)
settings = get_settings()


class SQLExplanationService:
    """Service to translate raw SQL into human-readable explanations using an LLM."""

    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            model=settings.llm_model,
            temperature=0.1,
            max_tokens=1024,
        ).with_structured_output(SQLExplanation)

    async def explain_sql(self, sql: str) -> SQLExplanation | None:
        """Translates a SQL query into a structured SQLExplanation."""
        if not sql or not sql.strip():
            return None

        log.info("Generating SQL explanation")
        sys_msg = SystemMessage(
            content="You are an expert Data Analyst and Database Administrator.\n"
            "Your job is to explain the provided SQL query in clear, human-readable terms.\n"
            "Break down the query into its summary, the tables it uses, how it joins them, the filters it applies, and how it aggregates data.\n"
            "Be concise but thorough so a non-technical user can understand exactly what data is being queried."
        )
        human_msg = HumanMessage(content=f"Explain this SQL query:\n```sql\n{sql}\n```")

        try:
            explanation = await self.llm.ainvoke([sys_msg, human_msg])
            return explanation
        except Exception as e:
            log.error("Failed to generate SQL explanation", error=str(e))
            return None
