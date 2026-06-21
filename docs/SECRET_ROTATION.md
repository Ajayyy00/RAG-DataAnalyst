# Secret Management & Rotation Runbook

All secrets are injected at runtime via environment variables / Docker secrets.
**No secret is ever committed.** `.env` is git-ignored and Docker-ignored; CI
runs `detect-secrets` against `.secrets.baseline` on every push.

## Inventory

| Secret | Env var | Storage | Rotation cadence |
|---|---|---|---|
| LLM API key | `LLM_API_KEY` | Secret manager | 90 days / on exposure |
| JWT signing key | `JWT_SECRET_KEY` | Secret manager | 90 days (rolling) |
| App secret key | `SECRET_KEY` | Secret manager | 90 days |
| Primary DB password | `POSTGRES_PASSWORD` | Secret manager | 90 days |
| Read-only DB password | `READONLY_POSTGRES_PASSWORD` | Secret manager | 90 days |
| Redis password | `REDIS_PASSWORD` | Secret manager | 90 days |
| Neo4j password | `NEO4J_PASSWORD` | Secret manager | 90 days |
| PHI encryption keys | `PHI_ENCRYPTION_KEYS` | KMS / secret manager | 180 days (with re-encrypt) |

## Rotation procedures

### LLM API key
1. Create a new key in the provider console.
2. Update `LLM_API_KEY` in the secret store; redeploy.
3. **Revoke the old key** in the console (rotating the value does not disable it).

### JWT signing key (`JWT_SECRET_KEY`)
Rotating invalidates all existing tokens. Either:
- **Hard cutover** (forces re-login): set new value, redeploy. Existing
  access tokens fail verification → clients silently refresh / re-login.
- All tokens are also independently revocable via the Redis denylist
  (`POST /api/v1/auth/logout`, and refresh rotation).

### Database passwords
1. `ALTER ROLE <role> PASSWORD '<new>';`
2. Update the corresponding env var; redeploy.
3. For the read-only role, re-run `scripts/sql/create_readonly_role.sql`
   with the new `-v ro_password=`.

### PHI encryption keys (`PHI_ENCRYPTION_KEYS`) — zero downtime
1. Generate a new key: `python -m app.scripts.generate_encryption_key`.
2. **Prepend** it (new first, keep old): `PHI_ENCRYPTION_KEYS=<new>,<old>`. Deploy.
   New writes use the new key; old data still decrypts with the old key.
3. Re-encrypt existing rows: `python -m app.scripts.reencrypt_pii`.
4. Once complete, drop the old key: `PHI_ENCRYPTION_KEYS=<new>`. Deploy.

## If a secret leaks
1. Rotate **and revoke** immediately (see above).
2. Invalidate sessions: bump `JWT_SECRET_KEY` and/or flush the auth denylist.
3. Review `audit_logs` for misuse during the exposure window.
4. Update `.secrets.baseline` only after the leak is remediated.

## Tooling
- Local guard: `pip install pre-commit && pre-commit install`
- Manual scan: `detect-secrets scan --baseline .secrets.baseline`
- CI: the `secret-scan` job fails the build on any new, unaudited secret.
