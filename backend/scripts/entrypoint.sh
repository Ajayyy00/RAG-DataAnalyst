#!/usr/bin/env bash
# Production entrypoint: apply DB migrations, then exec the given command.
# Used by the one-shot `migrate` service and safe to reuse for the API.
set -euo pipefail

echo "[entrypoint] applying database migrations (alembic upgrade head)…"
alembic upgrade head
echo "[entrypoint] migrations complete."

# If extra args were given, run them (e.g. uvicorn …); otherwise just exit 0
# (one-shot migrate mode).
if [[ "$#" -gt 0 ]]; then
    exec "$@"
fi
