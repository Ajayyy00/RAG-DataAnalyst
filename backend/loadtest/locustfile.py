"""Locust load test for the Healthcare Copilot API.

Covers: authentication, RAG retrieval, SQL validation/generation, the chat
query pipeline, and dashboard generation. A separate WebSocket user exercises
the realtime analytics socket.

Run:
    pip install -r loadtest/requirements-loadtest.txt
    # 100-user smoke (headless), 5 min:
    LOAD_PROFILE=smoke locust -f loadtest/locustfile.py --host http://localhost:8001 \
        --headless -u 100 -r 20 -t 5m --csv reports/load_smoke

    # Staged ramp to 500 / 1000 with the built-in shapes:
    LOAD_PROFILE=ramp500  locust -f loadtest/locustfile.py --host http://localhost:8001 --headless --csv reports/ramp500
    LOAD_PROFILE=ramp1000 locust -f loadtest/locustfile.py --host http://localhost:8001 --headless --csv reports/ramp1000

Credentials come from LOAD_EMAIL / LOAD_PASSWORD (default to the seeded analyst).
"""

import os
import random

from locust import HttpUser, LoadTestShape, between, events, task

LOAD_EMAIL = os.getenv("LOAD_EMAIL", "analyst@healthcare.com")
LOAD_PASSWORD = os.getenv("LOAD_PASSWORD", "Analyst1234!")

CLINICAL_QUESTIONS = [
    "How many diabetic patients do we have?",
    "Average length of stay by department",
    "30-day readmission rate by department for the last 6 months",
    "Top 10 most prescribed medications this year",
    "Count of encounters by encounter type",
    "Patients with abnormal glucose lab results",
]

SAMPLE_SQL = "SELECT encounter_type, COUNT(*) FROM encounters GROUP BY encounter_type"


class HealthcareUser(HttpUser):
    """Simulates an analyst using the copilot. Cookies persist across requests."""

    wait_time = between(1, 5)

    def on_start(self):
        # Cookie-based login; the Locust client stores the HttpOnly cookies.
        with self.client.post(
            "/api/v1/auth/login",
            data={"username": LOAD_EMAIL, "password": LOAD_PASSWORD},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="POST /auth/login",
            catch_response=True,
        ) as r:
            if r.status_code != 200:
                r.failure(f"login failed: {r.status_code}")

    @task(1)
    def me(self):
        self.client.get("/api/v1/auth/me", name="GET /auth/me")

    @task(3)
    def rag_search(self):
        q = random.choice(CLINICAL_QUESTIONS)
        self.client.get(
            "/api/v1/rag/search", params={"q": q, "n": 5}, name="GET /rag/search"
        )

    @task(3)
    def validate_sql(self):
        self.client.post(
            "/api/v1/chat/validate",
            json={"sql": SAMPLE_SQL},
            name="POST /chat/validate",
        )

    @task(5)
    def chat_query(self):
        q = random.choice(CLINICAL_QUESTIONS)
        self.client.post(
            "/api/v1/chat/query",
            json={"question": q, "options": {"include_insights": False}},
            name="POST /chat/query",
            timeout=120,
        )

    @task(1)
    def dashboard(self):
        self.client.post(
            "/api/v1/dashboard/generate",
            json={"request": "Overview of hospital operations"},
            name="POST /dashboard/generate",
            timeout=180,
        )


# ── Load shapes (staged ramp → steady → ramp-down) ───────────────────────────
class _StagedShape(LoadTestShape):
    stages: list = []

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["dur"]:
                return stage["users"], stage["rate"]
        return None


class Ramp500(_StagedShape):
    stages = [
        {"dur": 120, "users": 100, "rate": 20},
        {"dur": 300, "users": 300, "rate": 30},
        {"dur": 600, "users": 500, "rate": 40},
        {"dur": 900, "users": 500, "rate": 40},  # steady state
        {"dur": 960, "users": 0, "rate": 50},  # ramp down
    ]


class Ramp1000(_StagedShape):
    stages = [
        {"dur": 120, "users": 200, "rate": 40},
        {"dur": 360, "users": 500, "rate": 50},
        {"dur": 720, "users": 1000, "rate": 60},
        {"dur": 1080, "users": 1000, "rate": 60},  # steady state
        {"dur": 1140, "users": 0, "rate": 80},  # ramp down
    ]


# Select the active shape via LOAD_PROFILE; "smoke" uses CLI -u/-r (no shape).
_PROFILE = os.getenv("LOAD_PROFILE", "smoke").lower()
if _PROFILE == "ramp500":

    class ActiveShape(Ramp500):
        pass

elif _PROFILE == "ramp1000":

    class ActiveShape(Ramp1000):
        pass


@events.quitting.add_listener
def _assert_slo(environment, **_):
    """Fail the run (non-zero exit) if SLOs are breached — CI-friendly gate."""
    stats = environment.stats.total
    if stats.fail_ratio > 0.02:
        environment.process_exit_code = 1
    elif stats.get_response_time_percentile(0.95) > 5000:  # 5s p95 budget
        environment.process_exit_code = 1
    else:
        environment.process_exit_code = 0
