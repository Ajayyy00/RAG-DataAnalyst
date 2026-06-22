-- ============================================================================
--  Healthcare Copilot — Supabase rollback (AUTO-GENERATED)
--  Drops every object created by migration.sql. DESTRUCTIVE.
-- ============================================================================

-- Drop RLS policies first (tables dropped below take their policies with them,
-- but we drop explicitly so partial rollbacks are clean).
DROP POLICY IF EXISTS "patients_role_read" ON "patients";
DROP POLICY IF EXISTS "patients_trusted" ON "patients";
DROP POLICY IF EXISTS "encounters_role_read" ON "encounters";
DROP POLICY IF EXISTS "encounters_trusted" ON "encounters";
DROP POLICY IF EXISTS "diagnoses_role_read" ON "diagnoses";
DROP POLICY IF EXISTS "diagnoses_trusted" ON "diagnoses";
DROP POLICY IF EXISTS "procedures_role_read" ON "procedures";
DROP POLICY IF EXISTS "procedures_trusted" ON "procedures";
DROP POLICY IF EXISTS "medications_role_read" ON "medications";
DROP POLICY IF EXISTS "medications_trusted" ON "medications";
DROP POLICY IF EXISTS "lab_results_role_read" ON "lab_results";
DROP POLICY IF EXISTS "lab_results_trusted" ON "lab_results";
DROP POLICY IF EXISTS "vital_signs_role_read" ON "vital_signs";
DROP POLICY IF EXISTS "vital_signs_trusted" ON "vital_signs";
DROP POLICY IF EXISTS "readmissions_role_read" ON "readmissions";
DROP POLICY IF EXISTS "readmissions_trusted" ON "readmissions";
DROP POLICY IF EXISTS "providers_role_read" ON "providers";
DROP POLICY IF EXISTS "providers_trusted" ON "providers";
DROP POLICY IF EXISTS "claims_role_read" ON "claims";
DROP POLICY IF EXISTS "claims_trusted" ON "claims";

-- Drop tables in reverse FK-dependency order.
DROP TABLE IF EXISTS "vital_signs" CASCADE;
DROP TABLE IF EXISTS "readmissions" CASCADE;
DROP TABLE IF EXISTS "procedures" CASCADE;
DROP TABLE IF EXISTS "medications" CASCADE;
DROP TABLE IF EXISTS "lab_results" CASCADE;
DROP TABLE IF EXISTS "diagnoses" CASCADE;
DROP TABLE IF EXISTS "claims" CASCADE;
DROP TABLE IF EXISTS "nl_sql_pairs" CASCADE;
DROP TABLE IF EXISTS "encounters" CASCADE;
DROP TABLE IF EXISTS "providers" CASCADE;
DROP TABLE IF EXISTS "copilot_messages" CASCADE;
DROP TABLE IF EXISTS "departments" CASCADE;
DROP TABLE IF EXISTS "copilot_sessions" CASCADE;
DROP TABLE IF EXISTS "users" CASCADE;
DROP TABLE IF EXISTS "schema_registry" CASCADE;
DROP TABLE IF EXISTS "patients" CASCADE;
DROP TABLE IF EXISTS "facilities" CASCADE;
DROP TABLE IF EXISTS "audit_logs" CASCADE;
DROP TABLE IF EXISTS "alerts" CASCADE;

DROP ROLE IF EXISTS hc_readonly;
