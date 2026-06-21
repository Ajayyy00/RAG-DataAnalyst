-- ============================================================================
--  Rollback: remove the read-only executor role.
--  Run as superuser / owner:  psql -U postgres -d healthcopilot -f drop_readonly_role.sql
-- ============================================================================
\set ON_ERROR_STOP on

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hc_readonly') THEN
        EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM hc_readonly';
        EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM hc_readonly';
        EXECUTE 'REVOKE USAGE ON SCHEMA public FROM hc_readonly';
        EXECUTE 'REVOKE CONNECT ON DATABASE healthcopilot FROM hc_readonly';
        EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO hc_readonly';
        EXECUTE 'DROP ROLE hc_readonly';
    END IF;
END
$$;

\echo 'hc_readonly role removed.'
