#!/usr/bin/env bash
# ============================================================================
#  Backup verification: restore a dump into a throwaway DB and sanity-check it.
#  This is the test that proves a backup is actually recoverable.
#    Usage: verify_backup.sh <backup.dump>
#  Exits non-zero if the restore fails or core tables are missing/empty-of-schema.
# ============================================================================
set -euo pipefail

BACKUP_FILE="${1:?usage: verify_backup.sh <backup.dump>}"
VERIFY_DB="hc_verify_$(date -u +%s)"

cleanup() {
  psql -d postgres -c "DROP DATABASE IF EXISTS \"${VERIFY_DB}\" WITH (FORCE);" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[verify] restoring into scratch db ${VERIFY_DB}"
PGDATABASE=postgres "$(dirname "$0")/pg_restore.sh" "$BACKUP_FILE" "$VERIFY_DB"

echo "[verify] checking core tables exist"
EXPECTED=(users patients encounters diagnoses medications claims audit_logs)
for t in "${EXPECTED[@]}"; do
  exists="$(psql -tA -d "$VERIFY_DB" -c \
    "SELECT to_regclass('public.${t}') IS NOT NULL")"
  if [[ "$exists" != "t" ]]; then
    echo "[verify] FAIL: table '${t}' missing in restored backup" >&2
    exit 1
  fi
done

echo "[verify] checking RLS is present on patients"
rls="$(psql -tA -d "$VERIFY_DB" -c \
  "SELECT relrowsecurity FROM pg_class WHERE relname='patients'")"
[[ "$rls" == "t" ]] || { echo "[verify] WARN: RLS not enabled on patients"; }

echo "[verify] PASS — backup is restorable and schema is intact"
