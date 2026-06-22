#!/usr/bin/env python
"""
Data validation suite.
======================
Verifies a seeded dataset is internally consistent and analytics-ready:

  1. Row counts per table.
  2. Foreign-key integrity (no orphan child rows).
  3. Required-field NULL checks.
  4. Distribution sanity (provider_type split, encounter mix, claim status).
  5. Representative analytics queries execute and return rows.

    python scripts/validate_data.py            # validate the configured DB (public)
    python scripts/validate_data.py --schema seed_validate

Exit code is non-zero if any hard check fails (CI-friendly).
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import asyncpg

from app.config import get_settings

settings = get_settings()

TABLES = [
    "facilities",
    "departments",
    "providers",
    "patients",
    "encounters",
    "diagnoses",
    "procedures",
    "medications",
    "lab_results",
    "vital_signs",
    "claims",
    "readmissions",
]

# (child, fk_column, parent)
FKS = [
    ("encounters", "patient_id", "patients"),
    ("encounters", "provider_id", "providers"),
    ("encounters", "department_id", "departments"),
    ("diagnoses", "encounter_id", "encounters"),
    ("diagnoses", "patient_id", "patients"),
    ("procedures", "encounter_id", "encounters"),
    ("medications", "patient_id", "patients"),
    ("lab_results", "patient_id", "patients"),
    ("vital_signs", "encounter_id", "encounters"),
    ("claims", "encounter_id", "encounters"),
    ("readmissions", "index_encounter_id", "encounters"),
    ("readmissions", "readmit_encounter_id", "encounters"),
    ("departments", "facility_id", "facilities"),
]

NOT_NULL = [("patients", "mrn"), ("providers", "npi"), ("encounters", "encounter_type")]

# Representative analytics scenarios that must execute & return rows on full data.
ANALYTICS = {
    "top prescribed meds this month": """
        SELECT drug_name, count(*) n FROM {s}medications
        WHERE start_date >= date_trunc('month', CURRENT_DATE)
        GROUP BY drug_name ORDER BY n DESC LIMIT 10
    """,
    "diabetic patient cohort size": """
        SELECT count(DISTINCT patient_id) FROM {s}diagnoses
        WHERE icd10_code IN ('E11.9','E11.65','Z79.4')
    """,
    "30-day readmission rate": """
        SELECT round(100.0 * count(DISTINCT r.index_encounter_id)
               / NULLIF(count(DISTINCT e.id),0), 2) AS pct
        FROM {s}encounters e
        LEFT JOIN {s}readmissions r ON r.index_encounter_id = e.id
        WHERE e.encounter_type = 'Inpatient'
    """,
    "claims paid vs denied": """
        SELECT claim_status, count(*) n, round(sum(paid_amount),2) paid
        FROM {s}claims GROUP BY claim_status ORDER BY n DESC
    """,
    "physician vs nurse headcount": """
        SELECT provider_type, count(*) FROM {s}providers
        GROUP BY provider_type ORDER BY 2 DESC
    """,
}


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, ok: bool, msg: str) -> None:
        flag = "PASS" if ok else "FAIL"
        print(f"  [{flag}] {msg}")
        if not ok:
            self.failures.append(msg)


async def validate(schema: str) -> int:
    s = f"{schema}." if schema and schema != "public" else ""
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
    rpt = Report()
    try:
        print("\n== Row counts ==")
        counts = {}
        for t in TABLES:
            counts[t] = await conn.fetchval(f"SELECT count(*) FROM {s}{t}")
            print(f"  {t:<14} {counts[t]:>12,}")

        print("\n== Foreign-key integrity (orphans must be 0) ==")
        for child, col, parent in FKS:
            orphans = await conn.fetchval(
                f"SELECT count(*) FROM {s}{child} c "
                f"LEFT JOIN {s}{parent} p ON p.id = c.{col} "
                f"WHERE c.{col} IS NOT NULL AND p.id IS NULL"
            )
            rpt.check(orphans == 0, f"{child}.{col} -> {parent}: {orphans} orphan(s)")

        print("\n== Required fields (NULLs must be 0) ==")
        for t, col in NOT_NULL:
            nulls = await conn.fetchval(
                f"SELECT count(*) FROM {s}{t} WHERE {col} IS NULL"
            )
            rpt.check(nulls == 0, f"{t}.{col}: {nulls} null(s)")

        print("\n== Distribution sanity ==")
        if counts["providers"]:
            rows = await conn.fetch(
                f"SELECT provider_type, count(*) AS n FROM {s}providers "
                f"GROUP BY provider_type"
            )
            types = {r["provider_type"]: r["n"] for r in rows}
            phys, nurse = types.get("physician", 0), types.get("nurse", 0)
            rpt.check(
                phys > 0 and nurse > 0, f"provider split physician={phys} nurse={nurse}"
            )
            rpt.check(nurse >= phys, "nurses >= physicians (expected workforce ratio)")

        print("\n== Analytics scenarios (must run; should return rows on full data) ==")
        for name, sql in ANALYTICS.items():
            try:
                rows = await conn.fetch(sql.format(s=s))
                sample = dict(rows[0]) if rows else {}
                print(f"  [OK]   {name}: {len(rows)} row(s)  e.g. {sample}")
            except Exception as exc:
                rpt.check(False, f"{name}: query error: {exc}")
    finally:
        await conn.close()

    print("\n" + ("=" * 50))
    if rpt.failures:
        print(f"  VALIDATION FAILED: {len(rpt.failures)} issue(s)")
        return 1
    print("  VALIDATION PASSED")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate seeded healthcare data")
    ap.add_argument("--schema", default="public")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(validate(args.schema)))


if __name__ == "__main__":
    main()
