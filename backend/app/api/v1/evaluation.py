from fastapi import APIRouter

from app.dependencies import CurrentUser, DbSession
from app.schemas.evaluation import BenchmarkReport
from app.services.sql_evaluator import SQLEvaluatorService

router = APIRouter()


@router.post(
    "/run",
    response_model=BenchmarkReport,
    summary="Run the Text-to-SQL Benchmark Evaluation Suite",
)
async def run_evaluation(
    db: DbSession,
    current_user: CurrentUser,
) -> BenchmarkReport:
    """Triggers the evaluation engine on the benchmark dataset."""
    evaluator = SQLEvaluatorService(db, current_user)
    report = await evaluator.run_benchmark()
    return report
