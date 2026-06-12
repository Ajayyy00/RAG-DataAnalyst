"""
Tests for the SQL Validation & Safety Engine.
Run: .venv\Scripts\python.exe test_validation_engine.py
"""

import sys, textwrap
from dataclasses import dataclass
from typing import List, Optional

# ── bootstrap path so we can import the service directly ──────
import os
sys.path.insert(0, os.path.dirname(__file__))

# Monkey-patch structlog so we don't need the full app context
import structlog
structlog.configure(logger_factory=structlog.PrintLoggerFactory())

from app.services.sql_validation_service import (
    SQLValidationService, RiskLevel, validate_sql
)

svc = SQLValidationService()

# ── Colour helpers ────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"


@dataclass
class Case:
    name: str
    sql: str
    expect_valid: bool
    expect_violation_fragments: List[str] = None
    expect_warning_fragments: List[str] = None
    max_complexity: Optional[int] = None


CASES: List[Case] = [

    # ── SHOULD PASS ───────────────────────────────────────────

    Case(
        "Simple SELECT",
        "SELECT id, email FROM patients LIMIT 10;",
        expect_valid=True,
    ),
    Case(
        "SELECT with WHERE",
        "SELECT * FROM encounters WHERE encounter_type = 'inpatient' LIMIT 100;",
        expect_valid=True,
    ),
    Case(
        "Aggregation with GROUP BY",
        """
        SELECT department_id, COUNT(*) AS cnt, AVG(total_charge) AS avg_charge
        FROM encounters
        WHERE discharge_date >= CURRENT_DATE - INTERVAL '30 days'
        GROUP BY department_id
        ORDER BY cnt DESC
        LIMIT 20;
        """,
        expect_valid=True,
    ),
    Case(
        "CTE + JOIN",
        """
        WITH recent AS (
            SELECT id, patient_id, discharge_date
            FROM encounters
            WHERE encounter_type = 'inpatient'
        )
        SELECT p.id, p.first_name, r.discharge_date
        FROM patients p
        JOIN recent r ON r.patient_id = p.id
        LIMIT 50;
        """,
        expect_valid=True,
    ),
    Case(
        "Window function",
        """
        SELECT
            patient_id,
            admit_date,
            ROW_NUMBER() OVER (PARTITION BY patient_id ORDER BY admit_date) AS rn
        FROM encounters
        LIMIT 100;
        """,
        expect_valid=True,
    ),
    Case(
        "Subquery in FROM",
        """
        SELECT dept, total
        FROM (
            SELECT department_id AS dept, COUNT(*) AS total
            FROM encounters
            GROUP BY department_id
        ) sub
        ORDER BY total DESC
        LIMIT 10;
        """,
        expect_valid=True,
    ),
    Case(
        "LIMIT auto-injection (no LIMIT clause)",
        "SELECT id FROM patients;",
        expect_valid=True,
        expect_warning_fragments=["LIMIT 1000 automatically injected"],
    ),

    # ── SHOULD FAIL — DML/DDL ─────────────────────────────────

    Case(
        "DROP TABLE",
        "DROP TABLE patients;",
        expect_valid=False,
        expect_violation_fragments=["DROP"],
    ),
    Case(
        "DELETE statement",
        "DELETE FROM patients WHERE id = '123';",
        expect_valid=False,
        expect_violation_fragments=["DELETE"],
    ),
    Case(
        "ALTER TABLE",
        "ALTER TABLE patients ADD COLUMN ssn TEXT;",
        expect_valid=False,
        expect_violation_fragments=["ALTER"],
    ),
    Case(
        "TRUNCATE TABLE",
        "TRUNCATE TABLE encounters;",
        expect_valid=False,
        expect_violation_fragments=["TRUNCATE"],
    ),
    Case(
        "INSERT statement",
        "INSERT INTO patients (id, email) VALUES ('x', 'y@z.com');",
        expect_valid=False,
        expect_violation_fragments=["INSERT"],
    ),
    Case(
        "UPDATE statement",
        "UPDATE patients SET email = 'hacker@evil.com' WHERE 1=1;",
        expect_valid=False,
        expect_violation_fragments=["Tautology"],
    ),
    Case(
        "CREATE TABLE",
        "CREATE TABLE shadow_copy AS SELECT * FROM patients;",
        expect_valid=False,
        expect_violation_fragments=["CREATE"],
    ),

    # ── SHOULD FAIL — Injection ───────────────────────────────

    Case(
        "Stacked statement injection",
        "SELECT id FROM patients; DROP TABLE patients;--",
        expect_valid=False,
        expect_violation_fragments=["stacked"],
    ),
    Case(
        "Tautology injection (OR 1=1)",
        "SELECT * FROM patients WHERE id = '' OR 1=1 --",
        expect_valid=False,
        expect_violation_fragments=["Tautology"],
    ),
    Case(
        "Comment probe (--)",
        "SELECT * FROM patients -- comment injection",
        expect_valid=False,
        expect_violation_fragments=["comment"],
    ),

    # ── SHOULD FAIL — Unauthorized tables ─────────────────────

    Case(
        "Unauthorized table reference",
        "SELECT * FROM shadow_table LIMIT 10;",
        expect_valid=False,
        expect_violation_fragments=["shadow_table"],
    ),
    Case(
        "System catalog access",
        "SELECT * FROM pg_catalog.pg_tables LIMIT 10;",
        expect_valid=False,
    ),

    # ── SHOULD FAIL — Complexity ──────────────────────────────

    Case(
        "Overly complex query (many joins)",
        """
        SELECT *
        FROM encounters e
        JOIN patients p ON p.id = e.patient_id
        JOIN providers pv ON pv.id = e.provider_id
        JOIN departments d ON d.id = e.department_id
        JOIN diagnoses dx ON dx.encounter_id = e.id
        JOIN medications m ON m.encounter_id = e.id
        JOIN lab_results lr ON lr.encounter_id = e.id
        JOIN vital_signs vs ON vs.encounter_id = e.id
        JOIN readmissions r ON r.index_encounter_id = e.id
        JOIN claims c ON c.encounter_id = e.id
        JOIN (SELECT patient_id, MAX(admit_date) AS last FROM encounters GROUP BY patient_id) last_enc ON last_enc.patient_id = p.id
        JOIN (SELECT patient_id, COUNT(*) AS dx_cnt FROM diagnoses GROUP BY patient_id) dx_cnt ON dx_cnt.patient_id = p.id
        LIMIT 50;
        """,
        expect_valid=False,
        expect_violation_fragments=["complexity"],
    ),

    # ── SHOULD FAIL — Excessive LIMIT ─────────────────────────

    Case(
        "Excessive LIMIT value",
        "SELECT id FROM patients LIMIT 9999999;",
        expect_valid=False,
        expect_violation_fragments=["100,000"],
    ),
]


