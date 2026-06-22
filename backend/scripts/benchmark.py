#!/usr/bin/env python
"""
Analytics query benchmark.
==========================
Measures end-to-end SQL latency for representative copilot/BI queries against
the seeded Supabase/Postgres database and writes a Markdown report.

    python scripts/benchmark.py                 # default 7 runs/query
    python scripts/benchmark.py --runs 15 --out docs/PERFORMANCE_REPORT.md

Latency here is the database execution path (the component that scales with data
volume). The RAG + text-to-SQL LLM latency is measured separately by the running
service's Prometheus metrics (agentic_sql_step_latency_seconds).
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import asyncpg

from app.config import get_settings

settings = get_settings()

QUERIES = {
    "Q1 patient count": "SELECT count(*) FROM patients",
    "Q2 most prescribed meds (30d)": """
        SELECT drug_name, count(*) n FROM medications
        WHERE start_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY drug_name ORDER BY n DESC LIMIT 10
    """,
    "Q3 readmission trend (6mo)": """
        SELECT date_trunc('month', e.admit_date) m,
               count(DISTINCT r.index_encounter_id) readmits,
               count(DISTINCT e.id) inpt
        FROM encounters e
        LEFT JOIN readmissions r ON r.index_encounter_id = e.id
        WHERE e.encounter_type='Inpatient'
          AND e.admit_date >= CURRENT_DATE - INTERVAL '6 months'
        GROUP BY 1 ORDER BY 1
    """,
    "Q4 diabetic cohort + avg A1c": """
        SELECT count(DISTINCT d.patient_id) pts, round(avg(l.numeric_value),2) avg_a1c
        FROM diagnoses d
        JOIN lab_results l ON l.patient_id = d.patient_id AND l.loinc_code='4548-4'
        WHERE d.icd10_code IN ('E11.9','E11.65')
    """,
    "Q5 hospital utilization": """
        SELECT f.name, count(e.id) encounters, round(sum(e.total_charge),2) charges
        FROM facilities f
        JOIN departments dp ON dp.facility_id = f.id
        JOIN encounters e ON e.department_id = dp.id
        GROUP BY f.name ORDER BY encounters DESC LIMIT 20
    """,
    "Q6 payer revenue mix": """
        SELECT payer_name, count(*) claims, round(sum(paid_amount),2) paid,
               round(100.0*sum(CASE WHEN claim_status='Denied' THEN 1 ELSE 0 END)/count(*),1) denial_pct
        FROM claims GROUP BY payer_name ORDER BY paid DESC
    """,
    "Q7 abnormal labs by test": """
        SELECT test_name, count(*) n FROM lab_results
        WHERE abnormal_flag IN ('H','HH','L','LL')
        GROUP BY test_name ORDER BY n DESC LIMIT 15
    """,
    "Q8 top chronic diagnoses": """
        SELECT icd10_code, icd10_desc, count(DISTINCT patient_id) pts
        FROM diagnoses WHERE is_chronic GROUP BY 1,2 ORDER BY pts DESC LIMIT 15
    """,
}


async def run(runs: int, out: str | None, schema: str = "public") -> None:
    user, password, host, port, db = settings.db_components
    conn = await asyncpg.connect(
        user=user,
        password=password,
        host=host,
        port=port,
        database=db,
        ssl=settings.asyncpg_ssl,
        statement_cache_size=0,
    )
    if schema and schema != "public":
        await conn.execute(f"SET search_path TO {schema}, public")
    try:
        db_size = await conn.fetchval(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
        total_rows = 0
        for t in (
            "patients",
            "encounters",
            "diagnoses",
            "lab_results",
            "medications",
            "claims",
        ):
            try:
                total_rows += await conn.fetchval(f"SELECT count(*) FROM {t}")
            except Exception:
                pass

        results = []
        for name, sql in QUERIES.items():
            await conn.fetch(sql)  # warm-up (cache plans/pages)
            times = []
            for _ in range(runs):
                t0 = time.perf_counter()
                await conn.fetch(sql)
                times.append((time.perf_counter() - t0) * 1000)
            times.sort()
            results.append(
                (
                    name,
                    min(times),
                    statistics.median(times),
                    times[min(len(times) - 1, int(len(times) * 0.95))],
                    max(times),
                )
            )
            print(
                f"  {name:<34} p50={statistics.median(times):8.1f}ms  "
                f"p95={times[min(len(times)-1,int(len(times)*0.95))]:8.1f}ms"
            )
    finally:
        await conn.close()

    lines = [
        "# Performance Benchmark Report",
        "",
        f"- Database size: **{db_size}**",
        f"- Core fact rows (patients+encounters+dx+labs+meds+claims): **{total_rows:,}**",
        f"- Runs per query: {runs}  ·  warm cache",
        "",
        "| Query | min | p50 | p95 | max |",
        "|---|--:|--:|--:|--:|",
    ]
    for name, mn, p50, p95, mx in results:
        lines.append(f"| {name} | {mn:.1f} | {p50:.1f} | {p95:.1f} | {mx:.1f} | (ms)")
    report = "\n".join(lines) + "\n"
    print("\n" + report)
    if out:
        path = (ROOT.parent / out) if not Path(out).is_absolute() else Path(out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        print(f"Wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark analytics queries")
    ap.add_argument("--runs", type=int, default=7)
    ap.add_argument("--out", default=None, help="Write Markdown report to this path")
    ap.add_argument("--schema", default="public")
    args = ap.parse_args()
    asyncio.run(run(args.runs, args.out, args.schema))


if __name__ == "__main__":
    main()
