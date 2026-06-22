# Technical Architecture — Healthcare Copilot

Complete technical reference with Mermaid diagrams. Sections:

1. [System architecture](#1-system-architecture)
2. [Authentication flow](#2-authentication-flow)
3. [RAG flow](#3-rag-flow)
4. [SQL generation flow](#4-sql-generation-flow)
5. [Dashboard generation flow](#5-dashboard-generation-flow)
6. [WebSocket flow](#6-websocket-flow)
7. [Database schema](#7-database-schema)
8. [Security architecture](#8-security-architecture)
9. [Deployment architecture](#9-deployment-architecture)
10. [Backup & recovery architecture](#10-backup--recovery-architecture)

---

## 1. System architecture

A React SPA talks to an async FastAPI backend through an nginx edge. The backend
orchestrates an LLM, a RAG store (ChromaDB), a knowledge graph (Neo4j), and a
PostgreSQL warehouse — executing all AI-generated SQL through a **separate
read-only role**. Redis backs sessions/cache; Prometheus/Grafana/Jaeger provide
observability.

```mermaid
flowchart TB
    subgraph Client
        SPA["React SPA (Vite, Zustand, React Query)"]
    end

    subgraph Edge
        NGINX["nginx — TLS termination, static SPA, reverse proxy"]
    end

    subgraph Backend["FastAPI backend (uvicorn workers)"]
        MW["Middleware: security headers, audit, CORS"]
        ROUTES["Routers: auth, chat, dashboard, rag, sessions, kg, ws"]
        SVC["Services: router, RAG, text-to-SQL, agentic, validation, exec, insights"]
        MW --> ROUTES --> SVC
    end

    subgraph Data["Stateful services"]
        PG[("PostgreSQL 16 — RLS + PHI encryption")]
        ROLE["app role (RW) | hc_readonly (RO)"]
        REDIS[("Redis — sessions, denylist, semantic cache")]
        CHROMA[("ChromaDB — schema embeddings")]
        NEO[("Neo4j — knowledge graph")]
        KAFKA[["Kafka — clinical event stream"]]
    end

    subgraph External
        LLM["LLM API (Groq / OpenAI-compatible)"]
    end

    subgraph Obs["Observability"]
        PROM["Prometheus"]
        GRAF["Grafana"]
        JAEG["Jaeger / OTel"]
    end

    SPA -->|HTTPS| NGINX
    NGINX -->|/api, /ws| MW
    SVC -->|RW: auth, history| REDIS
    SVC -->|read-only SQL| ROLE --> PG
    SVC -->|embed + retrieve| CHROMA
    SVC -->|graph queries| NEO
    SVC -->|generate| LLM
    KAFKA --> SVC
    Backend -.metrics.-> PROM --> GRAF
    Backend -.traces.-> JAEG
```

---

## 2. Authentication flow

PyJWT access/refresh tokens are delivered as **HttpOnly cookies** (invisible to
JS). Access tokens carry a `jti` for revocation; refresh tokens are **rotated**
on every use and the spent token is denylisted in Redis. Logout denylists both.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser (SPA)
    participant N as nginx
    participant API as FastAPI
    participant DB as PostgreSQL
    participant R as Redis

    B->>API: POST /auth/login (form: username, password)
    API->>DB: SELECT user; verify bcrypt hash
    API->>API: create access+refresh JWT (with jti)
    API-->>B: Set-Cookie access_token, refresh_token (HttpOnly, SameSite, Secure)

    Note over B,API: Subsequent requests send cookies automatically
    B->>API: GET /api/... (cookie)
    API->>API: verify_token (cookie or Bearer)
    API->>R: EXISTS jwt:denylist:{jti}?
    R-->>API: not revoked
    API->>DB: load active user
    API-->>B: 200 + data

    Note over B,API: On 401, SPA silently refreshes once
    B->>API: POST /auth/refresh (refresh cookie)
    API->>R: EXISTS denylist:{old jti}? (replay check)
    API->>R: SETEX denylist:{old jti} (rotate)
    API-->>B: new access+refresh cookies

    B->>API: POST /auth/logout
    API->>R: SETEX denylist:{access jti}, denylist:{refresh jti}
    API-->>B: clear cookies
```

**Authorization:** `RequireRole` / `get_current_admin` dependencies gate routes;
the user's role is also pushed into PostgreSQL session GUCs for RLS (see §8).

---

## 3. RAG flow

Two phases. **Indexing** (startup / `/rag/index`) extracts live schema and stores
three chunk types per table in ChromaDB, skipping unchanged tables by hash.
**Retrieval** uses **HyDE** (generate a hypothetical SQL doc), embeds it,
over-fetches, re-ranks by table, and assembles a structured schema context.

```mermaid
flowchart TD
    subgraph Indexing
        EX["SchemaExtractor — columns, FKs, comments, row counts"]
        CH["Build chunks: table | columns | relationship"]
        HASH{"schema hash changed?"}
        UP["Embed + upsert into ChromaDB"]
        EX --> CH --> HASH
        HASH -- yes --> UP
        HASH -- no --> SKIP["skip table"]
    end

    subgraph Retrieval
        Q["User question"]
        HYDE["HyDE: LLM drafts hypothetical SQL"]
        E2["Embed search doc (sentence-transformers)"]
        QRY["ChromaDB query — over-fetch k*3"]
        RR["Re-rank by best chunk per table; expand via FK related_tables"]
        CTX["Assemble context: markdown schema + DDL + JOIN hints"]
        Q --> HYDE --> E2 --> QRY --> RR --> CTX
    end

    UP -. vectors .-> QRY
    CTX --> OUT["Schema context → LLM prompt"]
```

---

## 4. SQL generation flow

The default `/chat/query` pipeline and the streaming `/chat/query-agentic`
(LangGraph) pipeline both converge on the **same safety gate**: validation →
read-only execution → PHI redaction. Invalid or unauthorized SQL never executes.

```mermaid
flowchart TD
    Q["NL question"] --> PI{"Prompt-injection heuristic"}
    PI -- blocked --> R403["403 Security violation"]
    PI -- ok --> INTENT{"Intent router (LLM)"}
    INTENT -- conversational --> CHAT["Direct LLM reply"]
    INTENT -- clinical_query --> RAG["RAG: retrieve schema context (§3)"]

    RAG --> GEN["Text-to-SQL (LLM) + semantic cache"]
    GEN --> VAL{"SQL validation engine (sqlglot AST)"}

    subgraph Agentic["Agentic path (LangGraph)"]
        AS["schema → plan → generate"] --> AV{"validate"}
        AV -- invalid, retry<3 --> AS
        AV -- valid --> OPT["optimize (EXPLAIN + LLM rewrite)"]
        OPT --> REVAL{"re-validate rewrite"}
    end

    VAL -- invalid --> FAIL["Return validation errors (no execution)"]
    VAL -- valid --> EXEC
    REVAL -- valid --> EXEC["Read-only executor: SET TRANSACTION READ ONLY + set_config role/uid"]
    REVAL -- invalid --> EXEC2["fall back to validated draft"] --> EXEC

    EXEC --> RLS["PostgreSQL RLS policies enforce row access"]
    RLS --> ROWS["Result rows"]
    ROWS --> REDACT["PHI redaction by role"]
    REDACT --> CHARTS["Chart advisor + Insights engine (LLM)"]
    CHARTS --> SAVE["Persist message + return response"]
```

**Validation engine checks:** single `SELECT`/`WITH` only; table allow-list
(12 clinical tables; `users`/`audit_logs`/`copilot_*` denied); blocked DML/DDL
keywords (AST + comment/string-stripped regex); system-catalog block; stacked /
tautology / null-byte injection; complexity score ≤ 30; mandatory `LIMIT`.

---

## 5. Dashboard generation flow

One natural-language request fans out into 3–5 focused panels, each run through
the full NL→SQL→validate→read-only-exec→redact→chart pipeline **in parallel**,
then composed into a laid-out dashboard with an LLM executive summary.

```mermaid
flowchart TD
    REQ["Dashboard request (NL)"] --> PLAN["QueryPlanner (LLM): 3-5 sub-questions + chart hints"]
    PLAN -->|fallback if LLM down| FB["Rule-based plan"]
    PLAN --> FAN{{"asyncio.gather — parallel panels"}}

    subgraph Panel["Per-panel pipeline"]
        P1["RAG schema context"] --> P2["Text-to-SQL"]
        P2 --> P3{"Validate"}
        P3 -- valid --> P4["Read-only execute (user_role)"]
        P4 --> P5["PHI redaction"]
        P5 --> P6["Chart selection"]
    end

    FAN --> Panel
    Panel --> LAYOUT["LayoutEngine — grid spans + positions"]
    LAYOUT --> SUM["SummaryComposer (LLM) — executive summary"]
    SUM --> FILTERS["Dynamic filters (allowlisted columns)"]
    FILTERS --> RESP["DashboardResponse: panels + layout + summary"]
```

---

## 6. WebSocket flow

The streaming query socket authenticates from the **HttpOnly cookie** on the
handshake, then streams each pipeline stage as a discrete event. The realtime
analytics socket broadcasts Kafka-sourced clinical events to authenticated clients.

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser
    participant API as FastAPI WS
    participant R as RAG
    participant L as LLM
    participant V as Validator
    participant DB as Read-only PG

    B->>API: WS connect /api/v1/stream/{session} (cookie)
    API->>API: verify_token (cookie); reject 4001 if invalid
    B->>API: { question }
    API-->>B: status: retrieving_schema
    API->>R: retrieve schema context
    API-->>B: status: generating_sql
    API->>L: generate SQL
    API-->>B: sql_generated
    API->>V: validate (legacy 3-tuple)
    API-->>B: sql_validated { valid, violations }
    alt valid
        API->>DB: execute (read-only, role GUC)
        API->>API: PHI redaction by role
        API-->>B: results_ready
        API-->>B: chart_ready
        API-->>B: insights_ready
        API-->>B: done
    else invalid
        API-->>B: done { error: validation failed }
    end
```

---

## 7. Database schema

UUID PKs, timezone-aware audit timestamps, and an OLAP-style clinical star around
`patients` / `encounters`. Auth/copilot/audit tables are isolated from the
analytics allow-list. (Abbreviated; see `backend/app/db/models/`.)

```mermaid
erDiagram
    USERS ||--o{ COPILOT_SESSIONS : owns
    COPILOT_SESSIONS ||--o{ COPILOT_MESSAGES : contains
    COPILOT_MESSAGES ||--o| NL_SQL_PAIRS : "feedback for"

    FACILITIES ||--o{ DEPARTMENTS : has
    DEPARTMENTS ||--o{ PROVIDERS : staffs
    DEPARTMENTS ||--o{ ENCOUNTERS : hosts
    PATIENTS ||--o{ ENCOUNTERS : has
    PROVIDERS ||--o{ ENCOUNTERS : attends
    ENCOUNTERS ||--o{ DIAGNOSES : records
    ENCOUNTERS ||--o{ PROCEDURES : records
    ENCOUNTERS ||--o{ MEDICATIONS : orders
    ENCOUNTERS ||--o{ LAB_RESULTS : produces
    ENCOUNTERS ||--o{ VITAL_SIGNS : produces
    ENCOUNTERS ||--o{ CLAIMS : bills
    PATIENTS ||--o{ READMISSIONS : tracks

    USERS {
        uuid id PK
        string email UK
        string username UK
        string hashed_password
        string first_name "encrypted (Fernet)"
        string last_name "encrypted (Fernet)"
        string role "admin|doctor|nurse|analyst"
        bool is_active
    }
    PATIENTS {
        uuid id PK
        string mrn UK "PHI"
        string first_name "PHI"
        string last_name "PHI"
        date date_of_birth "PHI"
        string zip_code "PHI"
        string gender
        string race
    }
    ENCOUNTERS {
        uuid id PK
        uuid patient_id FK
        uuid provider_id FK
        uuid department_id FK
        string encounter_type
        timestamp admit_date
        timestamp discharge_date
        numeric total_charge
    }
    CLAIMS {
        uuid id PK
        uuid encounter_id FK
        string payer_name
        numeric billed_amount
        numeric paid_amount
        string claim_status "RLS: admin/analyst only"
    }
    AUDIT_LOGS {
        uuid id PK
        uuid user_id
        string endpoint
        int status_code
        string ip_address
    }
```

**Migrations (Alembic, linear):** `001` base schema → `73684e…` audit + roles →
`5222b9…` alerts → `a1b2c3…` FK/date indexes → `b2c3d4…` **RLS policies** →
`c3d4e5…` **PHI encryption** column widening.

---

## 8. Security architecture

Defense in depth — seven enforcement layers from the network edge down to the row.

```mermaid
flowchart TB
    A["1. Edge — TLS, HSTS, WAF/rate limit"] --> B
    B["2. App headers — CSP, X-Frame-Options, Referrer-Policy, Permissions-Policy"] --> C
    C["3. AuthN — PyJWT HttpOnly cookies, refresh rotation, Redis denylist, per-IP rate limit"] --> D
    D["4. AuthZ — RBAC (RequireRole) + role GUC propagation"] --> E
    E["5. AI guardrails — prompt-injection filter, sqlglot AST validation, allow-list, complexity, LIMIT"] --> F
    F["6. Execution isolation — hc_readonly SELECT-only role, SET TRANSACTION READ ONLY"] --> G
    G["7. Data layer — PostgreSQL RLS policies, PHI encryption at rest, PHI redaction on egress"] --> H
    H["Audit — structured logs, audit_logs table, HIPAA-tagged security events"]
```

```mermaid
flowchart LR
    REQ["AI-generated SQL"] --> V["Validation gate"]
    V -->|set_config app.current_user_role/id| S["Read-only session"]
    S --> RLS{"RLS policy per table"}
    RLS -->|role in clinical roles| CLIN["clinical rows visible"]
    RLS -->|role in admin/analyst| FIN["claims rows visible"]
    RLS -->|role NULL = trusted backend| ALL["full access (migrations/seed)"]
    RLS -->|unknown role| DENY["0 rows (fail closed)"]
    CLIN --> RED["PHI redaction by role"]
    FIN --> RED
```

---

## 9. Deployment architecture

Production runs behind a load balancer that terminates TLS; the nginx frontend
serves the SPA and reverse-proxies `/api` + `/ws`. Migrations run as a one-shot
job before the API starts. Datastores are private; the read-only role targets a
read replica.

```mermaid
flowchart TB
    USERS["Users (HTTPS)"] --> LB["Cloud LB — ACM / Key Vault cert (TLS)"]
    LB --> FE["frontend (nginx): SPA + proxy"]
    FE -->|/api /ws| BE["backend (uvicorn x4, --proxy-headers)"]

    MIG["migrate job: alembic upgrade head"] -. runs before .-> BE

    subgraph Private["Private network / managed services"]
        BE --> PGP[("PostgreSQL primary (RW)")]
        BE --> PGR[("PostgreSQL read replica — hc_readonly")]
        BE --> REDIS[("Redis (managed)")]
        BE --> CHROMA[("ChromaDB / managed vector DB")]
        BE --> NEO[("Neo4j")]
    end

    BE --> LLM["LLM API (external)"]
    SEC["Secrets Manager / Key Vault"] -. inject .-> BE
    BE -.metrics/traces.-> OBS["Prometheus + Grafana + Jaeger"]

    PGP -. streaming replication .-> PGR
```

Scaling: backend is stateless → horizontal autoscale; add **PgBouncer** in front
of Postgres; route `hc_readonly` to the replica; managed Redis/vector DB. See
[DEPLOYMENT.md](DEPLOYMENT.md).

---

## 10. Backup & recovery architecture

Automated, checksummed, custom-format `pg_dump` on a schedule, replicated
offsite, and — critically — **test-restored automatically**. Encryption keys are
backed up separately from the database (a DB restore is useless without them).

```mermaid
flowchart TD
    CRON["Scheduler (cron / k8s CronJob)"] --> BK["pg_backup.sh — pg_dump -Fc, gzip, sha256"]
    BK --> LOCAL[("Local /backups (retention: 14d)")]
    BK --> S3[("Offsite object storage (90d)")]
    BK --> VERIFY["verify_backup.sh — restore to scratch DB, assert tables + RLS"]
    VERIFY -->|fail| ALERT["Alert on-call"]

    subgraph Recovery
        FETCH["Fetch latest verified dump + sha256"] --> RST["pg_restore.sh"]
        RST --> MIGR["alembic upgrade head"]
        MIGR --> RORLE["create_readonly_role.sql"]
        RORLE --> KEYS["Restore PHI_ENCRYPTION_KEYS from KMS"]
        KEYS --> START["Start API — startup checks verify RO isolation + RLS"]
    end

    S3 --> FETCH
    KMS[("KMS / Secret Manager — encryption keys, secrets")] --> KEYS

    PITR["WAL archiving → PITR (RPO ~minutes)"] -.optional.-> RST
```

**Targets:** RTO ≤ 1h, RPO ≤ 24h (≤ 5 min with WAL/PITR). Derived stores
(ChromaDB, Neo4j) rebuild from Postgres on startup and are excluded from RPO.
Full runbook: [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md).

---

## Supabase data platform

The primary datastore can run on **Supabase** (managed PostgreSQL) with no change
to the application model — Supabase *is* Postgres, so SQLAlchemy/Alembic, RLS, the
read-only executor role, and Fernet PHI encryption all carry over.

```mermaid
flowchart LR
    SPA[React SPA] -->|HTTPS| API[FastAPI backend]
    API -->|asyncpg + TLS, pooler-aware| SB[(Supabase Postgres / RLS + FORCE)]
    API -. AI-generated SQL via hc_readonly .-> SB
    SEED[seeding pipeline / binary COPY] -->|bulk load| SB
    SB --> RAG[(ChromaDB schema vectors)]
    SB --> KG[(Neo4j knowledge graph)]
```

- **Connection:** `SUPABASE_DB_URL` (session or transaction pooler). The backend
  auto-enables TLS for `*.supabase.*` and, on the transaction pooler (`:6543`),
  disables prepared-statement caching (`Settings.asyncpg_connect_args`). Startup
  retries through pooler cold starts (`db.session.wait_for_database`).
- **Schema parity:** `supabase/migration.sql` is auto-generated from the ORM
  (`scripts/emit_supabase_sql.py`) and matches `alembic upgrade head` exactly.
- **Data:** the `seeding/` pipeline streams a 100K-patient / ~6.6M-row synthetic
  dataset via COPY. See [SUPABASE_SETUP.md](SUPABASE_SETUP.md),
  [DATA_GENERATION.md](DATA_GENERATION.md), [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md),
  and [SAMPLE_QUERIES.md](SAMPLE_QUERIES.md).
