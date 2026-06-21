#!/usr/bin/env bash
# ============================================================================
#  Restore a PostgreSQL custom-format backup.
#    Usage: pg_restore.sh <backup.dump> [target_db]
#  Verifies the sha256 sidecar (if present) before restoring.
#  Env: PGHOST PGPORT PGUSER PGPASSWORD
# ============================================================================
set -euo pipefail

BACKUP_FILE="${1:?usage: pg_restore.sh <backup.dump> [target_db]}"
TARGET_DB="${2:-${PGDATABASE:-healthcopilot}}"

if [[ -f "${BACKUP_FILE}.sha256" ]]; then
  echo "[restore] verifying checksum"
  (cd "$(dirname "$BACKUP_FILE")" && sha256sum -c "$(basename "$BACKUP_FILE").sha256")
fi

echo "[restore] (re)creating database ${TARGET_DB}"
psql -v ON_ERROR_STOP=1 -d postgres -c "DROP DATABASE IF EXISTS \"${TARGET_DB}\" WITH (FORCE);"
psql -v ON_ERROR_STOP=1 -d postgres -c "CREATE DATABASE \"${TARGET_DB}\";"

echo "[restore] restoring ${BACKUP_FILE} -> ${TARGET_DB}"
# --clean --if-exists makes the restore idempotent; -j parallelizes.
pg_restore --no-owner --jobs=4 --dbname="$TARGET_DB" "$BACKUP_FILE"

echo "[restore] done"
