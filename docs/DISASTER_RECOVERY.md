# Disaster Recovery Plan — Healthcare Copilot

## Objectives
| Metric | Target |
|---|---|
| RPO (max data loss) | ≤ 24h (daily dumps); ≤ 5 min with WAL archiving / PITR |
| RTO (max downtime) | ≤ 1h for full DB restore |
| Backup retention | 14 days local, 90 days offsite (S3) |
| Verification cadence | Automated restore test on every backup |

## What is backed up
- **PostgreSQL** (source of truth): all clinical + auth + audit data, via
  `scripts/backup/pg_backup.sh` (custom-format, compressed, checksummed).
- **PHI encryption keys** (`PHI_ENCRYPTION_KEYS`): stored in the secret manager,
  **NOT** in DB backups. A DB restore is useless without the keys — back them up
  in the KMS/secret store with their own rotation history.
- ChromaDB / Neo4j are **derived** state (re-indexed from Postgres on startup
  and by the KG sync job) — not part of RPO.
- Redis is a cache (sessions/denylist) — acceptable to lose; users re-login.

## Schedule (example — Kubernetes CronJob)
```yaml
apiVersion: batch/v1
kind: CronJob
metadata: { name: pg-backup }
spec:
  schedule: "0 */6 * * *"        # every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: postgres:16-alpine
              envFrom: [{ secretRef: { name: pg-backup-secrets } }]
              env:
                - { name: BACKUP_DIR, value: /backups }
                - { name: S3_BUCKET, value: s3://hc-backups/pg }
              command: ["/bin/sh","/scripts/pg_backup.sh"]
              volumeMounts:
                - { name: scripts, mountPath: /scripts }
                - { name: backups, mountPath: /backups }
```
Docker/cron equivalent: mount `scripts/backup/` and run `pg_backup.sh` from a
`postgres:16-alpine` sidecar on a cron schedule.

## Restore procedure
1. Provision a fresh PostgreSQL instance.
2. Fetch the latest verified dump (and its `.sha256`).
3. `PGHOST=... scripts/backup/pg_restore.sh <dump> healthcopilot`
4. Apply any migrations newer than the dump: `alembic upgrade head`.
5. Re-provision the read-only role: `psql -f scripts/sql/create_readonly_role.sql`.
6. Restore `PHI_ENCRYPTION_KEYS` from the secret manager (same keys as before).
7. Start the API — startup checks validate read-only isolation + RLS; ChromaDB
   re-indexes automatically.
8. Smoke test: login, run a chat query, confirm dashboards render.

## Backup verification (automated)
`scripts/backup/verify_backup.sh <dump>` restores into a throwaway database and
asserts core tables + RLS exist. Wire it to run after every backup; alert on
non-zero exit. **A backup that has never been test-restored is not a backup.**

## Point-in-time recovery (recommended for prod)
Enable WAL archiving (`archive_mode=on`, `archive_command` → object storage) or a
managed service with PITR (RDS/Cloud SQL) to cut RPO from 24h to minutes.

## Failure scenarios
| Scenario | Action |
|---|---|
| DB corruption | Restore latest verified dump (+ WAL replay for PITR). |
| Region outage | Restore from offsite (S3) into standby region. |
| Ransomware / bad deploy | Restore to a point before the event; rotate all secrets. |
| Lost encryption keys | PHI is unrecoverable — keys MUST be backed up separately. |
| Redis loss | None — sessions rebuild on next login. |
| ChromaDB/Neo4j loss | Re-index from Postgres (automatic on startup / KG sync). |
