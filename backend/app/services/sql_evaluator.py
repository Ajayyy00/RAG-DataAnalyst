import json
import time
import os
import structlog
from typing import List, Any
import sqlglot
from sqlalchemy.ext.asyncio import AsyncSession

# langchain_openai provides get_openai_callback via langchain_community; fall back gracefully
try:
    from langchain_community.callbacks.manager import get_openai_callback
except ImportError:
    from contextlib import contextmanager

    @contextmanager
    def get_openai_callback():
        """Stub callback when langchain_community is unavailable."""
        class _CB:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
        yield _CB()

from app.schemas.evaluation import EvaluationResult, BenchmarkReport
from app.services.agentic_sql_service import AgenticSQLService
from app.services.query_execution_service import QueryExecutionService

log = structlog.get_logger(__name__)

# GPT-4o pricing per 1K tokens
COST_PER_1K_PROMPT = 0.005
COST_PER_1K_COMPLETION = 0.015

class SQLEvaluatorService:
    def __init__(self, db: AsyncSession, current_user: Any = None):
        self.db = db
        self.current_user = current_user
        self.agentic_svc = AgenticSQLService(db, current_user)
        self.exec_svc = QueryExecutionService(db)

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens / 1000.0 * COST_PER_1K_PROMPT) + (completion_tokens / 1000.0 * COST_PER_1K_COMPLETION)

    def _check_exact_match(self, sql_a: str, sql_b: str) -> bool:
        try:
            ast_a = sqlglot.parse_one(sql_a, read="postgres")
            ast_b = sqlglot.parse_one(sql_b, read="postgres")
            return ast_a.sql() == ast_b.sql()
        except Exception:
            return False

    async def _check_execution_accuracy(self, generated_sql: str, gold_sql: str) -> bool:
        try:
            # Execute both and compare the rows
            # "Exactly ordered rows" requested by user
            gen_result = await self.exec_svc.execute(generated_sql, max_rows=100)
            gold_result = await self.exec_svc.execute(gold_sql, max_rows=100)
            
            # Compare columns and rows exactly
            if gen_result["columns"] != gold_result["columns"]:
                return False
            if gen_result["rows"] != gold_result["rows"]:
                return False
            return True
        except Exception as e:
            log.warning("Execution accuracy check failed", error=str(e))
            return False

    async def evaluate_query(self, benchmark_id: str, question: str, gold_sql: str) -> EvaluationResult:
        log.info(f"Evaluating query {benchmark_id}")
        start_time = time.time()
        final_sql = None
        error_msg = None
        
        with get_openai_callback() as cb:
            try:
                # Run the stream to completion to get the final SQL
                async for event in self.agentic_svc.generate_sql_stream(question):
                    if event["type"] == "sql":
                        final_sql = event["sql"]
                    elif event["type"] == "error":
                        error_msg = event.get("message")
            except Exception as e:
                error_msg = str(e)
                
        latency_ms = int((time.time() - start_time) * 1000)
        prompt_tokens = cb.prompt_tokens
        completion_tokens = cb.completion_tokens
        total_tokens = cb.total_tokens
        cost_usd = self._calculate_cost(prompt_tokens, completion_tokens)

        exact_match = False
        execution_accuracy = False

        if final_sql:
            exact_match = self._check_exact_match(final_sql, gold_sql)
            execution_accuracy = await self._check_execution_accuracy(final_sql, gold_sql)

        return EvaluationResult(
            id=benchmark_id,
            question=question,
            gold_sql=gold_sql,
            generated_sql=final_sql,
            exact_match=exact_match,
            execution_accuracy=execution_accuracy,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            error=error_msg
        )

    async def run_benchmark(self, dataset_path: str = "tests/evaluation/benchmark_dataset.json") -> BenchmarkReport:
        abs_path = os.path.join(os.getcwd(), dataset_path)
        with open(abs_path, "r") as f:
            dataset = json.load(f)

        results = []
        for item in dataset:
            res = await self.evaluate_query(item["id"], item["question"], item["gold_sql"])
            results.append(res)

        total_queries = len(results)
        successful_queries = sum(1 for r in results if r.execution_accuracy)
        avg_latency = sum(r.latency_ms for r in results) / total_queries if total_queries else 0
        em_rate = sum(1 for r in results if r.exact_match) / total_queries if total_queries else 0
        exec_rate = successful_queries / total_queries if total_queries else 0
        total_cost = sum(r.cost_usd for r in results)
        total_tokens = sum(r.total_tokens for r in results)

        return BenchmarkReport(
            total_queries=total_queries,
            successful_queries=successful_queries,
            average_latency_ms=avg_latency,
            exact_match_rate=em_rate,
            execution_accuracy_rate=exec_rate,
            total_cost_usd=total_cost,
            total_tokens=total_tokens,
            results=results
        )
