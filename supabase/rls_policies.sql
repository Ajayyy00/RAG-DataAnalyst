-- ============================================================================
--  Healthcare Copilot — Supabase schema bundle (AUTO-GENERATED)
--  Source of truth: SQLAlchemy models (regenerate via
--  backend/scripts/emit_supabase_sql.py). Do not hand-edit.
--
--  Apply:  paste into Supabase SQL editor, or
--          psql "$SUPABASE_DB_URL" -f supabase/migration.sql
--
--  Security model preserved from the self-hosted deployment:
--    * Transaction-local GUC `app.current_user_role` drives RLS. The trusted
--      backend (GUC unset) keeps full access; AI-generated SQL runs under the
--      read-only role with the GUC set => SELECT-only, role-gated.
--    * PHI columns on `users` stay TEXT (Fernet ciphertext, encrypted by the app).
--    * PostgREST roles (anon, authenticated) are REVOKED from all PHI tables.
-- ============================================================================

-- ── Row-Level Security (GUC-driven, mirrors Alembic b2c3d4e5f6a7) ──────────
ALTER TABLE "patients" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "patients" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "patients_trusted" ON "patients";
DROP POLICY IF EXISTS "patients_role_read" ON "patients";
CREATE POLICY "patients_trusted" ON "patients" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "patients_role_read" ON "patients" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "encounters" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "encounters" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "encounters_trusted" ON "encounters";
DROP POLICY IF EXISTS "encounters_role_read" ON "encounters";
CREATE POLICY "encounters_trusted" ON "encounters" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "encounters_role_read" ON "encounters" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "diagnoses" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "diagnoses" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "diagnoses_trusted" ON "diagnoses";
DROP POLICY IF EXISTS "diagnoses_role_read" ON "diagnoses";
CREATE POLICY "diagnoses_trusted" ON "diagnoses" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "diagnoses_role_read" ON "diagnoses" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "procedures" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "procedures" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "procedures_trusted" ON "procedures";
DROP POLICY IF EXISTS "procedures_role_read" ON "procedures";
CREATE POLICY "procedures_trusted" ON "procedures" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "procedures_role_read" ON "procedures" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "medications" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "medications" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "medications_trusted" ON "medications";
DROP POLICY IF EXISTS "medications_role_read" ON "medications";
CREATE POLICY "medications_trusted" ON "medications" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "medications_role_read" ON "medications" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "lab_results" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "lab_results" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "lab_results_trusted" ON "lab_results";
DROP POLICY IF EXISTS "lab_results_role_read" ON "lab_results";
CREATE POLICY "lab_results_trusted" ON "lab_results" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "lab_results_role_read" ON "lab_results" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "vital_signs" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "vital_signs" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "vital_signs_trusted" ON "vital_signs";
DROP POLICY IF EXISTS "vital_signs_role_read" ON "vital_signs";
CREATE POLICY "vital_signs_trusted" ON "vital_signs" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "vital_signs_role_read" ON "vital_signs" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "readmissions" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "readmissions" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "readmissions_trusted" ON "readmissions";
DROP POLICY IF EXISTS "readmissions_role_read" ON "readmissions";
CREATE POLICY "readmissions_trusted" ON "readmissions" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "readmissions_role_read" ON "readmissions" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "providers" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "providers" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "providers_trusted" ON "providers";
DROP POLICY IF EXISTS "providers_role_read" ON "providers";
CREATE POLICY "providers_trusted" ON "providers" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "providers_role_read" ON "providers" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','doctor','nurse','analyst'));

ALTER TABLE "claims" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "claims" FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "claims_trusted" ON "claims";
DROP POLICY IF EXISTS "claims_role_read" ON "claims";
CREATE POLICY "claims_trusted" ON "claims" FOR ALL USING (current_setting('app.current_user_role', true) IS NULL) WITH CHECK (current_setting('app.current_user_role', true) IS NULL);
CREATE POLICY "claims_role_read" ON "claims" FOR SELECT USING (current_setting('app.current_user_role', true) IN ('admin','analyst'));

-- Defense in depth: keep PHI out of the PostgREST data API entirely.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "patients" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "encounters" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "diagnoses" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "procedures" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "medications" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "lab_results" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "vital_signs" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "readmissions" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "providers" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "claims" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "users" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "audit_logs" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "copilot_sessions" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN REVOKE ALL ON "copilot_messages" FROM anon; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "patients" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "encounters" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "diagnoses" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "procedures" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "medications" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "lab_results" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "vital_signs" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "readmissions" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "providers" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "claims" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "users" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "audit_logs" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "copilot_sessions" FROM authenticated; END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN REVOKE ALL ON "copilot_messages" FROM authenticated; END IF;
END $$;
