#!/usr/bin/env python
"""
Healthcare Copilot — Database Seeder
=====================================
Populates all 17 tables with realistic synthetic healthcare data.

Usage:
    python scripts/seed_db.py [--drop-existing]

Requirements:
    - PostgreSQL running and .env configured
    - .venv activated OR run via: .venv/Scripts/python scripts/seed_db.py
    - Alembic migrations already applied: alembic upgrade head
"""

import argparse
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# ── Add backend root to path ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import asyncio
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# ── Import models ────────────────────────────────────────────────────────────
from app.config import get_settings
from app.db.models.healthcare import (
    Claim, Department, Diagnosis, Encounter, Facility,
    LabResult, Medication, Patient, Procedure, Provider,
    Readmission, VitalSign,
)
from app.db.models.user import User
from app.db.models.copilot import CopilotSession, CopilotMessage

settings = get_settings()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Realistic Reference Data ─────────────────────────────────────────────────

FACILITIES = [
    ("Metro General Hospital",     "Chicago",      "IL", "Hospital"),
    ("Riverside Medical Center",   "Los Angeles",  "CA", "Hospital"),
    ("Northeast Specialty Clinic", "Boston",       "MA", "Clinic"),
    ("Sunnydale Outpatient Care",  "Phoenix",      "AZ", "Clinic"),
    ("Bay Area Diagnostics",       "San Francisco","CA", "Lab"),
]

DEPARTMENTS = [
    ("Emergency Department",  "ED"),
    ("Cardiology",            "Inpatient"),
    ("Internal Medicine",     "Inpatient"),
    ("Orthopedics",           "Outpatient"),
    ("Oncology",              "Inpatient"),
    ("Neurology",             "Outpatient"),
    ("Pulmonology",           "Inpatient"),
    ("Endocrinology",         "Outpatient"),
    ("Gastroenterology",      "Outpatient"),
    ("Nephrology",            "Inpatient"),
    ("Radiology",             "Outpatient"),
    ("Laboratory",            "Outpatient"),
    ("ICU",                   "ICU"),
    ("Pediatrics",            "Inpatient"),
    ("Obstetrics",            "Inpatient"),
]

PROVIDERS = [
    ("Sarah",  "Chen",     "Cardiologist"),
    ("Michael","Rodriguez","Emergency Medicine"),
    ("Emily",  "Johnson",  "Internal Medicine"),
    ("David",  "Kim",      "Orthopedic Surgery"),
    ("Lisa",   "Patel",    "Oncologist"),
    ("James",  "Thompson", "Neurologist"),
    ("Maria",  "Garcia",   "Pulmonologist"),
    ("Robert", "Williams", "Endocrinologist"),
    ("Jennifer","Martinez","Gastroenterologist"),
    ("Kevin",  "Brown",    "Nephrologist"),
    ("Amanda", "Davis",    "Radiologist"),
    ("Christopher","Wilson","Pediatrician"),
    ("Rachel", "Anderson", "Obstetrician"),
    ("Daniel", "Taylor",   "Emergency Medicine"),
    ("Nicole", "Moore",    "Internal Medicine"),
    ("Brian",  "Jackson",  "Cardiologist"),
    ("Stephanie","White",  "Hospitalist"),
    ("Eric",   "Harris",   "Intensivist"),
    ("Ashley", "Clark",    "Family Medicine"),
    ("Ryan",   "Lewis",    "Urgent Care"),
    ("Lauren", "Robinson", "Emergency Medicine"),
    ("Justin", "Walker",   "Internal Medicine"),
    ("Megan",  "Hall",     "Cardiologist"),
    ("Tyler",  "Allen",    "Orthopedic Surgery"),
    ("Hannah", "Young",    "Endocrinologist"),
    ("Nathan", "King",     "Nephrologist"),
    ("Brittany","Wright",  "Oncologist"),
    ("Andrew", "Scott",    "Neurologist"),
    ("Samantha","Green",   "Hospitalist"),
    ("Joseph", "Baker",    "Pulmonologist"),
]

