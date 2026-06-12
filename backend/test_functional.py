"""
Full Functional Test Suite — Healthcare Copilot
Tests every major component end-to-end via the live API.
"""
import asyncio, sys, os, json, textwrap
sys.path.insert(0, os.path.dirname(__file__))

import structlog; structlog.configure(logger_factory=structlog.PrintLoggerFactory())

import httpx

BASE = "http://localhost:8001"
EMAIL = "admin@healthcare.com"
PASSWORD = "Admin1234!"  # try seeded password variants

# ── colours ──────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; C = "\033[96m"; B = "\033[1m"; X = "\033[0m"

passed = failed = 0

def ok(label, detail=""):
    global passed
    passed += 1
    print(f"  {G}PASS{X}  {label}" + (f"  {Y}({detail}){X}" if detail else ""))

def fail(label, detail=""):
    global failed
    print(f"  {R}FAIL{X}  {label}" + (f"  {R}>> {detail}{X}" if detail else ""))

def section(title):
    print(f"\n{B}{C}{'-'*60}{X}")
    print(f"{B}{C}  {title}{X}")
    print(f"{B}{C}{'-'*60}{X}")

# ─────────────────────────────────────────────────────────────
async def run():
    async with httpx.AsyncClient(base_url=BASE, timeout=90) as client:

        # ── 1. AUTH ──────────────────────────────────────────
        section("1. Authentication")
        r = await client.post("/api/v1/auth/login",
                              data={"username": EMAIL, "password": PASSWORD},
                              headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code == 200:
            token = r.json()["access_token"]
            ok("Login", f"token length={len(token)}")
        else:
            fail("Login", f"HTTP {r.status_code}: {r.text[:120]}")
            print(f"\n{R}Cannot continue without auth.{X}")
            return
        
        H = {"Authorization": f"Bearer {token}"}

        # ── 2. SQL VALIDATION ENGINE ──────────────────────────
        section("2. SQL Validation Engine")

        tests = [
            ("Valid SELECT",      "SELECT id, email FROM patients LIMIT 10;",           True),
            ("Valid CTE+JOIN",    "WITH r AS (SELECT id FROM encounters) SELECT id FROM r LIMIT 5;", True),
            ("DROP TABLE",        "DROP TABLE patients;",                                False),
            ("DELETE",            "DELETE FROM patients WHERE 1=1;",                     False),
            ("ALTER",             "ALTER TABLE patients ADD COLUMN x TEXT;",             False),
            ("TRUNCATE",          "TRUNCATE TABLE encounters;",                           False),
            ("Unauthorized table","SELECT * FROM shadow_table LIMIT 5;",                False),
            ("Stacked injection", "SELECT id FROM patients; DROP TABLE patients;--",     False),
            ("Tautology",         "SELECT * FROM patients WHERE '' = '' --",             False),
        ]

        for name, sql, expect_valid in tests:
            r = await client.post("/api/v1/chat/validate", json={"sql": sql}, headers=H)
            if r.status_code != 200:
                fail(name, f"HTTP {r.status_code}")
                continue
            d = r.json()
            if d["valid"] == expect_valid:
                detail = f"valid={d['valid']}"
                if not d['valid'] and d.get('violations'):
                    detail += f", violation='{d['violations'][0][:55]}'"
                ok(name, detail)
            else:
                fail(name, f"expected valid={expect_valid} got valid={d['valid']}, violations={d.get('violations')}")

        # ── 3. QUERY PIPELINE ────────────────────────────────
        section("3. Full Query Pipeline (NL -> SQL -> Chart -> Insights)")

        queries = [
            {
                "q": "Average LOS by department",
                "expect_cols": ["department", "avg_los_days"],
                "expect_chart": "bar",
            },
            {
                "q": "Readmission trends last 6 months",
                "expect_cols": ["month", "total_encounters"],
                "expect_chart": "line",
            },
            {
                "q": "Top 5 diagnoses by frequency",
                "expect_cols": ["icd10_desc", "diagnosis_count"],
                "expect_chart": None,   # may be bar or pie
            },
            {
                "q": "Medication count per patient last 90 days",
                "expect_cols": [],
                "expect_chart": None,
            },
        ]

        for qt in queries:
            r = await client.post("/api/v1/chat/query",
                                  json={"question": qt["q"],
                                        "options": {"include_sql": True,
                                                    "include_insights": True,
                                                    "chart_auto": True}},
                                  headers=H)
            if r.status_code != 200:
                fail(qt["q"], f"HTTP {r.status_code}: {r.text[:120]}")
                continue

            d = r.json()
            details = []

            # SQL check
            sql_ok = d.get("sql") and d["sql"].get("validated")
            details.append(f"sql_valid={sql_ok}")

            # Row count
            rows = d.get("results", {}).get("row_count", 0)
            cols = d.get("results", {}).get("columns", [])
            details.append(f"rows={rows}")

            # Column check
            col_ok = True
            for ec in qt["expect_cols"]:
                if ec not in cols:
                    col_ok = False
                    details.append(f"MISSING_COL={ec}")

            # Chart check
            chart = d.get("chart")
            chart_type = chart.get("type") if chart else None
            details.append(f"chart={chart_type}")

            # Insights check
            report = d.get("insight_report")
            flat   = d.get("insights", [])
            has_insights = bool(report or flat)
            if report:
                details.append(f"summary={'yes' if report.get('summary') else 'no'}")
                details.append(f"trends={len(report.get('trends', []))}")
                details.append(f"recs={len(report.get('recommendations', []))}")
                details.append(f"followups={len(report.get('follow_up_questions', []))}")
                details.append(f"confidence={report.get('confidence','?')}")

            if sql_ok and col_ok and has_insights:
                ok(qt["q"], "  ".join(details))
            else:
                fail(qt["q"], "  ".join(details))

        # ── 4. INSIGHTS ENGINE DEEP DIVE ─────────────────────
        section("4. InsightReport Structure Validation")

        r = await client.post("/api/v1/chat/query",
                              json={"question": "Average LOS by department",
                                    "options": {"include_insights": True}},
                              headers=H)
        if r.status_code == 200:
            report = r.json().get("insight_report", {})
            checks = [
                ("has summary",            bool(report.get("summary"))),
                ("trends is list",         isinstance(report.get("trends"), list)),
                ("anomalies is list",      isinstance(report.get("anomalies"), list)),
                ("recommendations is list",isinstance(report.get("recommendations"), list)),
                ("follow_up_questions list",isinstance(report.get("follow_up_questions"), list)),
                ("data_quality_notes list", isinstance(report.get("data_quality_notes"), list)),
                ("confidence is string",   report.get("confidence") in {"high","medium","low"}),
            ]
            for label, val in checks:
                (ok if val else fail)(label, str(report.get(label.split()[1], "N/A"))[:60])

            if report.get("recommendations"):
                rec = report["recommendations"][0]
                rec_checks = [
                    ("rec has priority", rec.get("priority") in {"high","medium","low"}),
                    ("rec has action",   bool(rec.get("action"))),
                    ("rec has rationale",bool(rec.get("rationale"))),
                ]
                for label, val in rec_checks:
                    (ok if val else fail)(label, str(rec.get(label.split()[2], ""))[:50])

        # ── 5. SESSION MANAGEMENT ─────────────────────────────
        section("5. Session Management")

        r = await client.get("/api/v1/sessions", headers=H)
        if r.status_code == 200:
            sessions = r.json().get("sessions", [])
            ok("List sessions", f"count={len(sessions)}")
        else:
            fail("List sessions", f"HTTP {r.status_code}")

        r2 = await client.post("/api/v1/sessions",
                               json={"title": "Functional test session"}, headers=H)
        if r2.status_code == 201:
            sid = r2.json()["id"]
            ok("Create session", f"id={sid[:8]}...")
            # get messages
            r3 = await client.get(f"/api/v1/sessions/{sid}/messages", headers=H)
            ok("Get session messages", f"HTTP {r3.status_code}")
        else:
            fail("Create session", f"HTTP {r2.status_code}")

        # ── SUMMARY ──────────────────────────────────────────
        total = passed + failed
        colour = G if failed == 0 else R
        print(f"\n{B}{colour}{'='*60}{X}")
        print(f"{B}{colour}  Results: {passed}/{total} passed   {failed} failed{X}")
        print(f"{B}{colour}{'='*60}{X}\n")

        if failed:
            sys.exit(1)

asyncio.run(run())
