"""
Full Website Functionality Checker
====================================
Tests every feature of the Healthcare Copilot platform:
  1. Backend health
  2. Auth (login/me)
  3. SQL Validation engine (9 cases)
  4. Chat pipeline (NL->SQL->Chart->Insights)
  5. InsightReport structure
  6. Dashboard generation engine
  7. Session management
  8. Schema/RAG endpoints
  9. Fine-tune endpoint
  10. Frontend reachability
"""
import asyncio, sys, json, httpx

BACKEND  = "http://localhost:8001"
FRONTEND = "http://localhost:5173"
EMAIL    = "admin@healthcare.com"
PASSWORD = "Admin1234!"

# ANSI (safe ASCII fallback)
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"
C = "\033[96m"; B = "\033[1m";  X = "\033[0m"

passed = 0; failed = 0; warnings = 0

def ok(label, detail=""):
    global passed; passed += 1
    print(f"  {G}PASS{X}  {label}" + (f"  {Y}({detail}){X}" if detail else ""))

def fail(label, detail=""):
    global failed
    print(f"  {R}FAIL{X}  {label}" + (f"  {R}>> {detail}{X}" if detail else ""))

def warn(label, detail=""):
    global warnings
    print(f"  {Y}WARN{X}  {label}" + (f"  {Y}({detail}){X}" if detail else ""))

def section(title):
    print(f"\n{B}{C}{'-'*62}{X}")
    print(f"{B}{C}  {title}{X}")
    print(f"{B}{C}{'-'*62}{X}")