# ICD-10 codes with descriptions and chronic flag
ICD10_CODES = [
    ("E11.9",  "Type 2 diabetes mellitus without complications",            True),
    ("I10",    "Essential (primary) hypertension",                          True),
    ("I25.10", "Atherosclerotic heart disease of native coronary artery",   True),
    ("J18.9",  "Pneumonia, unspecified organism",                           False),
    ("N18.3",  "Chronic kidney disease, stage 3",                           True),
    ("Z87.891","Personal history of nicotine dependence",                   False),
    ("E78.5",  "Hyperlipidemia, unspecified",                               True),
    ("M54.5",  "Low back pain",                                             False),
    ("J44.1",  "COPD with acute exacerbation",                              True),
    ("F32.1",  "Major depressive disorder, single episode, moderate",       True),
    ("K92.1",  "Melena",                                                    False),
    ("I50.9",  "Heart failure, unspecified",                                True),
    ("C34.10", "Malignant neoplasm of upper lobe, unspecified bronchus",    True),
    ("S52.501A","Unspecified fracture of lower end of radius, initial",     False),
    ("R05.9",  "Cough, unspecified",                                        False),
    ("I63.9",  "Cerebral infarction, unspecified",                          False),
    ("A41.9",  "Sepsis, unspecified organism",                              False),
    ("K57.30", "Diverticulosis of large intestine without perforation",     True),
    ("G30.9",  "Alzheimer's disease, unspecified",                          True),
    ("E11.65", "Type 2 diabetes mellitus with hyperglycemia",               True),
    ("N39.0",  "Urinary tract infection, site not specified",               False),
    ("R07.9",  "Chest pain, unspecified",                                   False),
    ("I21.9",  "Acute myocardial infarction, unspecified",                  False),
    ("B97.29", "Other coronavirus as cause of diseases classified elsewhere",False),
    ("E87.1",  "Hypo-osmolality and hyponatremia",                         False),
]

# CPT codes
CPT_CODES = [
    ("99213", "Office or outpatient visit, established patient, low complexity",   150.00),
    ("99214", "Office or outpatient visit, established patient, moderate complexity",220.00),
    ("99223", "Initial hospital care, high severity",                               450.00),
    ("99232", "Subsequent hospital care, moderate severity",                        175.00),
    ("99291", "Critical care, first 30–74 minutes",                                 550.00),
    ("71046", "Radiologic examination, chest, 2 views",                             95.00),
    ("93000", "Electrocardiogram, routine ECG",                                     65.00),
    ("80053", "Comprehensive metabolic panel",                                       40.00),
    ("85025", "Blood count; complete (CBC), automated",                              25.00),
    ("36415", "Collection of venous blood by venipuncture",                         15.00),
    ("27447", "Total knee replacement",                                           12000.00),
    ("43239", "Esophagogastroduodenoscopy with biopsy",                            1200.00),
    ("45378", "Colonoscopy, flexible",                                              900.00),
    ("93306", "Echocardiography, transthoracic",                                    800.00),
    ("70553", "MRI brain without and with contrast",                               2200.00),
]

# LOINC codes for lab results
LOINC_LABS = [
    ("2345-7",  "Glucose [Mass/volume] in Serum",          "mg/dL",  70,  100,  lambda: round(random.gauss(105, 30), 1)),
    ("4548-4",  "Hemoglobin A1c/Hemoglobin.total in Blood","%",       4.0,  5.6, lambda: round(random.gauss(7.2, 1.5), 1)),
    ("2160-0",  "Creatinine [Mass/volume] in Serum",        "mg/dL",  0.6,  1.2, lambda: round(random.gauss(1.1, 0.4), 2)),
    ("2823-3",  "Potassium [Moles/volume] in Serum",        "mEq/L",  3.5,  5.0, lambda: round(random.gauss(4.1, 0.4), 1)),
    ("2951-2",  "Sodium [Moles/volume] in Serum",           "mEq/L", 136,  145,  lambda: round(random.gauss(139, 3), 0)),
    ("718-7",   "Hemoglobin [Mass/volume] in Blood",        "g/dL",   12.0, 17.5,lambda: round(random.gauss(13.5, 2.0), 1)),
    ("6690-2",  "Leukocytes [#/volume] in Blood",           "K/uL",   4.5, 11.0, lambda: round(random.gauss(7.5, 2.5), 1)),
    ("13457-7", "LDL Cholesterol in Serum",                 "mg/dL",   0,  100,  lambda: round(random.gauss(115, 35), 0)),
    ("2093-3",  "Cholesterol [Mass/volume] in Serum",       "mg/dL",   0,  200,  lambda: round(random.gauss(195, 45), 0)),
    ("1742-6",  "Alanine aminotransferase [Enzymatic activity/volume]","U/L", 7, 56, lambda: round(random.gauss(35, 20), 0)),
    ("6768-6",  "Alkaline phosphatase [Enzymatic activity/volume]",    "U/L", 44,147, lambda: round(random.gauss(95, 30), 0)),
    ("14959-1", "Microalbumin [Mass/volume] in Urine",      "mg/L",    0,   30, lambda: round(random.gauss(25, 15), 1)),
    ("30522-7", "C reactive protein [Mass/volume] in Serum","mg/L",    0,   10, lambda: round(random.gauss(8, 6), 1)),
    ("14627-4", "Bicarbonate [Moles/volume] in Venous blood","mEq/L", 22,   29, lambda: round(random.gauss(24, 2), 0)),
    ("2028-9",  "Carbon dioxide [Moles/volume] in Serum",  "mEq/L",   22,   29, lambda: round(random.gauss(24, 2), 0)),
]

