#!/usr/bin/env bash
# ============================================================================
#  One-command production bootstrap for a fresh Ubuntu 22.04 VM.
#  Brings up the full stack via docker-compose.prod.yml, provisions the
#  least-privilege read-only role, and waits for health.
#
#    sudo ./deploy/bootstrap.sh
#
#  Prereqs: run deploy/generate-secrets.sh first (creates ./.env), and point
#  your DNS + TLS terminator (cloud LB or certs) at this host (see docs/DEPLOYMENT.md).
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.prod.yml"

# 1. Docker (install if missing).
if ! command -v docker >/dev/null; then
  echo "[bootstrap] installing Docker…"
  curl -fsSL https://get.docker.com | sh
fi

# 2. Require a populated .env.
[[ -f .env ]] || { echo "[bootstrap] .env missing — run deploy/generate-secrets.sh first" >&2; exit 1; }
set -a; . ./.env; set +a
: "${READONLY_POSTGRES_PASSWORD:?READONLY_POSTGRES_PASSWORD must be set in .env}"

# 3. Build + start (the one-shot `migrate` service runs alembic upgrade head).
echo "[bootstrap] building and starting the stack…"
$COMPOSE up -d --build

# 4. Wait for Postgres health, then provision the read-only role (idempotent).
echo "[bootstrap] waiting for postgres…"
until $COMPOSE exec -T postgres pg_isready -U "${POSTGRES_USER:-hc_user}" >/dev/null 2>&1; do sleep 3; done

echo "[bootstrap] provisioning hc_readonly role…"
$COMPOSE exec -T postgres psql -U "${POSTGRES_USER:-hc_user}" -d "${POSTGRES_DB:-healthcopilot}" \
  -v ro_password="${READONLY_POSTGRES_PASSWORD}" \
  < backend/scripts/sql/create_readonly_role.sql

# 5. Health gate.
echo "[bootstrap] waiting for the frontend edge to report healthy…"
for i in $(seq 1 30); do
  if curl -fsS http://localhost/healthz >/dev/null 2>&1; then
    echo "[bootstrap] ✅ stack is up. Point your TLS terminator/DNS at this host."
    exit 0
  fi
  sleep 4
done
echo "[bootstrap] ⚠ frontend not healthy yet — check: $COMPOSE logs --tail=50" >&2
exit 1
