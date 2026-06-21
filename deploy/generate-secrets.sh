#!/usr/bin/env bash
# ============================================================================
#  Generate a production .env with STRONG, unique secrets.
#  Run this ON THE TARGET SERVER. Secrets are written only to ./.env (never
#  printed, never committed — .env is git-ignored). Refuses to overwrite.
#
#    LLM_API_KEY=... DOMAIN=app.example.com ./deploy/generate-secrets.sh
#  (LLM_API_KEY and DOMAIN may also be entered interactively.)
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env"
if [[ -f "$ENV_FILE" ]]; then
  echo "Refusing to overwrite existing $ENV_FILE. Move it aside first." >&2
  exit 1
fi

command -v openssl >/dev/null || { echo "openssl is required" >&2; exit 1; }

# URL-safe secrets (hex) so they embed cleanly in redis:// / postgres:// URLs.
gen_pw()   { openssl rand -hex 24; }
# Fernet key = urlsafe-base64 of 32 random bytes (44 chars).
gen_fernet(){ head -c 32 /dev/urandom | base64 | tr '+/' '-_'; }

: "${LLM_API_KEY:=}"
if [[ -z "$LLM_API_KEY" ]]; then read -rp "LLM_API_KEY (Groq/OpenAI-compatible): " LLM_API_KEY; fi
: "${DOMAIN:=}"
if [[ -z "$DOMAIN" ]]; then read -rp "Public domain (e.g. app.example.com): " DOMAIN; fi

POSTGRES_PASSWORD="$(gen_pw)"
READONLY_POSTGRES_PASSWORD="$(gen_pw)"
REDIS_PASSWORD="$(gen_pw)"
NEO4J_PASSWORD="$(gen_pw)"
GRAFANA_ADMIN_PASSWORD="$(gen_pw)"
SECRET_KEY="$(gen_pw)$(gen_pw)"
JWT_SECRET_KEY="$(gen_pw)$(gen_pw)"
PHI_ENCRYPTION_KEYS="$(gen_fernet)"

umask 177   # .env readable only by owner
cat > "$ENV_FILE" <<EOF
# Generated $(date -u +%FT%TZ) — DO NOT COMMIT. Back up PHI_ENCRYPTION_KEYS to a KMS.
APP_ENV=production
APP_DEBUG=false
SECRET_KEY=${SECRET_KEY}

POSTGRES_DB=healthcopilot
POSTGRES_USER=hc_user
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

READONLY_POSTGRES_USER=hc_readonly
READONLY_POSTGRES_PASSWORD=${READONLY_POSTGRES_PASSWORD}
REQUIRE_READONLY_ROLE=true

REDIS_PASSWORD=${REDIS_PASSWORD}
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=${NEO4J_PASSWORD}
GRAFANA_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD}

JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

COOKIE_SECURE=true
COOKIE_SAMESITE=lax
CORS_ALLOWED_ORIGINS=https://${DOMAIN}

CHROMADB_MODE=http
CHROMADB_COLLECTION=healthcare_schema

LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
LLM_API_KEY=${LLM_API_KEY}
LLM_MAX_TOKENS=2048
LLM_TEMPERATURE=0.1

PHI_ENCRYPTION_KEYS=${PHI_ENCRYPTION_KEYS}
LOG_LEVEL=INFO
EOF

echo "Wrote $ENV_FILE (chmod 600). Secrets were NOT printed."
echo "ACTION: store PHI_ENCRYPTION_KEYS and DB passwords in your secret manager / KMS now."