MEDICATIONS = [
    ("Metformin",      "860975", "PO",  "500mg", "Twice daily"),
    ("Lisinopril",     "314076", "PO",  "10mg",  "Once daily"),
    ("Atorvastatin",   "617311", "PO",  "40mg",  "Once at bedtime"),
    ("Amlodipine",     "197361", "PO",  "5mg",   "Once daily"),
    ("Omeprazole",     "40790",  "PO",  "20mg",  "Once daily"),
    ("Aspirin",        "1191",   "PO",  "81mg",  "Once daily"),
    ("Furosemide",     "4603",   "PO",  "40mg",  "Once daily"),
    ("Levothyroxine",  "10582",  "PO",  "50mcg", "Once daily"),
    ("Warfarin",       "11289",  "PO",  "5mg",   "Once daily"),
    ("Insulin Glargine","274783","SC",  "20 units","Once at bedtime"),
    ("Gabapentin",     "194044", "PO",  "300mg", "Three times daily"),
    ("Sertraline",     "36437",  "PO",  "50mg",  "Once daily"),
    ("Albuterol",      "435",    "INH", "2.5mg", "Every 4-6 hours PRN"),
    ("Pantoprazole",   "40790",  "IV",  "40mg",  "Twice daily"),
    ("Heparin",        "5224",   "IV",  "25000 units","Continuous infusion"),
    ("Vancomycin",     "11124",  "IV",  "1000mg","Every 12 hours"),
    ("Ceftriaxone",    "25033",  "IV",  "1g",    "Once daily"),
    ("Morphine",       "7052",   "IV",  "2mg",   "Every 4 hours PRN"),
    ("Ondansetron",    "312086", "IV",  "4mg",   "Every 6 hours PRN"),
    ("Dexamethasone",  "3264",   "IV",  "6mg",   "Once daily"),
]

