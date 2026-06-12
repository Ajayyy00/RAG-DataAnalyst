"""Healthcare domain ORM models (OLAP schema)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ── Reference / Master Tables ─────────────────────────────────────────────────

class Facility(Base):
    """Hospital, clinic, or care centre."""

    __tablename__ = "facilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(2))
    facility_type: Mapped[str | None] = mapped_column(String(50))  # Hospital | Clinic | Lab
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    departments: Mapped[List["Department"]] = relationship("Department", back_populates="facility")


class Department(Base):
    """Clinical department within a facility."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    dept_type: Mapped[str | None] = mapped_column(String(50))  # Inpatient | Outpatient | ED | ICU
    facility_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("facilities.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    facility: Mapped["Facility"] = relationship("Facility", back_populates="departments")
    providers: Mapped[List["Provider"]] = relationship("Provider", back_populates="department")
    encounters: Mapped[List["Encounter"]] = relationship("Encounter", back_populates="department")


class Provider(Base):
    """Clinical provider (physician, nurse, etc.)."""

    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    npi: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    specialty: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    department: Mapped["Department"] = relationship("Department", back_populates="providers")


# ── Core Clinical Tables ──────────────────────────────────────────────────────

class Patient(Base):
    """Patient master record."""

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mrn: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(10))
    race: Mapped[str | None] = mapped_column(String(50))
    ethnicity: Mapped[str | None] = mapped_column(String(50))
    zip_code: Mapped[str | None] = mapped_column(String(5))
    insurance_type: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    encounters: Mapped[List["Encounter"]] = relationship("Encounter", back_populates="patient")
    diagnoses: Mapped[List["Diagnosis"]] = relationship("Diagnosis", back_populates="patient")
    medications: Mapped[List["Medication"]] = relationship("Medication", back_populates="patient")
    lab_results: Mapped[List["LabResult"]] = relationship("LabResult", back_populates="patient")
    vital_signs: Mapped[List["VitalSign"]] = relationship("VitalSign", back_populates="patient")


class Encounter(Base):
    """Patient visit / encounter record."""

    __tablename__ = "encounters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    encounter_type: Mapped[str] = mapped_column(String(50), nullable=False)  # Inpatient | Outpatient | ED | Telehealth
    admit_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    discharge_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discharge_disp: Mapped[str | None] = mapped_column(String(100))  # Home | SNF | Expired
    drg_code: Mapped[str | None] = mapped_column(String(10))
    drg_description: Mapped[str | None] = mapped_column(Text)
    total_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    total_payment: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    patient: Mapped["Patient"] = relationship("Patient", back_populates="encounters")
    department: Mapped["Department"] = relationship("Department", back_populates="encounters")
    diagnoses: Mapped[List["Diagnosis"]] = relationship("Diagnosis", back_populates="encounter")
    procedures: Mapped[List["Procedure"]] = relationship("Procedure", back_populates="encounter")
    medications: Mapped[List["Medication"]] = relationship("Medication", back_populates="encounter")
    lab_results: Mapped[List["LabResult"]] = relationship("LabResult", back_populates="encounter")
    vital_signs: Mapped[List["VitalSign"]] = relationship("VitalSign", back_populates="encounter")
    claims: Mapped[List["Claim"]] = relationship("Claim", back_populates="encounter")


class Diagnosis(Base):
    """ICD-10 diagnosis linked to an encounter."""

    __tablename__ = "diagnoses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    icd10_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    icd10_desc: Mapped[str | None] = mapped_column(Text)
    diagnosis_type: Mapped[str | None] = mapped_column(String(20))  # Primary | Secondary | Admitting
    diagnosis_date: Mapped[date | None] = mapped_column(Date)
    is_chronic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="diagnoses")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="diagnoses")


class Procedure(Base):
    """CPT procedure linked to an encounter."""

    __tablename__ = "procedures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    cpt_code: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    cpt_desc: Mapped[str | None] = mapped_column(Text)
    procedure_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    charge_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="procedures")


class Medication(Base):
    """Medication order linked to a patient and optionally an encounter."""

    __tablename__ = "medications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("encounters.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    drug_name: Mapped[str | None] = mapped_column(String(200))
    ndc_code: Mapped[str | None] = mapped_column(String(11))
    rxnorm_code: Mapped[str | None] = mapped_column(String(20))
    dose: Mapped[str | None] = mapped_column(String(50))
    unit: Mapped[str | None] = mapped_column(String(20))
    route: Mapped[str | None] = mapped_column(String(50))
    frequency: Mapped[str | None] = mapped_column(String(50))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    prescriber_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="medications")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="medications")


class LabResult(Base):
    """Laboratory test result."""

    __tablename__ = "lab_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("encounters.id"))
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    loinc_code: Mapped[str | None] = mapped_column(String(10), index=True)
    test_name: Mapped[str] = mapped_column(String(200), nullable=False)
    result_value: Mapped[str | None] = mapped_column(String(100))
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    unit: Mapped[str | None] = mapped_column(String(50))
    reference_low: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    reference_high: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    abnormal_flag: Mapped[str | None] = mapped_column(String(5))  # H | L | HH | LL | N
    result_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ordering_prov: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("providers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="lab_results")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="lab_results")


class VitalSign(Base):
    """Vital sign reading captured during an encounter."""

    __tablename__ = "vital_signs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    systolic_bp: Mapped[int | None] = mapped_column(Integer)
    diastolic_bp: Mapped[int | None] = mapped_column(Integer)
    heart_rate: Mapped[int | None] = mapped_column(Integer)
    respiratory_rate: Mapped[int | None] = mapped_column(Integer)
    temperature_f: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    spo2_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="vital_signs")
    patient: Mapped["Patient"] = relationship("Patient", back_populates="vital_signs")


class Claim(Base):
    """Insurance claim linked to an encounter."""

    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    claim_type: Mapped[str | None] = mapped_column(String(20))  # Professional | Institutional
    submission_date: Mapped[date | None] = mapped_column(Date)
    payer_name: Mapped[str | None] = mapped_column(String(100))
    billed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    allowed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    denial_reason: Mapped[str | None] = mapped_column(String(200))
    claim_status: Mapped[str | None] = mapped_column(String(20), index=True)  # Paid | Denied | Pending
    adjudication_dt: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="claims")


class Readmission(Base):
    """Tracks 30-day readmission events."""

    __tablename__ = "readmissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    index_encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    readmit_encounter_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("encounters.id"), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("patients.id"), nullable=False, index=True)
    days_to_readmit: Mapped[int | None] = mapped_column(Integer)
    readmit_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
