# Load & Performance Testing

Locust-based suite exercising auth, RAG, SQL validation/generation, chat, and
dashboard endpoints, plus a standalone WebSocket probe.

## Setup
```bash
pip install -r loadtest/requirements-loadtest.txt
# seed users so logins succeed
python -m app.scripts.seed_db
```

## Profiles

| Profile | Peak users | Spawn rate | Duration | Command |
|---|---|---|---|---|
| smoke   | 100  | 20/s | ~5 min  | `LOAD_PROFILE=smoke locust -f loadtest/locustfile.py --host $HOST --headless -u 100 -r 20 -t 5m --csv reports/smoke` |
| ramp500 | 500  | staged | ~16 min | `LOAD_PROFILE=ramp500 locust -f loadtest/locustfile.py --host $HOST --headless --csv reports/ramp500` |
| ramp1000| 1000 | staged | ~19 min | `LOAD_PROFILE=ramp1000 locust -f loadtest/locustfile.py --host $HOST --headless --csv reports/ramp1000` |

`HOST=http://localhost:8001`. The `ramp*` profiles drive the user count via the
built-in `LoadTestShape` classes (staged ramp → steady → ramp-down).

### WebSockets
```bash
python loadtest/ws_loadtest.py --connections 500 --duration 60 --token <ACCESS_JWT>
```

## SLO gate
The run exits non-zero (CI-friendly) when, across the whole run:
- error rate > **2%**, or
- p95 latency > **5000 ms**.

Tune in `locustfile.py::_assert_slo`.

## Report template

After a run, `reports/<profile>_stats.csv` and `_stats_history.csv` are written.
Summarize as:

| Metric | smoke (100) | ramp500 | ramp1000 |
|---|---|---|---|
| Throughput (req/s) | | | |
| p50 / p95 / p99 latency (ms) | | | |
| Error rate (%) | | | |
| `POST /chat/query` p95 (ms) | | | |
| `POST /dashboard/generate` p95 (ms) | | | |
| CPU / memory (api container) | | | |
| DB connections (peak) | | | |

### Interpreting results / known bottlenecks
- **LLM latency dominates** `chat/query` and `dashboard/generate`; these call an
  external model. Expect seconds, not ms. Scale via concurrency + caching, not
  CPU. The semantic cache absorbs repeat questions.
- **Embeddings** are CPU-bound but now offloaded off the event loop
  (`asyncio.to_thread`); watch worker CPU under `rag/search` load.
- **DB pool**: primary pool = 10+20, read-only pool = 5+10 per worker. With 4
  workers that is (4×35) = up to 140 connections — ensure Postgres
  `max_connections` ≥ 200 or add PgBouncer before the 1000-user profile.
