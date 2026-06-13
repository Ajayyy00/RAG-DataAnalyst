"""SQL Optimization Engine for detecting slow queries and suggesting rewrites/indexes."""

import json
from typing import Any, Dict, List

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import get_settings

log = structlog.get_logger(__name__)
settings = get_settings()

class OptimizationResult(BaseModel):
    optimized_sql: str = Field(description="The rewritten, highly optimized raw SQL query. Do not include markdown fences.")
    index_suggestions: List[str] = Field(description="List of raw CREATE INDEX SQL commands that would speed up this query.")

class SQLOptimizationEngine:
    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "not-needed",
            model=settings.llm_model,
            temperature=0.1,  # Low temperature for deterministic code generation
            max_tokens=settings.llm_max_tokens,
        ).with_structured_output(OptimizationResult)

    async def analyze_plan(self, db: AsyncSession, sql: str) -> Dict[str, Any]:
        """
        Executes an EXPLAIN (FORMAT JSON) to retrieve the query execution plan.
        We do not use ANALYZE to avoid executing a potentially very slow query here,
        relying on PostgreSQL's cost estimator instead.
        """
        try:
            # We must wrap in a transaction or just execute, it's a read-only EXPLAIN
            result = await db.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"))
            plan_data = result.scalar()
            
            # plan_data is typically a list containing a single dictionary
            if isinstance(plan_data, str):
                plan_json = json.loads(plan_data)
            else:
                plan_json = plan_data
                
            if isinstance(plan_json, list) and len(plan_json) > 0:
                return plan_json[0].get("Plan", {})
            return plan_json.get("Plan", {}) if isinstance(plan_json, dict) else {}
        except Exception as e:
            log.warning("Failed to analyze execution plan", error=str(e))
            return {}

    def is_slow_query(self, plan: Dict[str, Any]) -> bool:
        """
        Heuristic to detect if a query is slow based on the EXPLAIN plan.
        We check if the Total Cost is high or if there are severe Sequential Scans on large tables.
        """
        if not plan:
            return False
            
        total_cost = plan.get("Total Cost", 0)
        
        # Arbitrary threshold for "slow" query. 
        # In a real system, this might be dynamically calibrated.
        if total_cost > 1000.0:
            return True
            
        # Recursive check for sequential scans
        def has_seq_scan(node: Dict[str, Any]) -> bool:
            if node.get("Node Type") == "Seq Scan":
                return True
            for child in node.get("Plans", []):
                if has_seq_scan(child):
                    return True
            return False
            
        return has_seq_scan(plan)

    async def optimize(self, sql: str, plan: Dict[str, Any]) -> OptimizationResult:
        """
        Uses an LLM to rewrite the SQL and suggest indexes based on the execution plan.
        """
        log.info("Optimizing SQL with LLM", plan_cost=plan.get("Total Cost"))
        
        sys_msg = SystemMessage(
            content="You are an expert PostgreSQL Database Administrator and Query Optimizer.\n"
                    "Your job is to analyze the provided SQL query and its PostgreSQL EXPLAIN execution plan.\n"
                    "1. Rewrite the SQL to be mathematically equivalent but faster (e.g., using CTEs, proper JOINs, or window functions).\n"
                    "2. Suggest optimal `CREATE INDEX` commands to speed up the query.\n"
                    "Return the response in the requested structured JSON format."
        )
        
        plan_str = json.dumps(plan, indent=2)
        human_msg = HumanMessage(
            content=f"Original SQL:\n{sql}\n\nExecution Plan:\n{plan_str}"
        )
        
        try:
            result = await self.llm.ainvoke([sys_msg, human_msg])
            return result
        except Exception as e:
            log.error("LLM Optimization failed", error=str(e))
            return OptimizationResult(optimized_sql=sql, index_suggestions=[])