# ── Runner ────────────────────────────────────────────────────

def run_tests() -> None:
    passed = 0
    failed = 0

    print(f"\n{BOLD}{CYAN}{'='*65}{RESET}")
    print(f"{BOLD}{CYAN}  SQL Validation & Safety Engine — Test Suite{RESET}")
    print(f"{BOLD}{CYAN}{'='*65}{RESET}\n")

    for i, case in enumerate(CASES, 1):
        sql = textwrap.dedent(case.sql).strip()
        result = svc.validate(sql)

        ok = result.is_valid == case.expect_valid

        # Check violation fragments
        if ok and case.expect_violation_fragments:
            all_text = " ".join(result.violations).lower()
            for frag in case.expect_violation_fragments:
                if frag.lower() not in all_text:
                    ok = False
                    break

        # Check warning fragments
        if ok and case.expect_warning_fragments:
            all_text = " ".join(result.warnings).lower()
            for frag in case.expect_warning_fragments:
                if frag.lower() not in all_text:
                    ok = False
                    break

        # Check max complexity
        if ok and case.max_complexity is not None:
            if result.complexity_score > case.max_complexity:
                ok = False

        status_icon = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        validity_str = f"valid={result.is_valid}  score={result.complexity_score}  risk={result.risk_level.name}"

        print(f"  [{i:02d}] {status_icon}  {case.name}")
        print(f"        {validity_str}")

        if not ok:
            failed += 1
            if result.violations:
                print(f"        {RED}Violations:{RESET}")
                for v in result.violations:
                    print(f"          - {v}")
            if result.warnings:
                print(f"        {YELLOW}Warnings:{RESET}")
                for w in result.warnings:
                    print(f"          - {w}")
            if case.expect_violation_fragments:
                print(f"        {YELLOW}Expected fragments:{RESET} {case.expect_violation_fragments}")
        else:
            passed += 1
            if result.warnings:
                for w in result.warnings:
                    print(f"        {YELLOW}WARN: {w}{RESET}")

        print()

    total = passed + failed
    colour = GREEN if failed == 0 else RED
    print(f"{BOLD}{colour}Results: {passed}/{total} passed{RESET}")
    if failed:
        print(f"{RED}  {failed} test(s) failed.{RESET}")
    print()

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    run_tests()
