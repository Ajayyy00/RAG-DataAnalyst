-- ============================================================================
--  Healthcare Copilot — least-privilege read-only executor role
-- ----------------------------------------------------------------------------
--  All AI-generated SQL is executed under THIS role (READONLY_POSTGRES_USER).
--  It can SELECT only the clinical tables and is explicitly denied access to
--  authentication, audit, and conversation tables. It is NOT a superuser and
--  does NOT have BYPASSRLS, so Row-Level Security policies are enforced.
--
--  Run as a superuser / the database owner:
--     psql -U postgres -d healthcopilot \
--          -v ro_password="$READONLY_POSTGRES_PASSWORD" \
--          -f create_readonly_role.sql
-- ============================================================================

\set ON_ERROR_STOP on

-- 1. Create the role (idempotent). Password supplied via -v ro_password=...
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hc_readonly') THEN
        EXECUTE format(
            'CREATE ROLE hc_readonly LOGIN PASSWORD %L '
            'NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT',
            :'ro_password'
        );
    ELSE
        EXECUTE format('ALTER ROLE hc_readonly PASSWORD %L', :'ro_password');
    END IF;
END
$$;

-- Harden: never allow RLS bypass.
ALTER ROLE hc_readonly NOBYPASSRLS;

-- 2. Connect + schema usage only.
GRANT CONNECT ON DATABASE healthcopilot TO hc_readonly;
GRANT USAGE  ON SCHEMA public           TO hc_readonly;

-- 3. Strip any inherited blanket privileges, then grant SELECT on the
--    clinical allowlist ONLY.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM hc_readonly;

GRANT SELECT ON
    patients, encounters, diagnoses, procedures, medications,
    lab_results, vital_signs, claims, readmissions,
    providers, departments, facilities
TO hc_readonly;

-- 4. Explicitly deny the sensitive non-clinical tables (defense in depth —
--    they were never granted, but REVOKE makes the intent auditable).
REVOKE ALL ON
    users, audit_logs, copilot_sessions, copilot_messages,
    nl_sql_pairs, schema_registry, alerts
FROM hc_readonly;

-- 5. No write privileges on sequences; no function execution beyond defaults.
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM hc_readonly;

-- 6. Future tables created in public default to NO access for this role.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM hc_readonly;

-- 7. Belt-and-suspenders: make the whole session read-only by default.
ALTER ROLE hc_readonly SET default_transaction_read_only = on;
ALTER ROLE hc_readonly SET statement_timeout = '30s';

\echo 'hc_readonly role provisioned: SELECT-only on clinical tables, RLS-enforced.'
