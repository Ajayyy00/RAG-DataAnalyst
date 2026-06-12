# Healthcare Copilot — FastAPI Backend

AI-powered natural language interface for healthcare analytics. Converts clinical questions into SQL, executes them against PostgreSQL, generates charts, and produces LLM-driven insights.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.11+
- A running vLLM or Ollama instance (Llama 3)

### 1. Clone and Configure

```bash
cd d:\llm\healthcare-copilot\backend
cp .env.example .env
# Edit .env with your actual secrets
```

### 2. Run with Docker Compose

```bash
docker-compose up --build
```

Services started:
| Service    | Port  | Purpose                          |
|------------|-------|----------------------------------|
| backend    | 8001  | FastAPI application              |
| postgres   | 5432  | Primary PostgreSQL database      |
| redis      | 6379  | Session cache + conversation TTL |
| chromadb   | 8000  | Schema vector embeddings         |
| prometheus | 9090  | Metrics collection               |

### 3. Run Migrations

```bash
docker-compose exec backend alembic upgrade head
```

### 4. Open API Docs

- Swagger UI: http://localhost:8001/docs
- ReDoc:       http://localhost:8001/redoc
- Health:      http://localhost:8001/health
- Metrics:     http://localhost:8001/metrics

---

## Local Development (without Docker)

```bash
# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Copy env file
cp .env.example .env

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

---

## Architecture

```
app/
├── main.py                  # FastAPI factory + lifespan
├── config.py                # Pydantic Settings (env-driven)
├── dependencies.py          # DI: DB, Redis, JWT auth
│
├── api/v1/
│   ├── router.py            # Aggregate all sub-routers
│   ├── auth.py              # POST /auth/register, /login, /refresh
│   ├── chat.py              # POST /chat/query, /chat/validate
│   ├── sessions.py          # CRUD /sessions/*
│   ├── schema_routes.py     # GET /schema/tables, POST /schema/reindex
│   └── finetune.py          # POST /finetune/feedback, GET /finetune/pairs
│
├── api/websocket/
│   └── stream.py            # WS /stream/{session_id}
│
├── core/
│   ├── security.py          # JWT creation/verification, bcrypt
│   ├── logging.py           # structlog configuration
│   └── exceptions.py        # Custom exceptions + FastAPI handlers
│
├── db/
│   ├── base.py              # SQLAlchemy DeclarativeBase
│   ├── session.py           # Async engine + session factory
│   └── models/
│       ├── user.py          # User (RBAC)
│       ├── healthcare.py    # 12 healthcare domain tables
│       └── copilot.py       # Sessions, messages, NL-SQL pairs
│
├── schemas/
│   ├── auth.py              # Register/login/token schemas
│   ├── chat.py              # Query request/response schemas
│   ├── session.py           # Session/message schemas
│   └── finetune.py          # Feedback/export schemas
│
└── services/
    ├── auth_service.py              # Registration, login, token refresh
    ├── rag_service.py               # ChromaDB schema indexing + retrieval
    ├── text_to_sql_service.py       # LLM prompt engineering + SQL generation
    ├── sql_validation_service.py    # sqlglot-based safety + syntax checks
    ├── query_execution_service.py   # PostgreSQL execution + timeout
    ├── chart_generation_service.py  # Chart type recommendation logic
    ├── llm_explanation_service.py   # Clinical insight generation
    └── conversation_history_service.py  # Session + Redis cache management
```

---

## API Reference

### Authentication

| Method | Endpoint                  | Auth | Description                 |
|--------|---------------------------|------|-----------------------------|
| POST   | `/api/v1/auth/register`   | No   | Create a new user           |
| POST   | `/api/v1/auth/login`      | No   | Get access + refresh tokens |
| POST   | `/api/v1/auth/refresh`    | No   | Renew access token          |
| GET    | `/api/v1/auth/me`         | Yes  | Current user profile        |
| POST   | `/api/v1/auth/change-password` | Yes | Change password        |

### Chat & Query

| Method | Endpoint               | Auth | Description                        |
|--------|------------------------|------|------------------------------------|
| POST   | `/api/v1/chat/query`   | Yes  | NL → SQL → Execute → Insights      |
| POST   | `/api/v1/chat/validate`| Yes  | Validate SQL without executing     |

### Sessions

| Method | Endpoint                              | Auth | Description            |
|--------|---------------------------------------|------|------------------------|
| POST   | `/api/v1/sessions`                    | Yes  | Create session         |
| GET    | `/api/v1/sessions`                    | Yes  | List user sessions     |
| GET    | `/api/v1/sessions/{id}`               | Yes  | Get session            |
| GET    | `/api/v1/sessions/{id}/messages`      | Yes  | Get message history    |
| DELETE | `/api/v1/sessions/{id}`               | Yes  | Archive session        |

### Schema

| Method | Endpoint                          | Auth      | Description             |
|--------|-----------------------------------|-----------|-------------------------|
| GET    | `/api/v1/schema/tables`           | User      | List all tables         |
| GET    | `/api/v1/schema/tables/{name}`    | User      | Get column details      |
| POST   | `/api/v1/schema/reindex`          | **Admin** | Re-index schema to Chroma |
| GET    | `/api/v1/schema/search?q=...`     | User      | Semantic schema search  |

### Fine-Tuning

| Method | Endpoint                      | Auth      | Description              |
|--------|-------------------------------|-----------|--------------------------|
| POST   | `/api/v1/finetune/feedback`   | User      | Submit feedback          |
| GET    | `/api/v1/finetune/pairs`      | **Admin** | List NL-SQL pairs        |
| GET    | `/api/v1/finetune/stats`      | **Admin** | Dataset statistics       |
| POST   | `/api/v1/finetune/export`     | **Admin** | Export JSONL dataset     |

### WebSocket

```
WS /api/v1/stream/{session_id}?token=<access_token>
```

---

## Environment Variables

| Variable                    | Default                    | Description                    |
|-----------------------------|----------------------------|--------------------------------|
| `APP_ENV`                   | development                | Environment name               |
| `POSTGRES_HOST`             | localhost                  | PostgreSQL host                |
| `POSTGRES_DB`               | healthcopilot              | Database name                  |
| `POSTGRES_USER`             | hc_user                    | Database user                  |
| `POSTGRES_PASSWORD`         | —                          | Database password              |
| `REDIS_URL`                 | redis://localhost:6379     | Redis connection URL           |
| `CHROMADB_HOST`             | localhost                  | ChromaDB host                  |
| `LLM_BASE_URL`              | http://localhost:8080/v1   | OpenAI-compatible LLM endpoint |
| `LLM_MODEL`                 | meta-llama/Meta-Llama-3-8B | Model name                     |
| `JWT_SECRET_KEY`            | —                          | JWT signing secret             |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 60                       | Token lifetime                 |
| `QUERY_TIMEOUT_SECONDS`     | 30                         | Max SQL execution time         |
| `EMBEDDING_MODEL`           | all-MiniLM-L6-v2           | Sentence transformer model     |

---

## Testing

```bash
pytest tests/ -v --asyncio-mode=auto
```

---

## Security Notes

- All SQL is validated through `sqlglot` AST parsing before execution
- Only `SELECT` statements are permitted; all DML/DDL is blocked
- Tables not on the allowlist are rejected at validation time
- JWT tokens use HS256 and expire after 60 minutes (configurable)
- Passwords are hashed with bcrypt (12 rounds)
- Statement timeout is enforced at the PostgreSQL session level
