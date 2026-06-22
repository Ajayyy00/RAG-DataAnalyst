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

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ── Tables ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS alerts (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	event_type VARCHAR NOT NULL, 
	severity VARCHAR NOT NULL, 
	message VARCHAR NOT NULL, 
	metadata_json JSON, 
	resolved BOOLEAN DEFAULT false NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	user_id UUID, 
	endpoint VARCHAR(255) NOT NULL, 
	method VARCHAR(10) NOT NULL, 
	status_code INTEGER NOT NULL, 
	ip_address VARCHAR(50), 
	duration_ms FLOAT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS facilities (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	city VARCHAR(100), 
	state VARCHAR(2), 
	facility_type VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS patients (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	mrn VARCHAR(20) NOT NULL, 
	first_name VARCHAR(100) NOT NULL, 
	last_name VARCHAR(100) NOT NULL, 
	date_of_birth DATE NOT NULL, 
	gender VARCHAR(10), 
	race VARCHAR(50), 
	ethnicity VARCHAR(50), 
	zip_code VARCHAR(5), 
	insurance_type VARCHAR(50), 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS schema_registry (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	table_name VARCHAR(100) NOT NULL, 
	column_name VARCHAR(100) NOT NULL, 
	data_type VARCHAR(50), 
	is_nullable BOOLEAN, 
	column_comment TEXT, 
	last_indexed_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS users (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	email VARCHAR(255) NOT NULL, 
	username VARCHAR(100) NOT NULL, 
	hashed_password VARCHAR(255) NOT NULL, 
	first_name TEXT, 
	last_name TEXT, 
	role VARCHAR(20) NOT NULL, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	last_login_at TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS copilot_sessions (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	user_id UUID NOT NULL, 
	title VARCHAR(200), 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	last_active_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE TABLE IF NOT EXISTS departments (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	name VARCHAR(100) NOT NULL, 
	dept_type VARCHAR(50), 
	facility_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(facility_id) REFERENCES facilities (id)
);

CREATE TABLE IF NOT EXISTS copilot_messages (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	session_id UUID NOT NULL, 
	role VARCHAR(10) NOT NULL, 
	content TEXT NOT NULL, 
	generated_sql TEXT, 
	sql_valid BOOLEAN, 
	execution_ms INTEGER, 
	row_count INTEGER, 
	chart_type VARCHAR(50), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(session_id) REFERENCES copilot_sessions (id)
);

CREATE TABLE IF NOT EXISTS providers (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	npi VARCHAR(10) NOT NULL, 
	first_name VARCHAR(100), 
	last_name VARCHAR(100), 
	provider_type VARCHAR(20), 
	specialty VARCHAR(100), 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	department_id UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(department_id) REFERENCES departments (id)
);

CREATE TABLE IF NOT EXISTS encounters (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	patient_id UUID NOT NULL, 
	provider_id UUID, 
	department_id UUID, 
	encounter_type VARCHAR(50) NOT NULL, 
	admit_date TIMESTAMP WITH TIME ZONE NOT NULL, 
	discharge_date TIMESTAMP WITH TIME ZONE, 
	discharge_disp VARCHAR(100), 
	drg_code VARCHAR(10), 
	drg_description TEXT, 
	total_charge NUMERIC(12, 2), 
	total_payment NUMERIC(12, 2), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id), 
	FOREIGN KEY(provider_id) REFERENCES providers (id), 
	FOREIGN KEY(department_id) REFERENCES departments (id)
);

CREATE TABLE IF NOT EXISTS nl_sql_pairs (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	message_id UUID, 
	nl_question TEXT NOT NULL, 
	generated_sql TEXT NOT NULL, 
	corrected_sql TEXT, 
	is_validated BOOLEAN DEFAULT false NOT NULL, 
	is_correct BOOLEAN, 
	difficulty VARCHAR(20), 
	query_type VARCHAR(50), 
	schema_version VARCHAR(20), 
	split VARCHAR(10) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(message_id) REFERENCES copilot_messages (id)
);

CREATE TABLE IF NOT EXISTS claims (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	encounter_id UUID NOT NULL, 
	patient_id UUID NOT NULL, 
	claim_type VARCHAR(20), 
	submission_date DATE, 
	payer_name VARCHAR(100), 
	billed_amount NUMERIC(12, 2), 
	allowed_amount NUMERIC(12, 2), 
	paid_amount NUMERIC(12, 2), 
	denial_reason VARCHAR(200), 
	claim_status VARCHAR(20), 
	adjudication_dt DATE, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(encounter_id) REFERENCES encounters (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id)
);

CREATE TABLE IF NOT EXISTS diagnoses (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	encounter_id UUID NOT NULL, 
	patient_id UUID NOT NULL, 
	icd10_code VARCHAR(10) NOT NULL, 
	icd10_desc TEXT, 
	diagnosis_type VARCHAR(20), 
	diagnosis_date DATE, 
	is_chronic BOOLEAN DEFAULT false NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(encounter_id) REFERENCES encounters (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id)
);

CREATE TABLE IF NOT EXISTS lab_results (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	encounter_id UUID, 
	patient_id UUID NOT NULL, 
	loinc_code VARCHAR(10), 
	test_name VARCHAR(200) NOT NULL, 
	result_value VARCHAR(100), 
	numeric_value NUMERIC(12, 4), 
	unit VARCHAR(50), 
	reference_low NUMERIC(12, 4), 
	reference_high NUMERIC(12, 4), 
	abnormal_flag VARCHAR(5), 
	result_date TIMESTAMP WITH TIME ZONE NOT NULL, 
	ordering_prov UUID, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(encounter_id) REFERENCES encounters (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id), 
	FOREIGN KEY(ordering_prov) REFERENCES providers (id)
);

CREATE TABLE IF NOT EXISTS medications (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	encounter_id UUID, 
	patient_id UUID NOT NULL, 
	drug_name VARCHAR(200), 
	ndc_code VARCHAR(11), 
	rxnorm_code VARCHAR(20), 
	dose VARCHAR(50), 
	unit VARCHAR(20), 
	route VARCHAR(50), 
	frequency VARCHAR(50), 
	start_date DATE, 
	end_date DATE, 
	prescriber_id UUID, 
	is_active BOOLEAN DEFAULT true NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(encounter_id) REFERENCES encounters (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id), 
	FOREIGN KEY(prescriber_id) REFERENCES providers (id)
);

CREATE TABLE IF NOT EXISTS procedures (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	encounter_id UUID NOT NULL, 
	patient_id UUID NOT NULL, 
	cpt_code VARCHAR(10) NOT NULL, 
	cpt_desc TEXT, 
	procedure_date TIMESTAMP WITH TIME ZONE, 
	provider_id UUID, 
	quantity INTEGER NOT NULL, 
	charge_amount NUMERIC(10, 2), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(encounter_id) REFERENCES encounters (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id), 
	FOREIGN KEY(provider_id) REFERENCES providers (id)
);

CREATE TABLE IF NOT EXISTS readmissions (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	index_encounter_id UUID NOT NULL, 
	readmit_encounter_id UUID NOT NULL, 
	patient_id UUID NOT NULL, 
	days_to_readmit INTEGER, 
	readmit_reason TEXT, 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(index_encounter_id) REFERENCES encounters (id), 
	FOREIGN KEY(readmit_encounter_id) REFERENCES encounters (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id)
);

CREATE TABLE IF NOT EXISTS vital_signs (
	id UUID DEFAULT gen_random_uuid() NOT NULL, 
	encounter_id UUID NOT NULL, 
	patient_id UUID NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	systolic_bp INTEGER, 
	diastolic_bp INTEGER, 
	heart_rate INTEGER, 
	respiratory_rate INTEGER, 
	temperature_f NUMERIC(5, 2), 
	spo2_pct NUMERIC(5, 2), 
	weight_kg NUMERIC(6, 2), 
	height_cm NUMERIC(5, 2), 
	created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(encounter_id) REFERENCES encounters (id), 
	FOREIGN KEY(patient_id) REFERENCES patients (id)
);

-- ── Indexes ───────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS ix_alerts_event_type ON alerts (event_type);
CREATE INDEX IF NOT EXISTS ix_alerts_severity ON alerts (severity);
CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at);
CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_patients_mrn ON patients (mrn);
CREATE INDEX IF NOT EXISTS ix_schema_registry_table_name ON schema_registry (table_name);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email);
CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);
CREATE INDEX IF NOT EXISTS ix_copilot_sessions_user_id ON copilot_sessions (user_id);
CREATE INDEX IF NOT EXISTS ix_copilot_messages_created_at ON copilot_messages (created_at);
CREATE INDEX IF NOT EXISTS ix_copilot_messages_session_id ON copilot_messages (session_id);
CREATE UNIQUE INDEX IF NOT EXISTS ix_providers_npi ON providers (npi);
CREATE INDEX IF NOT EXISTS ix_providers_provider_type ON providers (provider_type);
CREATE INDEX IF NOT EXISTS ix_encounters_admit_date ON encounters (admit_date);
CREATE INDEX IF NOT EXISTS ix_encounters_patient_id ON encounters (patient_id);
CREATE INDEX IF NOT EXISTS ix_claims_claim_status ON claims (claim_status);
CREATE INDEX IF NOT EXISTS ix_claims_encounter_id ON claims (encounter_id);
CREATE INDEX IF NOT EXISTS ix_claims_patient_id ON claims (patient_id);
CREATE INDEX IF NOT EXISTS ix_diagnoses_encounter_id ON diagnoses (encounter_id);
CREATE INDEX IF NOT EXISTS ix_diagnoses_icd10_code ON diagnoses (icd10_code);
CREATE INDEX IF NOT EXISTS ix_diagnoses_patient_id ON diagnoses (patient_id);
CREATE INDEX IF NOT EXISTS ix_lab_results_loinc_code ON lab_results (loinc_code);
CREATE INDEX IF NOT EXISTS ix_lab_results_patient_id ON lab_results (patient_id);
CREATE INDEX IF NOT EXISTS ix_lab_results_result_date ON lab_results (result_date);
CREATE INDEX IF NOT EXISTS ix_medications_patient_id ON medications (patient_id);
CREATE INDEX IF NOT EXISTS ix_procedures_cpt_code ON procedures (cpt_code);
CREATE INDEX IF NOT EXISTS ix_procedures_encounter_id ON procedures (encounter_id);
CREATE INDEX IF NOT EXISTS ix_procedures_patient_id ON procedures (patient_id);
CREATE INDEX IF NOT EXISTS ix_readmissions_patient_id ON readmissions (patient_id);
CREATE INDEX IF NOT EXISTS ix_vital_signs_encounter_id ON vital_signs (encounter_id);
CREATE INDEX IF NOT EXISTS ix_vital_signs_patient_id ON vital_signs (patient_id);

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

-- ── Least-privilege executor role for AI-generated SQL ─────────────────────
-- Set the password first:  \set ro_password 'your-strong-password'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'hc_readonly') THEN
    CREATE ROLE hc_readonly LOGIN PASSWORD :'ro_password'
      NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END $$;
GRANT USAGE ON SCHEMA public TO hc_readonly;
    GRANT SELECT ON "patients" TO hc_readonly;
    GRANT SELECT ON "encounters" TO hc_readonly;
    GRANT SELECT ON "diagnoses" TO hc_readonly;
    GRANT SELECT ON "procedures" TO hc_readonly;
    GRANT SELECT ON "medications" TO hc_readonly;
    GRANT SELECT ON "lab_results" TO hc_readonly;
    GRANT SELECT ON "vital_signs" TO hc_readonly;
    GRANT SELECT ON "readmissions" TO hc_readonly;
    GRANT SELECT ON "providers" TO hc_readonly;
    GRANT SELECT ON "claims" TO hc_readonly;
    GRANT SELECT ON "departments" TO hc_readonly;
    GRANT SELECT ON "facilities" TO hc_readonly;
-- No grants on users / audit_logs / copilot_* => analysts can never read them.

