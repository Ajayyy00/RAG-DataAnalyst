#!/usr/bin/env bash
# ============================================================================
#  Automated PostgreSQL backup (custom-format, compressed, with retention).
#  Intended to run on a schedule (cron / k8s CronJob / systemd timer).
#
#  Env:
#    PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE   (libpq standard)
#    BACKUP_DIR        (default: /backups)
#    RETENTION_DAYS    (default: 14)
#    S3_BUCKET         (optional: s3://bucket/prefix — requires awscli)
# ============================================================================
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"
PGDATABASE="${PGDATABASE:-healthcopilot}"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR}/${PGDATABASE}_${TS}.dump"

mkdir -p "$BACKUP_DIR"

echo "[backup] pg_dump ${PGDATABASE} -> ${OUT}"
# -Fc = custom format (compressed, supports parallel restore + selective restore)
pg_dump --format=custom --compress=9 --no-owner --file="$OUT" "$PGDATABASE"

# Integrity: list the archive TOC; a corrupt dump fails here.
pg_restore --list "$OUT" > /dev/null
SHA="$(sha256sum "$OUT" | awk '{print $1}')"
echo "$SHA  $(basename "$OUT")" > "${OUT}.sha256"
echo "[backup] OK  size=$(du -h "$OUT" | cut -f1)  sha256=${SHA}"

# Optional offsite copy.
if [[ -n "${S3_BUCKET:-}" ]]; then
  echo "[backup] uploading to ${S3_BUCKET}"
  aws s3 cp "$OUT"        "${S3_BUCKET}/"
  aws s3 cp "${OUT}.sha256" "${S3_BUCKET}/"
fi

# Retention: delete local dumps older than RETENTION_DAYS.
echo "[backup] pruning backups older than ${RETENTION_DAYS} days"
find "$BACKUP_DIR" -name "${PGDATABASE}_*.dump*" -type f -mtime "+${RETENTION_DAYS}" -delete

echo "[backup] done"
