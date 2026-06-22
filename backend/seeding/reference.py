"""
Clinical reference data and realistic distributions for synthetic generation.
=============================================================================
Everything here is real-world coded healthcare reference data (ICD-10, LOINC,
RxNorm, CPT, DRG, US payers) plus epidemiologically-plausible distributions so
the generated dataset behaves like real analytics data — not placeholder noise.

No PHI: all names/IDs are randomly synthesized at generation time.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta, timezone

# ── Demographics (roughly US-representative weights) ──────────────────────────

GENDERS = ["Male", "Female", "Non-binary", "Unknown"]
GENDER_WEIGHTS = [0.487, 0.495, 0.012, 0.006]

RACES = [
    "White",
    "Black or African American",
    "Asian",
    "American Indian or Alaska Native",
    "Native Hawaiian or Other Pacific Islander",
    "Other",
    "Unknown",
]
RACE_WEIGHTS = [0.601, 0.134, 0.059, 0.013, 0.003, 0.15, 0.04]
ETHNICITIES = ["Hispanic or Latino", "Non-Hispanic", "Unknown"]
ETHNICITY_WEIGHTS = [0.185, 0.78, 0.035]

# Age bands (years) with utilization-weighted probabilities. Healthcare contact
# skews older, so the elderly are over-represented relative to the population.
AGE_BANDS = [(0, 17), (18, 34), (35, 49), (50, 64), (65, 79), (80, 100)]
AGE_BAND_WEIGHTS = [0.10, 0.15, 0.16, 0.22, 0.24, 0.13]

# State population weights (top states carry most of the mass; remainder spread).
STATE_POP = {
    "CA": 39.0,
    "TX": 30.0,
    "FL": 22.6,
    "NY": 19.7,
    "PA": 13.0,
    "IL": 12.6,
    "OH": 11.8,
    "GA": 11.0,
    "NC": 10.7,
    "MI": 10.0,
    "NJ": 9.3,
    "VA": 8.7,
    "WA": 7.8,
    "AZ": 7.4,
    "MA": 7.0,
    "TN": 7.1,
    "IN": 6.8,
    "MD": 6.2,
    "MO": 6.2,
    "WI": 5.9,
    "CO": 5.8,
    "MN": 5.7,
    "SC": 5.3,
    "AL": 5.1,
    "LA": 4.6,
    "KY": 4.5,
    "OR": 4.2,
    "OK": 4.0,
    "CT": 3.6,
    "UT": 3.4,
    "NV": 3.2,
    "AR": 3.0,
    "MS": 2.9,
    "KS": 2.9,
    "NM": 2.1,
    "NE": 2.0,
    "ID": 1.9,
    "WV": 1.8,
    "HI": 1.4,
    "ME": 1.4,
    "MT": 1.1,
    "RI": 1.1,
    "DE": 1.0,
    "SD": 0.9,
    "ND": 0.8,
    "AK": 0.7,
    "VT": 0.6,
    "WY": 0.6,
}
_STATES = list(STATE_POP.keys())
_STATE_WEIGHTS = list(STATE_POP.values())

PAYERS = [
    "Medicare",
    "Medicaid",
    "Blue Cross Blue Shield",
    "UnitedHealthcare",
    "Aetna",
    "Cigna",
    "Humana",
    "Kaiser Permanente",
    "Anthem",
    "Self-Pay",
]
PAYER_WEIGHTS = [0.21, 0.19, 0.14, 0.12, 0.08, 0.07, 0.06, 0.05, 0.05, 0.03]

# ── Facilities & departments ──────────────────────────────────────────────────

FACILITY_TYPES = ["Hospital", "Clinic", "Lab", "Urgent Care", "Surgery Center"]
FACILITY_TYPE_WEIGHTS = [0.35, 0.34, 0.12, 0.12, 0.07]
HOSPITAL_SUFFIXES = [
    "General Hospital",
    "Medical Center",
    "Regional Health",
    "Memorial Hospital",
    "Community Hospital",
    "University Medical Center",
    "Health System",
    "Specialty Clinic",
    "Family Care",
    "Diagnostics",
]

DEPARTMENTS = [
    ("Emergency Department", "ED"),
    ("Cardiology", "Inpatient"),
    ("Internal Medicine", "Inpatient"),
    ("Orthopedics", "Outpatient"),
    ("Oncology", "Inpatient"),
    ("Neurology", "Outpatient"),
    ("Pulmonology", "Inpatient"),
    ("Endocrinology", "Outpatient"),
    ("Gastroenterology", "Outpatient"),
    ("Nephrology", "Inpatient"),
    ("Radiology", "Outpatient"),
    ("Laboratory", "Outpatient"),
    ("ICU", "ICU"),
    ("Pediatrics", "Inpatient"),
    ("Obstetrics", "Inpatient"),
    ("Family Medicine", "Outpatient"),
    ("Surgery", "Inpatient"),
    ("Behavioral Health", "Outpatient"),
]

# ── Providers ─────────────────────────────────────────────────────────────────

PHYSICIAN_SPECIALTIES = [
    "Cardiology",
    "Emergency Medicine",
    "Internal Medicine",
    "Orthopedic Surgery",
    "Oncology",
    "Neurology",
    "Pulmonology",
    "Endocrinology",
    "Gastroenterology",
    "Nephrology",
    "Radiology",
    "Pediatrics",
    "Obstetrics & Gynecology",
    "Family Medicine",
    "Hospitalist",
    "Critical Care",
    "Anesthesiology",
    "Psychiatry",
    "General Surgery",
    "Dermatology",
]
NURSE_SPECIALTIES = [
    "Registered Nurse",
    "ICU Nurse",
    "ED Nurse",
    "Nurse Practitioner",
    "Charge Nurse",
    "OR Nurse",
    "Oncology Nurse",
    "Pediatric Nurse",
    "Labor & Delivery Nurse",
    "Telemetry Nurse",
    "Case Manager",
    "Nurse Anesthetist",
    "Clinical Nurse Specialist",
]

# ── ICD-10 diagnoses: (code, description, is_chronic, base_weight, min_age) ─────
# base_weight ~ relative prevalence; min_age gates pediatric-implausible dx.
ICD10 = [
    ("I10", "Essential (primary) hypertension", True, 14.0, 25),
    ("E11.9", "Type 2 diabetes mellitus without complications", True, 9.0, 30),
    ("E11.65", "Type 2 diabetes mellitus with hyperglycemia", True, 3.0, 30),
    ("E78.5", "Hyperlipidemia, unspecified", True, 11.0, 30),
    (
        "I25.10",
        "Atherosclerotic heart disease of native coronary artery",
        True,
        6.0,
        45,
    ),
    ("I50.9", "Heart failure, unspecified", True, 4.0, 50),
    ("N18.3", "Chronic kidney disease, stage 3", True, 3.5, 50),
    ("J44.1", "COPD with acute exacerbation", True, 3.0, 45),
    ("J45.909", "Unspecified asthma, uncomplicated", True, 4.0, 0),
    ("F32.1", "Major depressive disorder, single episode, moderate", True, 4.0, 14),
    ("F41.1", "Generalized anxiety disorder", True, 4.5, 14),
    ("M54.5", "Low back pain", False, 7.0, 18),
    ("M17.11", "Unilateral primary osteoarthritis, right knee", True, 3.0, 45),
    ("J18.9", "Pneumonia, unspecified organism", False, 3.5, 0),
    ("N39.0", "Urinary tract infection, site not specified", False, 4.5, 0),
    ("R07.9", "Chest pain, unspecified", False, 4.0, 18),
    ("R05.9", "Cough, unspecified", False, 3.5, 0),
    ("I21.9", "Acute myocardial infarction, unspecified", False, 1.8, 40),
    ("I63.9", "Cerebral infarction, unspecified", False, 1.6, 50),
    ("A41.9", "Sepsis, unspecified organism", False, 1.5, 18),
    ("E66.9", "Obesity, unspecified", True, 8.0, 12),
    ("Z79.4", "Long term (current) use of insulin", True, 2.5, 25),
    ("K21.9", "Gastro-esophageal reflux disease without esophagitis", True, 5.0, 18),
    ("G47.33", "Obstructive sleep apnea", True, 3.0, 25),
    ("C50.911", "Malignant neoplasm of breast, unspecified, female", True, 1.2, 35),
    (
        "C34.90",
        "Malignant neoplasm of unspecified part of bronchus or lung",
        True,
        1.0,
        45,
    ),
    (
        "S52.501A",
        "Unspecified fracture of lower end of right radius, initial",
        False,
        1.5,
        0,
    ),
    ("R51.9", "Headache, unspecified", False, 3.0, 5),
    ("Z00.00", "Encounter for general adult medical examination", False, 6.0, 18),
    ("Z23", "Encounter for immunization", False, 4.0, 0),
]

# Conditions that should be tagged on the patient for cross-table correlation.
DIABETES_CODES = {"E11.9", "E11.65", "Z79.4"}
HYPERTENSION_CODES = {"I10"}
HEART_CODES = {"I25.10", "I50.9", "I21.9"}

# ── LOINC labs: (code, name, unit, ref_low, ref_high, mean, sd) ─────────────────
LOINC_LABS = [
    ("2345-7", "Glucose [Mass/volume] in Serum or Plasma", "mg/dL", 70, 99, 105, 30),
    ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", "%", 4.0, 5.6, 5.9, 1.3),
    (
        "2160-0",
        "Creatinine [Mass/volume] in Serum or Plasma",
        "mg/dL",
        0.6,
        1.2,
        1.05,
        0.35,
    ),
    (
        "2823-3",
        "Potassium [Moles/volume] in Serum or Plasma",
        "mEq/L",
        3.5,
        5.0,
        4.1,
        0.4,
    ),
    ("2951-2", "Sodium [Moles/volume] in Serum or Plasma", "mEq/L", 136, 145, 139, 3),
    ("718-7", "Hemoglobin [Mass/volume] in Blood", "g/dL", 12.0, 17.5, 13.6, 1.9),
    ("6690-2", "Leukocytes [#/volume] in Blood", "10*3/uL", 4.5, 11.0, 7.5, 2.4),
    ("13457-7", "Cholesterol in LDL [Mass/volume] (calc)", "mg/dL", 0, 100, 112, 33),
    (
        "2093-3",
        "Cholesterol [Mass/volume] in Serum or Plasma",
        "mg/dL",
        0,
        200,
        193,
        42,
    ),
    (
        "1742-6",
        "Alanine aminotransferase [Enzymatic activity/volume]",
        "U/L",
        7,
        56,
        33,
        18,
    ),
    (
        "6768-6",
        "Alkaline phosphatase [Enzymatic activity/volume]",
        "U/L",
        44,
        147,
        95,
        28,
    ),
    ("14959-1", "Microalbumin [Mass/volume] in Urine", "mg/L", 0, 30, 22, 14),
    (
        "30522-7",
        "C reactive protein [Mass/volume] in Serum or Plasma",
        "mg/L",
        0,
        10,
        7,
        6,
    ),
    ("2085-9", "Cholesterol in HDL [Mass/volume]", "mg/dL", 40, 60, 52, 14),
    ("33914-3", "Glomerular filtration rate (eGFR)", "mL/min", 60, 120, 78, 22),
]

# ── Medications: (drug, ndc, rxnorm, dose, unit, route, frequency) ──────────────
MEDICATIONS = [
    ("Metformin", "00093-1048", "860975", "500", "mg", "PO", "Twice daily"),
    ("Lisinopril", "00071-0222", "314076", "10", "mg", "PO", "Once daily"),
    ("Atorvastatin", "00071-0155", "617311", "40", "mg", "PO", "Once at bedtime"),
    ("Amlodipine", "00069-1530", "197361", "5", "mg", "PO", "Once daily"),
    ("Omeprazole", "00186-0740", "40790", "20", "mg", "PO", "Once daily"),
    ("Aspirin", "00904-2013", "1191", "81", "mg", "PO", "Once daily"),
    ("Furosemide", "00054-4297", "4603", "40", "mg", "PO", "Once daily"),
    ("Levothyroxine", "00074-4341", "10582", "50", "mcg", "PO", "Once daily"),
    (
        "Insulin Glargine",
        "00088-2220",
        "274783",
        "20",
        "units",
        "SC",
        "Once at bedtime",
    ),
    ("Albuterol", "00173-0682", "435", "90", "mcg", "INH", "Every 4-6 hours PRN"),
    ("Sertraline", "00049-4960", "36437", "50", "mg", "PO", "Once daily"),
    ("Gabapentin", "00071-0803", "194044", "300", "mg", "PO", "Three times daily"),
    ("Hydrochlorothiazide", "00143-1232", "5487", "25", "mg", "PO", "Once daily"),
    ("Montelukast", "00006-0117", "88249", "10", "mg", "PO", "Once daily"),
    ("Pantoprazole", "00008-0841", "40790", "40", "mg", "IV", "Twice daily"),
    ("Ceftriaxone", "00004-1964", "25033", "1", "g", "IV", "Once daily"),
    ("Vancomycin", "00409-6533", "11124", "1000", "mg", "IV", "Every 12 hours"),
    ("Heparin", "00641-0392", "5224", "5000", "units", "SC", "Every 8 hours"),
    ("Ondansetron", "00078-0467", "312086", "4", "mg", "IV", "Every 6 hours PRN"),
    ("Warfarin", "00056-0172", "11289", "5", "mg", "PO", "Once daily"),
]
# Map a correlated condition to preferred drug indices in MEDICATIONS.
COND_DRUGS = {
    "diabetes": [0, 8],  # Metformin, Insulin Glargine
    "hypertension": [1, 3, 12],  # Lisinopril, Amlodipine, HCTZ
    "heart": [1, 3, 5, 6, 19],  # Lisinopril, Amlodipine, Aspirin, Furosemide, Warfarin
    "lipids": [2],  # Atorvastatin
}

# ── CPT procedures: (code, description, base_charge) ────────────────────────────
CPT = [
    ("99213", "Office/outpatient visit, established, low complexity", 150.0),
    ("99214", "Office/outpatient visit, established, moderate complexity", 220.0),
    ("99223", "Initial hospital care, high severity", 450.0),
    ("99232", "Subsequent hospital care, moderate severity", 175.0),
    ("99291", "Critical care, first 30-74 minutes", 550.0),
    ("71046", "Radiologic exam, chest, 2 views", 95.0),
    ("93000", "Electrocardiogram, routine ECG", 65.0),
    ("80053", "Comprehensive metabolic panel", 40.0),
    ("85025", "Complete blood count (CBC), automated", 25.0),
    ("36415", "Collection of venous blood by venipuncture", 15.0),
    ("27447", "Total knee arthroplasty", 12000.0),
    ("43239", "Esophagogastroduodenoscopy with biopsy", 1200.0),
    ("45378", "Colonoscopy, flexible", 900.0),
    ("93306", "Echocardiography, transthoracic", 800.0),
    ("70553", "MRI brain without and with contrast", 2200.0),
]

# ── DRG (inpatient): (code, description) ────────────────────────────────────────
DRG = [
    ("470", "Major hip/knee joint replacement w/o MCC"),
    ("291", "Heart failure and shock w MCC"),
    ("292", "Heart failure and shock w CC"),
    ("194", "Simple pneumonia and pleurisy w CC"),
    ("690", "Kidney and urinary tract infections w/o MCC"),
    ("064", "Intracranial hemorrhage or cerebral infarction w MCC"),
    ("280", "Acute myocardial infarction, discharged alive w MCC"),
    ("871", "Septicemia w/o MV >96 hours w MCC"),
    ("392", "Esophagitis, gastroent & misc digestive disorders w/o MCC"),
    ("247", "Percutaneous cardiovascular procedures w drug-eluting stent"),
]

ENCOUNTER_TYPES = ["Outpatient", "ED", "Inpatient", "Telehealth"]
ENCOUNTER_TYPE_WEIGHTS = [0.55, 0.20, 0.15, 0.10]
DISCHARGE_DISPS = [
    "Home",
    "Home with Services",
    "SNF",
    "Rehabilitation",
    "Transfer",
    "AMA",
    "Expired",
]
DISCHARGE_DISP_WEIGHTS = [0.62, 0.14, 0.10, 0.06, 0.04, 0.02, 0.02]
CLAIM_STATUSES = ["Paid", "Denied", "Pending"]
CLAIM_STATUS_WEIGHTS = [0.72, 0.16, 0.12]
DENIAL_REASONS = [
    "Not medically necessary",
    "Prior authorization required",
    "Out of network",
    "Duplicate claim",
    "Coding error",
    "Coverage lapsed",
]
READMIT_REASONS = [
    "Worsening heart failure symptoms",
    "Uncontrolled diabetes",
    "Surgical site infection",
    "Pneumonia",
    "Medication non-compliance",
    "Sepsis",
    "Acute kidney injury",
    "COPD exacerbation",
]

UTC = timezone.utc


def random_state() -> str:
    return random.choices(_STATES, weights=_STATE_WEIGHTS, k=1)[0]


def random_age() -> int:
    lo, hi = random.choices(AGE_BANDS, weights=AGE_BAND_WEIGHTS, k=1)[0]
    return random.randint(lo, hi)


def dob_for_age(age: int, ref: date) -> date:
    start = ref.replace(year=ref.year - age - 1)
    return start + timedelta(days=random.randint(0, 364))


def abnormal_flag(value: float, low: float, high: float) -> str:
    if value < low * 0.8:
        return "LL"
    if value < low:
        return "L"
    if value > high * 1.2:
        return "HH"
    if value > high:
        return "H"
    return "N"
