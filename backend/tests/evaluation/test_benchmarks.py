import pytest

from app.db.session import AsyncSessionLocal
from app.services.sql_evaluator import SQLEvaluatorService


@pytest.mark.asyncio
async def test_text_to_sql_benchmark():
    """
    Automated test to ensure the Agentic SQL pipeline maintains high accuracy.
    This test runs the benchmark suite and asserts that Execution Accuracy is >= 80%.
    """
    async with AsyncSessionLocal() as db:
        evaluator = SQLEvaluatorService(db)
        # Using a relative path that works from the backend root
        report = await evaluator.run_benchmark(
            "tests/evaluation/benchmark_dataset.json"
        )

    print(f"\nBenchmark Results:")
    print(f"Total Queries: {report.total_queries}")
    print(f"Successful Queries: {report.successful_queries}")
    print(f"Exact Match Rate: {report.exact_match_rate * 100:.2f}%")
    print(f"Execution Accuracy: {report.execution_accuracy_rate * 100:.2f}%")
    print(f"Average Latency: {report.average_latency_ms:.2f} ms")
    print(f"Total Cost: ${report.total_cost_usd:.6f}")

    assert report.total_queries > 0, "Benchmark dataset is empty."
    assert (
        report.execution_accuracy_rate >= 0.80
    ), f"Execution accuracy {report.execution_accuracy_rate*100}% fell below 80% threshold."