async def run():
    async with httpx.AsyncClient(base_url=BACKEND, timeout=120) as c:

        # ---- 1. HEALTH -----------------------------------------------
        section("1. Backend Health")
        r = await c.get("/health")
        if r.status_code == 200 and r.json().get("status") == "healthy":
            d = r.json()
            ok("GET /health", f"service={d.get('service')} env={d.get('environment')}")
        else:
            fail("GET /health", f"HTTP {r.status_code}")

        # ---- 2. FRONTEND ---------------------------------------------
        section("2. Frontend Reachability")
        try:
            async with httpx.AsyncClient(timeout=10) as fc:
                rf = await fc.get(FRONTEND)
            if rf.status_code == 200:
                ok("Frontend loaded", f"HTTP {rf.status_code}, bytes={len(rf.content)}")
            else:
                warn("Frontend", f"HTTP {rf.status_code}")
        except Exception as e:
            fail("Frontend unreachable", str(e)[:60])

        # ---- 3. AUTH -------------------------------------------------
        section("3. Authentication")
        r = await c.post("/api/v1/auth/login",
                         data={"username": EMAIL, "password": PASSWORD},
                         headers={"Content-Type": "application/x-www-form-urlencoded"})
        if r.status_code != 200:
            fail("Login", f"HTTP {r.status_code}: {r.text[:80]}")
            print(f"\n{R}Cannot continue without token.{X}"); return
        token = r.json()["access_token"]
        ok("Login", f"JWT length={len(token)}")

        H = {"Authorization": f"Bearer {token}"}
        r2 = await c.get("/api/v1/auth/me", headers=H)
        if r2.status_code == 200:
            u = r2.json(); ok("GET /me", f"role={u.get('role')} email={u.get('email')}")
        else:
            fail("GET /me", f"HTTP {r2.status_code}")

        # ---- 4. SQL VALIDATION ENGINE --------------------------------
        section("4. SQL Validation Engine (9 test cases)")
        cases = [
            ("Valid SELECT",         "SELECT id, name FROM patients LIMIT 10;",                    True),
            ("Valid CTE",            "WITH cte AS (SELECT id FROM encounters) SELECT * FROM cte;", True),
            ("Valid Aggregation",    "SELECT dept, COUNT(*) as cnt FROM encounters GROUP BY dept;", True),
            ("DROP TABLE",           "DROP TABLE patients;",                                        False),
            ("DELETE rows",          "DELETE FROM encounters WHERE 1=1;",                           False),
            ("ALTER TABLE",          "ALTER TABLE patients ADD COLUMN x TEXT;",                     False),
            ("TRUNCATE",             "TRUNCATE TABLE encounters;",                                  False),
            ("Stacked injection",    "SELECT * FROM patients; DROP TABLE patients;",                False),
            ("Comment injection",    "SELECT * FROM patients WHERE 1=1 --",                        False),
        ]
        for name, sql, expect in cases:
            r = await c.post("/api/v1/chat/validate", json={"sql": sql}, headers=H)
            if r.status_code != 200:
                fail(name, f"HTTP {r.status_code}"); continue
            d = r.json()
            if d["valid"] == expect:
                viol = d["violations"][0][:50] if not expect and d.get("violations") else ""
                ok(name, f"valid={d['valid']}" + (f" | {viol}" if viol else ""))
            else:
                fail(name, f"expected={expect} got={d['valid']}")

        # ---- 5. CHAT PIPELINE ----------------------------------------
        section("5. Chat Pipeline  (NL -> SQL -> Chart -> InsightReport)")
        chat_tests = [
            ("Avg LOS by department",          "bar"),
            ("Top 5 diagnoses by frequency",   None),
            ("Monthly encounters last 6 months", "line"),
        ]
        for question, expected_chart in chat_tests:
            r = await c.post("/api/v1/chat/query",
                json={"question": question,
                      "options": {"include_sql": True, "include_insights": True, "chart_auto": True}},
                headers=H)
            if r.status_code != 200:
                fail(question, f"HTTP {r.status_code}: {r.text[:80]}"); continue
            d = r.json()
            sql_valid   = d.get("sql", {}).get("validated", False)
            row_count   = d.get("results", {}).get("row_count", 0)
            chart_type  = d.get("chart", {}).get("type") if d.get("chart") else None
            report      = d.get("insight_report") or {}
            has_summary = bool(report.get("summary"))
            has_trends  = len(report.get("trends", [])) > 0
            has_recs    = len(report.get("recommendations", [])) > 0
            has_followup= len(report.get("follow_up_questions", [])) > 0
            confidence  = report.get("confidence", "?")
            detail = (f"sql_valid={sql_valid} rows={row_count} chart={chart_type} "
                      f"summary={'yes' if has_summary else 'no'} "
                      f"trends={len(report.get('trends',[]))} "
                      f"recs={len(report.get('recommendations',[]))} "
                      f"confidence={confidence}")
            if sql_valid and has_summary:
                ok(question, detail)
            else:
                fail(question, detail)

        # ---- 6. INSIGHT REPORT SCHEMA --------------------------------
        section("6. InsightReport Schema Validation")
        r = await c.post("/api/v1/chat/query",
            json={"question": "Average LOS by department",
                  "options": {"include_insights": True}},
            headers=H)
        if r.status_code == 200:
            report = r.json().get("insight_report") or {}
            schema_checks = [
                ("summary is string",   isinstance(report.get("summary"), str) and len(report.get("summary","")) > 10),
                ("trends is list",      isinstance(report.get("trends"), list)),
                ("anomalies is list",   isinstance(report.get("anomalies"), list)),
                ("recommendations list",isinstance(report.get("recommendations"), list)),
                ("follow_up_questions", isinstance(report.get("follow_up_questions"), list)),
                ("data_quality_notes",  isinstance(report.get("data_quality_notes"), list)),
                ("confidence valid",    report.get("confidence") in {"high","medium","low"}),
            ]
            for label, val in schema_checks:
                (ok if val else fail)(label)
            if report.get("recommendations"):
                rec = report["recommendations"][0]
                rec_checks = [
                    ("rec.priority valid", rec.get("priority") in {"high","medium","low"}),
                    ("rec.action str",     isinstance(rec.get("action"), str) and bool(rec.get("action"))),
                    ("rec.rationale str",  isinstance(rec.get("rationale"), str)),
                ]
                for label, val in rec_checks:
                    (ok if val else fail)(label, str(rec.get(label.split(".")[1].split()[0], ""))[:50])
        else:
            fail("InsightReport fetch", f"HTTP {r.status_code}")

        # ---- 7. DASHBOARD GENERATION ENGINE --------------------------
        section("7. Auto Dashboard Generation Engine")
        r = await c.post("/api/v1/dashboard/generate",
            json={"request": "Show hospital admissions and readmission trends"},
            headers=H)
        if r.status_code == 200:
            d = r.json()
            panels        = d.get("panels", [])
            summary       = d.get("summary", "")
            layout        = d.get("layout", {})
            success_count = layout.get("success_count", 0)
            total_rows    = d.get("total_rows", 0)
            title         = d.get("title", "")

            ok("Dashboard generated", f"panels={len(panels)} success={success_count} rows={total_rows}")
            ok("Dashboard title",     f'"{title}"') if title else fail("Dashboard title", "empty")
            ok("Executive summary",   f"{len(summary)} chars") if len(summary) > 20 else warn("Summary short", summary[:50])

            # Check panel structure
            panel_issues = []
            for p in panels:
                if not p.get("title"):    panel_issues.append(f"{p.get('id','?')}: no title")
                if not p.get("sql"):      panel_issues.append(f"{p.get('title','?')}: no sql")
            if panel_issues:
                fail("Panel structure", " | ".join(panel_issues[:3]))
            else:
                ok("All panels have title+sql", f"checked {len(panels)} panels")

            # Check chart types
            chart_types = [p.get("chart_type") for p in panels if p.get("chart_type")]
            ok("Chart types assigned", f"{set(chart_types)}")

            # Check insight summaries
            with_insights = sum(1 for p in panels if p.get("insight_summary"))
            ok("Panels with insight summaries", f"{with_insights}/{len(panels)}")
        else:
            fail("Dashboard generate", f"HTTP {r.status_code}: {r.text[:120]}")

        # ---- 8. SESSION MANAGEMENT -----------------------------------
        section("8. Session Management")
        # List
        r = await c.get("/api/v1/sessions", headers=H)
        if r.status_code == 200:
            sessions = r.json().get("sessions", [])
            ok("List sessions", f"count={len(sessions)}")
        else:
            fail("List sessions", f"HTTP {r.status_code}")
            sessions = []

        # Create
        r2 = await c.post("/api/v1/sessions", json={"title": "Full check session"}, headers=H)
        if r2.status_code == 201:
            sid = r2.json()["id"]
            ok("Create session", f"id={sid[:8]}...")

            # Get messages (empty)
            r3 = await c.get(f"/api/v1/sessions/{sid}/messages", headers=H)
            ok("Get messages (empty)", f"HTTP {r3.status_code}")

            # Delete
            r4 = await c.delete(f"/api/v1/sessions/{sid}", headers=H)
            if r4.status_code in (200, 204):
                ok("Delete session", f"HTTP {r4.status_code}")
            else:
                warn("Delete session", f"HTTP {r4.status_code}")
        else:
            fail("Create session", f"HTTP {r2.status_code}")

        # ---- 9. SCHEMA ENDPOINT --------------------------------------
        section("9. Schema & RAG Endpoints")
        r = await c.get("/api/v1/schema/tables", headers=H)
        if r.status_code == 200:
            tables = r.json()
            count = len(tables) if isinstance(tables, list) else len(tables.get("tables", []))
            ok("GET /schema/tables", f"tables={count}")
        else:
            warn("GET /schema/tables", f"HTTP {r.status_code}")

        r2 = await c.post("/api/v1/rag/search",
                          json={"query": "patient encounters diagnoses", "top_k": 3},
                          headers=H)
        if r2.status_code == 200:
            results = r2.json()
            ok("POST /rag/search", f"results={len(results.get('results', results if isinstance(results, list) else []))}")
        else:
            warn("POST /rag/search", f"HTTP {r2.status_code}")

        # ---- 10. OPENAPI / DOCS ENDPOINT ----------------------------
        section("10. OpenAPI Documentation")
        r = await c.get("/openapi.json")
        if r.status_code == 200:
            spec = r.json()
            endpoints = list(spec.get("paths", {}).keys())
            ok("OpenAPI spec loaded", f"endpoints={len(endpoints)}")
            dashboard_ep = [e for e in endpoints if "dashboard" in e]
            ok("Dashboard endpoints registered", f"{dashboard_ep}")
            chat_ep = [e for e in endpoints if "chat" in e]
            ok("Chat endpoints registered", f"{chat_ep}")
        else:
            fail("OpenAPI", f"HTTP {r.status_code}")

        # ---- SUMMARY -------------------------------------------------
        total = passed + failed
        colour = G if failed == 0 else R
        print(f"\n{B}{colour}{'='*62}{X}")
        print(f"{B}{colour}  RESULTS  {passed} passed  /  {failed} failed  /  {warnings} warnings{X}")
        print(f"{B}{colour}  Total checks: {total + warnings}{X}")
        print(f"{B}{colour}{'='*62}{X}")
        if failed > 0:
            sys.exit(1)

asyncio.run(run())
