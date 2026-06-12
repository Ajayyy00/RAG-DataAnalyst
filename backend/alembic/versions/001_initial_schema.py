"""Initial healthcare copilot schema.

Revision ID: 001
Revises: 
Create Date: 2026-06-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable UUID extension
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pg_trgm"')

    # ── Users ─────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("username", sa.String(100), nullable=False, unique=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("role", sa.String(20), nullable=False, server_default="analyst"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_users_email", "users", ["email"])
    op.create_index("ix_users_username", "users", ["username"])

    # ── Facilities ────────────────────────────────────────────
    op.create_table(
        "facilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(2)),
        sa.Column("facility_type", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Departments ───────────────────────────────────────────
    op.create_table(
        "departments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("dept_type", sa.String(50)),
        sa.Column("facility_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("facilities.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Providers ─────────────────────────────────────────────
    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("npi", sa.String(10), nullable=False, unique=True),
        sa.Column("first_name", sa.String(100)),
        sa.Column("last_name", sa.String(100)),
        sa.Column("specialty", sa.String(100)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Patients ──────────────────────────────────────────────
    op.create_table(
        "patients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("mrn", sa.String(20), nullable=False, unique=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("gender", sa.String(10)),
        sa.Column("race", sa.String(50)),
        sa.Column("ethnicity", sa.String(50)),
        sa.Column("zip_code", sa.String(5)),
        sa.Column("insurance_type", sa.String(50)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_patients_mrn", "patients", ["mrn"])
    op.create_index("ix_patients_dob", "patients", ["date_of_birth"])

    # ── Encounters ────────────────────────────────────────────
    op.create_table(
        "encounters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id")),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id")),
        sa.Column("encounter_type", sa.String(50), nullable=False),
        sa.Column("admit_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("discharge_date", sa.DateTime(timezone=True)),
        sa.Column("discharge_disp", sa.String(100)),
        sa.Column("drg_code", sa.String(10)),
        sa.Column("drg_description", sa.Text()),
        sa.Column("total_charge", sa.Numeric(12, 2)),
        sa.Column("total_payment", sa.Numeric(12, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_encounters_patient_id", "encounters", ["patient_id"])
    op.create_index("ix_encounters_admit_date", "encounters", ["admit_date"])

    # ── Diagnoses ─────────────────────────────────────────────
    op.create_table(
        "diagnoses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("icd10_code", sa.String(10), nullable=False),
        sa.Column("icd10_desc", sa.Text()),
        sa.Column("diagnosis_type", sa.String(20)),
        sa.Column("diagnosis_date", sa.Date()),
        sa.Column("is_chronic", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_diagnoses_icd10", "diagnoses", ["icd10_code"])
    op.create_index("ix_diagnoses_patient", "diagnoses", ["patient_id"])

    # ── Procedures ────────────────────────────────────────────
    op.create_table(
        "procedures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("cpt_code", sa.String(10), nullable=False),
        sa.Column("cpt_desc", sa.Text()),
        sa.Column("procedure_date", sa.DateTime(timezone=True)),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id")),
        sa.Column("quantity", sa.Integer(), server_default="1"),
        sa.Column("charge_amount", sa.Numeric(10, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Medications ───────────────────────────────────────────
    op.create_table(
        "medications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id")),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("drug_name", sa.String(200)),
        sa.Column("ndc_code", sa.String(11)),
        sa.Column("rxnorm_code", sa.String(20)),
        sa.Column("dose", sa.String(50)),
        sa.Column("unit", sa.String(20)),
        sa.Column("route", sa.String(50)),
        sa.Column("frequency", sa.String(50)),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("prescriber_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id")),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Lab Results ───────────────────────────────────────────
    op.create_table(
        "lab_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id")),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("loinc_code", sa.String(10)),
        sa.Column("test_name", sa.String(200), nullable=False),
        sa.Column("result_value", sa.String(100)),
        sa.Column("numeric_value", sa.Numeric(12, 4)),
        sa.Column("unit", sa.String(50)),
        sa.Column("reference_low", sa.Numeric(12, 4)),
        sa.Column("reference_high", sa.Numeric(12, 4)),
        sa.Column("abnormal_flag", sa.String(5)),
        sa.Column("result_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ordering_prov", postgresql.UUID(as_uuid=True), sa.ForeignKey("providers.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Vital Signs ───────────────────────────────────────────
    op.create_table(
        "vital_signs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("systolic_bp", sa.Integer()),
        sa.Column("diastolic_bp", sa.Integer()),
        sa.Column("heart_rate", sa.Integer()),
        sa.Column("respiratory_rate", sa.Integer()),
        sa.Column("temperature_f", sa.Numeric(5, 2)),
        sa.Column("spo2_pct", sa.Numeric(5, 2)),
        sa.Column("weight_kg", sa.Numeric(6, 2)),
        sa.Column("height_cm", sa.Numeric(5, 2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Claims ────────────────────────────────────────────────
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("claim_type", sa.String(20)),
        sa.Column("submission_date", sa.Date()),
        sa.Column("payer_name", sa.String(100)),
        sa.Column("billed_amount", sa.Numeric(12, 2)),
        sa.Column("allowed_amount", sa.Numeric(12, 2)),
        sa.Column("paid_amount", sa.Numeric(12, 2)),
        sa.Column("denial_reason", sa.String(200)),
        sa.Column("claim_status", sa.String(20)),
        sa.Column("adjudication_dt", sa.Date()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Readmissions ──────────────────────────────────────────
    op.create_table(
        "readmissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("index_encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("readmit_encounter_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("encounters.id"), nullable=False),
        sa.Column("patient_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("days_to_readmit", sa.Integer()),
        sa.Column("readmit_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Copilot Sessions ──────────────────────────────────────
    op.create_table(
        "copilot_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("last_active_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_copilot_sessions_user", "copilot_sessions", ["user_id"])

    # ── Copilot Messages ──────────────────────────────────────
    op.create_table(
        "copilot_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("copilot_sessions.id"), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("generated_sql", sa.Text()),
        sa.Column("sql_valid", sa.Boolean()),
        sa.Column("execution_ms", sa.Integer()),
        sa.Column("row_count", sa.Integer()),
        sa.Column("chart_type", sa.String(50)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_copilot_messages_session", "copilot_messages", ["session_id"])

    # ── NL-SQL Pairs ──────────────────────────────────────────
    op.create_table(
        "nl_sql_pairs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("copilot_messages.id")),
        sa.Column("nl_question", sa.Text(), nullable=False),
        sa.Column("generated_sql", sa.Text(), nullable=False),
        sa.Column("corrected_sql", sa.Text()),
        sa.Column("is_validated", sa.Boolean(), server_default="false"),
        sa.Column("is_correct", sa.Boolean()),
        sa.Column("difficulty", sa.String(20)),
        sa.Column("query_type", sa.String(50)),
        sa.Column("schema_version", sa.String(20)),
        sa.Column("split", sa.String(10), server_default="train"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── Schema Registry ───────────────────────────────────────
    op.create_table(
        "schema_registry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("table_name", sa.String(100), nullable=False),
        sa.Column("column_name", sa.String(100), nullable=False),
        sa.Column("data_type", sa.String(50)),
        sa.Column("is_nullable", sa.Boolean()),
        sa.Column("column_comment", sa.Text()),
        sa.Column("last_indexed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("schema_registry")
    op.drop_table("nl_sql_pairs")
    op.drop_table("copilot_messages")
    op.drop_table("copilot_sessions")
    op.drop_table("readmissions")
    op.drop_table("claims")
    op.drop_table("vital_signs")
    op.drop_table("lab_results")
    op.drop_table("medications")
    op.drop_table("procedures")
    op.drop_table("diagnoses")
    op.drop_table("encounters")
    op.drop_table("patients")
    op.drop_table("providers")
    op.drop_table("departments")
    op.drop_table("facilities")
    op.drop_table("users")
