# Supabase Setup Guide

This platform runs on **Supabase** (managed PostgreSQL 15+). Supabase *is*
Postgres, so the existing SQLAlchemy/Alembic stack, Row-Level Security, and PHI
encryption all carry over unchanged — you only point the app at Supabase and
load data.

```
React SPA ──HTTPS──▶ FastAPI backend ──asyncpg/TLS──▶ Supabase Postgres
                          │                                 │ RLS + GUC role
                          └── read-only role (hc_readonly) ──┘ (AI-generated SQL)
```

## 1. Create the project
1. https://supabase.com → **New project**. Pick a region close to your backend.
2. Save the **database password** (you set it at creation).
3. **Project Settings → Database → Connection string**. You'll see three modes:

| Mode | Host / Port | Use it for |
|---|---|---|
| Direct | `db.<ref>.supabase.co:5432` | migrations from an IPv6 host |
| **Session pooler** | `aws-0-<region>.pooler.supabase.com:5432` | **the backend (recommended)** — IPv4, supports prepared statements |
| Transaction pooler | `aws-0-<region>.pooler.supabase.com:6543` | serverless / very high connection count |

The backend auto-detects the transaction pooler (`:6543`) and disables
prepared-statement caching automatically (see `Settings.asyncpg_connect_args`),
so either pooler works. **Session pooler (5432) is the default recommendation.**

## 2. Create the schema
Two equivalent options.

**A. Alembic (recommended — keeps migrations as the source of truth):**
```bash
cd backend
export SUPABASE_DB_URL='postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres'
alembic upgrade head        # creates all tables, indexes, RLS, provider_type, PHI columns
```

**B. SQL bundle (paste-and-go in the Supabase SQL editor):**
- Open `supabase/migration.sql` and run it (or `psql "$SUPABASE_DB_URL" -f supabase/migration.sql`).
- It is auto-generated from the ORM (`backend/scripts/emit_supabase_sql.py`) and is
  idempotent (`IF NOT EXISTS`). `supabase/rollback.sql` reverses it.

Both paths produce the **same** schema: 19 tables, FK indexes, GUC-driven RLS
(`*_trusted` + `*_role_read` policies), `providers.provider_type`, and the
`users.first_name/last_name` PHI columns as `TEXT` (Fernet ciphertext).

## 3. Provision the least-privilege role
AI-generated SQL never runs as the owner. Create the read-only executor:
```bash
psql "$SUPABASE_DB_URL" \
  -v ro_password="$(openssl rand -hex 24)" \
  -f backend/scripts/sql/create_readonly_role.sql
```
(Or run the "Least-privilege executor role" block at the bottom of
`supabase/migration.sql`.) Then set `READONLY_POSTGRES_USER=hc_readonly` and
`READONLY_POSTGRES_PASSWORD=…` in the backend env.

## 4. Configure the backend `.env`
```ini
SUPABASE_DB_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres
# Optional (only if you use Supabase Storage/Auth/Realtime REST — not needed for analytics):
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...

READONLY_POSTGRES_USER=hc_readonly
READONLY_POSTGRES_PASSWORD=...
REQUIRE_READONLY_ROLE=true

PHI_ENCRYPTION_KEYS=<fernet-key>        # python -m app.scripts.generate_encryption_key
```
`SUPABASE_DB_URL` overrides the discrete `POSTGRES_*` vars; TLS is enabled
automatically for `*.supabase.*` hosts.

## 5. Load data
```bash
cd backend
python -m scripts.seed.seed_all --scale prod --truncate --users
```
Scales: `demo` (seconds) · `small` · `medium` · `prod` (full 100K-patient set).
See [DATA_GENERATION.md](DATA_GENERATION.md). Then validate & benchmark:
```bash
python scripts/validate_data.py
python scripts/benchmark.py --out docs/PERFORMANCE_REPORT.md
```

## 6. Run the backend
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8001
```
Startup runs `wait_for_database()` (retries through pooler cold starts) and the
fail-closed security checks before serving.

## Security notes specific to Supabase
- **PostgREST data API:** this app connects directly to Postgres and does **not**
  use PostgREST. `migration.sql` `REVOKE`s `anon`/`authenticated` from every PHI
  table as defense-in-depth. If you don't need the data API at all, disable it in
  **Project Settings → API**.
- **RLS** is `ENABLE` + `FORCE` on all clinical tables — it applies even to the
  table owner. The trusted backend (no role GUC) keeps full access; AI-generated
  SQL sets `app.current_user_role` and is restricted to role-gated `SELECT`.
- **Backups:** Supabase provides daily backups (Pro: PITR). Keep your
  `PHI_ENCRYPTION_KEYS` in a separate secret manager — a DB backup is useless PHI
  without them, by design.
- **HIPAA:** Supabase supports a **BAA** on paid plans. Sign it before loading
  real PHI. The synthetic dataset here contains no real PHI.
