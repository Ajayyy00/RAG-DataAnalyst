from typing import List, Optional
from pydantic import BaseModel

class EvaluationResult(BaseModel):
    id: str
    question: str
    gold_sql: str
    generated_sql: Optional[str]
    exact_match: bool
    execution_accuracy: bool
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    error: Optional[str] = None

class BenchmarkReport(BaseModel):
    total_queries: int
    successful_queries: int
    average_latency_ms: float
    exact_match_rate: float
    execution_accuracy_rate: float
    total_cost_usd: float
    total_tokens: int
    results: List[EvaluationResult]