PAYERS = ["Medicare", "Medicaid", "Blue Cross Blue Shield", "Aetna", "Cigna", "UnitedHealth", "Humana", "Self-Pay"]
ENCOUNTER_TYPES = ["Inpatient", "Outpatient", "ED", "Telehealth"]
DISCHARGE_DISPS = ["Home", "SNF", "Home with Services", "Rehabilitation", "Expired", "AMA", "Transfer"]
GENDERS = ["Male", "Female", "Non-binary", "Unknown"]
RACES = ["White", "Black or African American", "Asian", "Hispanic or Latino", "American Indian", "Unknown"]
ETHNICITIES = ["Non-Hispanic", "Hispanic", "Unknown"]
FIRST_NAMES_M = ["James","John","Robert","Michael","William","David","Richard","Joseph","Thomas","Charles","Daniel","Matthew","Anthony","Mark","Donald"]
FIRST_NAMES_F = ["Mary","Patricia","Jennifer","Linda","Barbara","Elizabeth","Susan","Jessica","Sarah","Karen","Lisa","Nancy","Betty","Sandra","Dorothy"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia","Miller","Davis","Wilson","Moore","Taylor","Anderson","Thomas","Jackson","White","Harris","Martin","Thompson","Young","Robinson"]
US_STATES = ["AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA","KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ","NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT","VA","WA","WV","WI","WY"]

DRG_CODES = [
    ("470",  "Major joint replacement or reattachment of lower extremity w/o MCC"),
    ("291",  "Heart failure and shock w MCC"),
    ("292",  "Heart failure and shock w CC"),
    ("194",  "Simple pneumonia and pleurisy w CC"),
    ("690",  "Urinary tract infections w MCC"),
    ("064",  "Intracranial hemorrhage or cerebral infarction w MCC"),
    ("281",  "Acute MI, discharged alive w MCC"),
    ("177",  "Respiratory infections and inflammations w MCC"),
    ("871",  "Septicemia or severe sepsis w/o MV >96 hours w MCC"),
    ("392",  "Esophagitis, gastroent and misc digest disorders w MCC"),
]


def rnd_date_between(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def rnd_dt_between(start: datetime, end: datetime) -> datetime:
    delta = int((end - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, delta))


def abnormal_flag(value: float, low: float, high: float) -> str:
    if value < low * 0.8:
        return "LL"
    elif value < low:
        return "L"
    elif value > high * 1.2:
        return "HH"
    elif value > high:
        return "H"
    return "N"


async def seed(drop_existing: bool = False) -> None:
    print("=" * 60)
    print("  Healthcare Copilot — Database Seeder")
    print("=" * 60)

    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionFactory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionFactory() as db:
        if drop_existing:
            print("\n⚠  Dropping existing seed data...")
            for tbl in [
                "readmissions","claims","vital_signs","lab_results",
                "medications","procedures","diagnoses","encounters",
                "patients","providers","departments","facilities",
                "copilot_messages","copilot_sessions","users",
            ]:
                await db.execute(text(f"TRUNCATE TABLE {tbl} CASCADE"))
            await db.commit()
            print("   Tables truncated.\n")

        # ── 1. Facilities ───────────────────────────────────────────
        print("→ Seeding facilities...")
        facility_objs = []
        for name, city, state, ftype in FACILITIES:
            f = Facility(name=name, city=city, state=state, facility_type=ftype)
            db.add(f)
            facility_objs.append(f)
        await db.flush()
        print(f"  ✓ {len(facility_objs)} facilities")

        # ── 2. Departments ──────────────────────────────────────────
        print("→ Seeding departments...")
        dept_objs = []
        for i, (name, dtype) in enumerate(DEPARTMENTS):
            fac = facility_objs[i % len(facility_objs)]
            d = Department(name=name, dept_type=dtype, facility_id=fac.id)
            db.add(d)
            dept_objs.append(d)
        await db.flush()
        print(f"  ✓ {len(dept_objs)} departments")

        # ── 3. Providers ────────────────────────────────────────────
        print("→ Seeding providers...")
        provider_objs = []
        npi_set = set()
        for first, last, spec in PROVIDERS:
            while True:
                npi = str(random.randint(1000000000, 9999999999))
                if npi not in npi_set:
                    npi_set.add(npi)
                    break
            dept = random.choice(dept_objs)
            p = Provider(
                npi=npi, first_name=first, last_name=last,
                specialty=spec, is_active=True, department_id=dept.id
            )
            db.add(p)
            provider_objs.append(p)
        await db.flush()
        print(f"  ✓ {len(provider_objs)} providers")

        # ── 4. Patients ─────────────────────────────────────────────
        print("→ Seeding 500 patients...")
        patient_objs = []
        mrn_counter = 100001
        for i in range(500):
            gender = random.choice(GENDERS)
            if gender == "Male":
                first = random.choice(FIRST_NAMES_M)
            else:
                first = random.choice(FIRST_NAMES_F)
            last = random.choice(LAST_NAMES)
            dob = rnd_date_between(date(1940, 1, 1), date(2005, 12, 31))
            pat = Patient(
                mrn=str(mrn_counter + i),
                first_name=first,
                last_name=last,
                date_of_birth=dob,
                gender=gender,
                race=random.choice(RACES),
                ethnicity=random.choice(ETHNICITIES),
                zip_code=str(random.randint(10000, 99999)),
                insurance_type=random.choice(PAYERS),
                is_active=random.random() > 0.03,
            )
            db.add(pat)
            patient_objs.append(pat)
        await db.flush()
        print(f"  ✓ {len(patient_objs)} patients")

        # ── 5. Encounters ────────────────────────────────────────────
        print("→ Seeding 1,500 encounters...")
        encounter_objs = []
        now = datetime.now(timezone.utc)
        two_years_ago = now - timedelta(days=730)

        for _ in range(1500):
            patient = random.choice(patient_objs)
            enc_type = random.choice(ENCOUNTER_TYPES)
            admit = rnd_dt_between(two_years_ago, now - timedelta(days=1))

            if enc_type == "Inpatient":
                los_days = random.randint(1, 14)
                discharge = admit + timedelta(days=los_days)
                drg = random.choice(DRG_CODES)
                charge = round(random.uniform(8000, 85000), 2)
            elif enc_type == "ED":
                los_hours = random.randint(2, 24)
                discharge = admit + timedelta(hours=los_hours)
                drg = None
                charge = round(random.uniform(1200, 12000), 2)
            else:
                discharge = admit + timedelta(hours=random.randint(1, 4))
                drg = None
                charge = round(random.uniform(150, 3500), 2)

            payment = round(charge * random.uniform(0.55, 0.92), 2)
            prov = random.choice(provider_objs)
            dept = random.choice(dept_objs)

            enc = Encounter(
                patient_id=patient.id,
                provider_id=prov.id,
                department_id=dept.id,
                encounter_type=enc_type,
                admit_date=admit,
                discharge_date=discharge if random.random() > 0.05 else None,
                discharge_disp=random.choice(DISCHARGE_DISPS) if enc_type in ("Inpatient","ED") else "Home",
                drg_code=drg[0] if drg else None,
                drg_description=drg[1] if drg else None,
                total_charge=Decimal(str(charge)),
                total_payment=Decimal(str(payment)),
            )
            db.add(enc)
            encounter_objs.append(enc)

        await db.flush()
        print(f"  ✓ {len(encounter_objs)} encounters")

        # ── 6. Diagnoses ─────────────────────────────────────────────
        print("→ Seeding ~2,000 diagnoses...")
        dx_count = 0
        for enc in encounter_objs:
            n_dx = random.randint(1, 5)
            chosen = random.sample(ICD10_CODES, min(n_dx, len(ICD10_CODES)))
            for rank, (code, desc, chronic) in enumerate(chosen):
                dx_type = "Primary" if rank == 0 else "Secondary"
                dx = Diagnosis(
                    encounter_id=enc.id,
                    patient_id=enc.patient_id,
                    icd10_code=code,
                    icd10_desc=desc,
                    diagnosis_type=dx_type,
                    diagnosis_date=enc.admit_date.date() if enc.admit_date else None,
                    is_chronic=chronic,
                )
                db.add(dx)
                dx_count += 1
        await db.flush()
        print(f"  ✓ {dx_count} diagnoses")

        # ── 7. Procedures ─────────────────────────────────────────────
        print("→ Seeding ~1,200 procedures...")
        proc_count = 0
        for enc in random.sample(encounter_objs, min(900, len(encounter_objs))):
            n_proc = random.randint(1, 3)
            for cpt_code, cpt_desc, charge in random.sample(CPT_CODES, min(n_proc, len(CPT_CODES))):
                proc = Procedure(
                    encounter_id=enc.id,
                    patient_id=enc.patient_id,
                    cpt_code=cpt_code,
                    cpt_desc=cpt_desc,
                    procedure_date=enc.admit_date,
                    provider_id=enc.provider_id,
                    quantity=1,
                    charge_amount=Decimal(str(round(charge * random.uniform(0.8, 1.3), 2))),
                )
                db.add(proc)
                proc_count += 1
        await db.flush()
        print(f"  ✓ {proc_count} procedures")

        # ── 8. Medications ────────────────────────────────────────────
        print("→ Seeding ~800 medication records...")
        med_count = 0
        for enc in random.sample(encounter_objs, min(700, len(encounter_objs))):
            n_meds = random.randint(1, 4)
            for drug_name, rxnorm, route, dose, freq in random.sample(MEDICATIONS, min(n_meds, len(MEDICATIONS))):
                start = enc.admit_date.date() if enc.admit_date else date.today()
                end_date = start + timedelta(days=random.randint(5, 90)) if random.random() > 0.3 else None
                med = Medication(
                    encounter_id=enc.id,
                    patient_id=enc.patient_id,
                    drug_name=drug_name,
                    rxnorm_code=rxnorm,
                    dose=dose,
                    unit="mg",
                    route=route,
                    frequency=freq,
                    start_date=start,
                    end_date=end_date,
                    prescriber_id=enc.provider_id,
                    is_active=end_date is None or end_date > date.today(),
                )
                db.add(med)
                med_count += 1
        await db.flush()
        print(f"  ✓ {med_count} medications")

        # ── 9. Lab Results ────────────────────────────────────────────
        print("→ Seeding ~3,000 lab results...")
        lab_count = 0
        for enc in encounter_objs:
            n_labs = random.randint(1, 5)
            chosen_labs = random.sample(LOINC_LABS, min(n_labs, len(LOINC_LABS)))
            for loinc, name, unit, ref_low, ref_high, value_fn in chosen_labs:
                val = float(value_fn())
                flag = abnormal_flag(val, float(ref_low), float(ref_high))
                result_dt = enc.admit_date + timedelta(hours=random.randint(1, 12)) if enc.admit_date else datetime.now(timezone.utc)
                lab = LabResult(
                    encounter_id=enc.id,
                    patient_id=enc.patient_id,
                    loinc_code=loinc,
                    test_name=name,
                    result_value=str(val),
                    numeric_value=Decimal(str(round(val, 4))),
                    unit=unit,
                    reference_low=Decimal(str(ref_low)),
                    reference_high=Decimal(str(ref_high)),
                    abnormal_flag=flag,
                    result_date=result_dt,
                    ordering_prov=enc.provider_id,
                )
                db.add(lab)
                lab_count += 1
        await db.flush()
        print(f"  ✓ {lab_count} lab results")

        # ── 10. Vital Signs ───────────────────────────────────────────
        print("→ Seeding ~1,500 vital sign records...")
        vs_count = 0
        for enc in encounter_objs:
            n_vitals = random.randint(1, 3)
            for _ in range(n_vitals):
                recorded = enc.admit_date + timedelta(hours=random.randint(0, 8)) if enc.admit_date else datetime.now(timezone.utc)
                vs = VitalSign(
                    encounter_id=enc.id,
                    patient_id=enc.patient_id,
                    recorded_at=recorded,
                    systolic_bp=random.randint(90, 190),
                    diastolic_bp=random.randint(55, 115),
                    heart_rate=random.randint(48, 130),
                    respiratory_rate=random.randint(10, 28),
                    temperature_f=Decimal(str(round(random.uniform(96.5, 103.5), 1))),
                    spo2_pct=Decimal(str(round(random.uniform(88.0, 100.0), 1))),
                    weight_kg=Decimal(str(round(random.uniform(45.0, 140.0), 1))),
                    height_cm=Decimal(str(round(random.uniform(150.0, 200.0), 1))),
                )
                db.add(vs)
                vs_count += 1
        await db.flush()
        print(f"  ✓ {vs_count} vital signs")

        # ── 11. Claims ────────────────────────────────────────────────
        print("→ Seeding ~600 claims...")
        claim_count = 0
        for enc in random.sample(encounter_objs, min(600, len(encounter_objs))):
            billed = float(enc.total_charge or 5000)
            allowed = round(billed * random.uniform(0.6, 0.85), 2)
            paid = round(allowed * random.uniform(0.7, 1.0), 2)
            status = random.choices(["Paid","Denied","Pending"], weights=[70,15,15])[0]
            sub_date = enc.admit_date.date() + timedelta(days=random.randint(1, 7)) if enc.admit_date else date.today()
            cl = Claim(
                encounter_id=enc.id,
                patient_id=enc.patient_id,
                claim_type=random.choice(["Professional","Institutional"]),
                submission_date=sub_date,
                payer_name=random.choice(PAYERS),
                billed_amount=Decimal(str(round(billed, 2))),
                allowed_amount=Decimal(str(allowed)),
                paid_amount=Decimal(str(paid)) if status == "Paid" else Decimal("0.00"),
                denial_reason="Not medically necessary" if status == "Denied" else None,
                claim_status=status,
                adjudication_dt=sub_date + timedelta(days=random.randint(14, 60)) if status != "Pending" else None,
            )
            db.add(cl)
            claim_count += 1
        await db.flush()
        print(f"  ✓ {claim_count} claims")

        # ── 12. Readmissions ──────────────────────────────────────────
        print("→ Seeding ~120 readmission records...")
        readmit_count = 0
        inpatient_encs = [e for e in encounter_objs if e.encounter_type == "Inpatient"]
        patient_to_encs: dict = {}
        for enc in inpatient_encs:
            pid = enc.patient_id
            if pid not in patient_to_encs:
                patient_to_encs[pid] = []
            patient_to_encs[pid].append(enc)

        for pid, encs in patient_to_encs.items():
            if len(encs) < 2:
                continue
            sorted_encs = sorted(encs, key=lambda e: e.admit_date)
            for i in range(len(sorted_encs) - 1):
                index_enc = sorted_encs[i]
                next_enc = sorted_encs[i + 1]
                if index_enc.discharge_date is None:
                    continue
                days = (next_enc.admit_date - index_enc.discharge_date).days
                if 0 < days <= 30:
                    ra = Readmission(
                        index_encounter_id=index_enc.id,
                        readmit_encounter_id=next_enc.id,
                        patient_id=pid,
                        days_to_readmit=days,
                        readmit_reason=random.choice([
                            "Worsening heart failure symptoms",
                            "Uncontrolled diabetes",
                            "Wound infection",
                            "Pneumonia",
                            "Medication non-compliance",
                            "Sepsis",
                        ]),
                    )
                    db.add(ra)
                    readmit_count += 1
                    if readmit_count >= 150:
                        break
            if readmit_count >= 150:
                break
        await db.flush()
        print(f"  ✓ {readmit_count} readmissions")

        # ── 13. Users ─────────────────────────────────────────────────
        print("→ Seeding users...")
        users_data = [
            ("admin@healthcopilot.internal",  "admin",    "Admin",    "User",   "admin",    "Admin1234!"),
            ("analyst@healthcopilot.internal", "analyst",  "Data",     "Analyst","analyst",  "Analyst1234!"),
            ("clinician@healthcopilot.internal","clinician","Dr. Jane","Doe",    "clinician","Clinician1234!"),
        ]
        created_users = []
        for email, username, first, last, role, password in users_data:
            u = User(
                email=email,
                username=username,
                first_name=first,
                last_name=last,
                role=role,
                hashed_password=pwd_ctx.hash(password),
                is_active=True,
            )
            db.add(u)
            created_users.append((u, password))
        await db.flush()
        print(f"  ✓ {len(created_users)} users created")

        # ── Commit all ────────────────────────────────────────────────
        await db.commit()

    await engine.dispose()

    # ── Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Seed Complete!")
    print("=" * 60)
    print(f"\n  Facilities:  {len(FACILITIES)}")
    print(f"  Departments: {len(DEPARTMENTS)}")
    print(f"  Providers:   {len(PROVIDERS)}")
    print(f"  Patients:    500")
    print(f"  Encounters:  1,500")
    print(f"  Diagnoses:   ~{dx_count}")
    print(f"  Procedures:  ~{proc_count}")
    print(f"  Medications: ~{med_count}")
    print(f"  Lab Results: ~{lab_count}")
    print(f"  Vital Signs: ~{vs_count}")
    print(f"  Claims:      ~{claim_count}")
    print(f"  Readmissions:~{readmit_count}")
    print(f"\n  Users created:")
    for u, pw in created_users:
        print(f"    {u.role:12s}  {u.email}  (password: {pw})")
    print("\n  Now run: python -m uvicorn app.main:app --reload --port 8001\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Healthcare Copilot database")
    parser.add_argument("--drop-existing", action="store_true", help="Truncate all tables before seeding")
    args = parser.parse_args()
    asyncio.run(seed(drop_existing=args.drop_existing))
