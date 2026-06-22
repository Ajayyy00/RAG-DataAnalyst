"""
Synthetic healthcare data generation pipeline.
==============================================
Streaming, memory-bounded generation: encounters are produced in chunks and
their child records (diagnoses, labs, meds, procedures, vitals, claims) are
generated and COPY-loaded alongside each chunk, so peak memory stays flat no
matter the scale (100K → 5M rows).

Realism highlights:
  * Age-/prevalence-weighted ICD-10 diagnoses (older patients accrue chronic dx).
  * Cross-table correlation: diabetic encounters → elevated glucose/HbA1c labs
    and metformin/insulin orders; hypertensive/cardiac → matching drug classes.
  * Encounter-type intensity: inpatient/ED encounters carry far more labs,
    diagnoses, procedures and vitals than telehealth/outpatient.
  * 30-day readmissions derived in-database from the encounter timeline.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import asyncpg
import numpy as np
from faker import Faker

from seeding import reference as R
from seeding.bulk import copy_chunks
from seeding.scales import Scale

fake = Faker("en_US")

CHUNK = 20_000  # encounters per streaming chunk

# Per-encounter-type intensity weights for each child table.
_TYPE_IDX = {t: i for i, t in enumerate(R.ENCOUNTER_TYPES)}
DX_W = [1.0, 2.5, 4.0, 0.5]  # Outpatient, ED, Inpatient, Telehealth
LAB_W = [1.0, 3.0, 5.0, 0.2]
MED_W = [1.2, 1.5, 3.0, 0.6]
PROC_W = [1.0, 2.0, 3.0, 0.1]
VS_W = [1.0, 4.0, 6.0, 0.2]
CLAIM_W = [1.2, 3.0, 4.0, 0.3]

# Pre-split ICD pools for age gating + precomputed weights.
_ICD_ALL = R.ICD10
_ICD_ALL_W = [c[3] for c in _ICD_ALL]
_ICD_PED = [c for c in R.ICD10 if c[4] <= 12]
_ICD_PED_W = [c[3] for c in _ICD_PED]


# ── Column definitions (COPY order) ───────────────────────────────────────────
COLS = {
    "facilities": ("id", "name", "city", "state", "facility_type"),
    "departments": ("id", "name", "dept_type", "facility_id"),
    "providers": (
        "id",
        "npi",
        "first_name",
        "last_name",
        "provider_type",
        "specialty",
        "is_active",
        "department_id",
    ),
    "patients": (
        "id",
        "mrn",
        "first_name",
        "last_name",
        "date_of_birth",
        "gender",
        "race",
        "ethnicity",
        "zip_code",
        "insurance_type",
        "is_active",
    ),
    "encounters": (
        "id",
        "patient_id",
        "provider_id",
        "department_id",
        "encounter_type",
        "admit_date",
        "discharge_date",
        "discharge_disp",
        "drg_code",
        "drg_description",
        "total_charge",
        "total_payment",
    ),
    "diagnoses": (
        "id",
        "encounter_id",
        "patient_id",
        "icd10_code",
        "icd10_desc",
        "diagnosis_type",
        "diagnosis_date",
        "is_chronic",
    ),
    "medications": (
        "id",
        "encounter_id",
        "patient_id",
        "drug_name",
        "ndc_code",
        "rxnorm_code",
        "dose",
        "unit",
        "route",
        "frequency",
        "start_date",
        "end_date",
        "prescriber_id",
        "is_active",
    ),
    "lab_results": (
        "id",
        "encounter_id",
        "patient_id",
        "loinc_code",
        "test_name",
        "result_value",
        "numeric_value",
        "unit",
        "reference_low",
        "reference_high",
        "abnormal_flag",
        "result_date",
        "ordering_prov",
    ),
    "procedures": (
        "id",
        "encounter_id",
        "patient_id",
        "cpt_code",
        "cpt_desc",
        "procedure_date",
        "provider_id",
        "quantity",
        "charge_amount",
    ),
    "vital_signs": (
        "id",
        "encounter_id",
        "patient_id",
        "recorded_at",
        "systolic_bp",
        "diastolic_bp",
        "heart_rate",
        "respiratory_rate",
        "temperature_f",
        "spo2_pct",
        "weight_kg",
        "height_cm",
    ),
    "claims": (
        "id",
        "encounter_id",
        "patient_id",
        "claim_type",
        "submission_date",
        "payer_name",
        "billed_amount",
        "allowed_amount",
        "paid_amount",
        "denial_reason",
        "claim_status",
        "adjudication_dt",
    ),
}

WINDOW_DAYS = 365 * 3  # encounters span ~3 years


def _now() -> datetime:
    return datetime.now(tz=R.UTC)


def _dec(x: float, q: str = "0.01") -> Decimal:
    return Decimal(str(round(float(x), len(q.split(".")[1]) if "." in q else 0)))


def _lambdas(target: int, total_enc: int, type_w: list[float]) -> list[float]:
    """Per-encounter-type Poisson rate so the expected total ≈ target while
    concentrating rows on high-intensity encounter types."""
    if total_enc == 0:
        return [0.0] * len(type_w)
    sumw_p = sum(p * w for p, w in zip(R.ENCOUNTER_TYPE_WEIGHTS, type_w))
    return [target * w / (total_enc * sumw_p) for w in type_w]


# ── Reference layer: facilities, departments, providers ───────────────────────


async def seed_facilities(conn: asyncpg.Connection, scale: Scale) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []

    def gen():
        chunk = []
        for _ in range(scale.facilities):
            fid = uuid.uuid4()
            ids.append(fid)
            ftype = random.choices(R.FACILITY_TYPES, weights=R.FACILITY_TYPE_WEIGHTS)[0]
            name = f"{fake.city()} {random.choice(R.HOSPITAL_SUFFIXES)}"
            chunk.append((fid, name[:200], fake.city()[:100], R.random_state(), ftype))
        yield chunk

    await copy_chunks(conn, "facilities", COLS["facilities"], gen(), label="facilities")
    return ids


async def seed_departments(
    conn: asyncpg.Connection, facility_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    ids: list[uuid.UUID] = []

    def gen():
        chunk = []
        for fid in facility_ids:
            picks = random.sample(
                R.DEPARTMENTS, k=random.randint(4, min(12, len(R.DEPARTMENTS)))
            )
            for name, dtype in picks:
                did = uuid.uuid4()
                ids.append(did)
                chunk.append((did, name, dtype, fid))
        yield chunk

    await copy_chunks(
        conn, "departments", COLS["departments"], gen(), label="departments"
    )
    return ids


async def seed_providers(
    conn: asyncpg.Connection, scale: Scale, dept_ids: list[uuid.UUID]
) -> list[uuid.UUID]:
    """Returns physician ids (used for clinical attribution)."""
    physician_ids: list[uuid.UUID] = []
    used_npi: set[str] = set()

    def npi() -> str:
        while True:
            n = str(random.randint(1_000_000_000, 9_999_999_999))
            if n not in used_npi:
                used_npi.add(n)
                return n

    def gen():
        chunk = []
        for kind, count, specs in (
            ("physician", scale.physicians, R.PHYSICIAN_SPECIALTIES),
            ("nurse", scale.nurses, R.NURSE_SPECIALTIES),
        ):
            for _ in range(count):
                pid = uuid.uuid4()
                if kind == "physician":
                    physician_ids.append(pid)
                chunk.append(
                    (
                        pid,
                        npi(),
                        fake.first_name()[:100],
                        fake.last_name()[:100],
                        kind,
                        random.choice(specs),
                        random.random() > 0.05,
                        random.choice(dept_ids),
                    )
                )
                if len(chunk) >= 50_000:
                    yield chunk
                    chunk = []
        yield chunk

    await copy_chunks(conn, "providers", COLS["providers"], gen(), label="providers")
    return physician_ids


# ── Patients ──────────────────────────────────────────────────────────────────


async def seed_patients(
    conn: asyncpg.Connection, scale: Scale
) -> tuple[list[uuid.UUID], np.ndarray]:
    """Returns (patient_ids, birth_year array) for downstream age correlation."""
    ids: list[uuid.UUID] = []
    birth_years = np.empty(scale.patients, dtype=np.int16)
    ref = date.today()
    seq = 100_001

    def gen():
        nonlocal seq
        chunk = []
        for i in range(scale.patients):
            pid = uuid.uuid4()
            ids.append(pid)
            age = R.random_age()
            birth_years[i] = ref.year - age
            dob = R.dob_for_age(age, ref)
            gender = random.choices(R.GENDERS, weights=R.GENDER_WEIGHTS)[0]
            first = (
                fake.first_name_female()
                if gender == "Female"
                else (fake.first_name_male() if gender == "Male" else fake.first_name())
            )
            # Medicare skews to 65+; otherwise weighted payer mix.
            payer = (
                "Medicare"
                if age >= 65 and random.random() < 0.8
                else random.choices(R.PAYERS, weights=R.PAYER_WEIGHTS)[0]
            )
            chunk.append(
                (
                    pid,
                    f"MRN{seq:08d}",
                    first[:100],
                    fake.last_name()[:100],
                    dob,
                    gender,
                    random.choices(R.RACES, weights=R.RACE_WEIGHTS)[0],
                    random.choices(R.ETHNICITIES, weights=R.ETHNICITY_WEIGHTS)[0],
                    f"{random.randint(1, 99999):05d}",
                    payer,
                    random.random() > 0.03,
                )
            )
            seq += 1
            if len(chunk) >= 50_000:
                yield chunk
                chunk = []
        yield chunk

    await copy_chunks(conn, "patients", COLS["patients"], gen(), label="patients")
    return ids, birth_years


# ── Child-record builders (per encounter) ─────────────────────────────────────


def _gen_diagnoses(enc_id, pid, admit_d, age, n, out) -> set[str]:
    """Append n diagnosis rows; return set of correlated condition tags."""
    conds: set[str] = set()
    if n <= 0:
        return conds
    pool, weights = (_ICD_PED, _ICD_PED_W) if age < 13 else (_ICD_ALL, _ICD_ALL_W)
    picks = random.choices(pool, weights=weights, k=n)
    for rank, (code, desc, chronic, _w, _ma) in enumerate(picks):
        out.append(
            (
                uuid.uuid4(),
                enc_id,
                pid,
                code,
                desc,
                "Primary" if rank == 0 else "Secondary",
                admit_d,
                chronic,
            )
        )
        if code in R.DIABETES_CODES:
            conds.add("diabetes")
        if code in R.HYPERTENSION_CODES:
            conds.add("hypertension")
        if code in R.HEART_CODES:
            conds.add("heart")
        if code == "E78.5":
            conds.add("lipids")
    return conds


def _gen_labs(enc_id, pid, admit_dt, prov_id, n, conds, out) -> None:
    if n <= 0:
        return
    diabetic = "diabetes" in conds
    for code, name, unit, lo, hi, mean, sd in random.choices(R.LOINC_LABS, k=n):
        m, s = mean, sd
        if diabetic and code == "2345-7":  # glucose
            m, s = 165, 55
        elif diabetic and code == "4548-4":  # HbA1c
            m, s = 8.1, 1.8
        val = max(0.0, random.gauss(m, s))
        val = round(val, 1 if hi < 100 else 0)
        out.append(
            (
                uuid.uuid4(),
                enc_id,
                pid,
                code,
                name,
                str(val),
                _dec(val, "0.0001"),
                unit,
                _dec(lo, "0.0001"),
                _dec(hi, "0.0001"),
                R.abnormal_flag(val, lo, hi),
                admit_dt + timedelta(hours=random.randint(1, 14)),
                prov_id,
            )
        )


def _gen_meds(enc_id, pid, admit_d, prov_id, n, conds, out) -> None:
    if n <= 0:
        return
    for _ in range(n):
        idx = None
        for cond in conds:
            if cond in R.COND_DRUGS and random.random() < 0.7:
                idx = random.choice(R.COND_DRUGS[cond])
                break
        if idx is None:
            idx = random.randrange(len(R.MEDICATIONS))
        drug, ndc, rx, dose, unit, route, freq = R.MEDICATIONS[idx]
        end = (
            admit_d + timedelta(days=random.randint(7, 180))
            if random.random() > 0.35
            else None
        )
        out.append(
            (
                uuid.uuid4(),
                enc_id,
                pid,
                drug,
                ndc,
                rx,
                dose,
                unit,
                route,
                freq,
                admit_d,
                end,
                prov_id,
                end is None or end > date.today(),
            )
        )


def _gen_procedures(enc_id, pid, admit_dt, prov_id, n, out) -> None:
    for _ in range(n):
        code, desc, charge = random.choice(R.CPT)
        out.append(
            (
                uuid.uuid4(),
                enc_id,
                pid,
                code,
                desc,
                admit_dt,
                prov_id,
                1,
                _dec(charge * random.uniform(0.8, 1.3)),
            )
        )


def _gen_vitals(enc_id, pid, admit_dt, n, out) -> None:
    for _ in range(n):
        out.append(
            (
                uuid.uuid4(),
                enc_id,
                pid,
                admit_dt + timedelta(hours=random.randint(0, 10)),
                random.randint(95, 185),
                random.randint(55, 110),
                random.randint(48, 125),
                random.randint(11, 26),
                _dec(random.uniform(96.5, 102.5), "0.01"),
                _dec(random.uniform(89, 100), "0.01"),
                _dec(random.uniform(45, 140), "0.01"),
                _dec(random.uniform(150, 200), "0.01"),
            )
        )


def _gen_claim(enc_id, pid, admit_d, charge, out) -> None:
    billed = float(charge or 5000)
    allowed = round(billed * random.uniform(0.55, 0.85), 2)
    status = random.choices(R.CLAIM_STATUSES, weights=R.CLAIM_STATUS_WEIGHTS)[0]
    paid = round(allowed * random.uniform(0.75, 1.0), 2) if status == "Paid" else 0.0
    sub = admit_d + timedelta(days=random.randint(1, 10))
    out.append(
        (
            uuid.uuid4(),
            enc_id,
            pid,
            random.choice(["Professional", "Institutional"]),
            sub,
            random.choices(R.PAYERS, weights=R.PAYER_WEIGHTS)[0],
            _dec(billed),
            _dec(allowed),
            _dec(paid),
            random.choice(R.DENIAL_REASONS) if status == "Denied" else None,
            status,
            (
                sub + timedelta(days=random.randint(14, 60))
                if status != "Pending"
                else None
            ),
        )
    )


# ── Encounters + streaming children ───────────────────────────────────────────


async def seed_encounters(
    conn: asyncpg.Connection,
    scale: Scale,
    patient_ids: list[uuid.UUID],
    birth_years: np.ndarray,
    physician_ids: list[uuid.UUID],
    dept_ids: list[uuid.UUID],
) -> dict[str, int]:
    """Generate encounters and all child tables in memory-bounded chunks."""
    total = scale.encounters
    lam = {
        "diagnoses": _lambdas(scale.diagnoses, total, DX_W),
        "lab_results": _lambdas(scale.lab_results, total, LAB_W),
        "medications": _lambdas(scale.medications, total, MED_W),
        "procedures": _lambdas(scale.procedures, total, PROC_W),
        "vital_signs": _lambdas(scale.vital_signs, total, VS_W),
        "claims": [min(0.98, x) for x in _lambdas(scale.claims, total, CLAIM_W)],
    }
    counts = {
        k: 0
        for k in (
            "encounters",
            "diagnoses",
            "lab_results",
            "medications",
            "procedures",
            "vital_signs",
            "claims",
        )
    }
    n_pat = len(patient_ids)
    now = _now()
    cur_year = now.year

    print(f"  Generating {total:,} encounters + children (chunk={CHUNK:,})...")
    done = 0
    while done < total:
        this = min(CHUNK, total - done)
        enc_rows: list[tuple] = []
        dx_rows: list[tuple] = []
        lab_rows: list[tuple] = []
        med_rows: list[tuple] = []
        proc_rows: list[tuple] = []
        vs_rows: list[tuple] = []
        claim_rows: list[tuple] = []

        # Vectorized draws for the chunk.
        types = random.choices(
            R.ENCOUNTER_TYPES, weights=R.ENCOUNTER_TYPE_WEIGHTS, k=this
        )
        pidx = np.random.randint(0, n_pat, size=this)
        offsets = (np.random.beta(1.3, 2.0, size=this) * WINDOW_DAYS).astype(int)
        tcodes = np.array([_TYPE_IDX[t] for t in types])
        c_dx = np.random.poisson([lam["diagnoses"][c] for c in tcodes])
        c_lab = np.random.poisson([lam["lab_results"][c] for c in tcodes])
        c_med = np.random.poisson([lam["medications"][c] for c in tcodes])
        c_proc = np.random.poisson([lam["procedures"][c] for c in tcodes])
        c_vs = np.random.poisson([lam["vital_signs"][c] for c in tcodes])
        c_claim = np.random.random(this) < np.array([lam["claims"][c] for c in tcodes])

        for i in range(this):
            etype = types[i]
            p_i = int(pidx[i])
            pid = patient_ids[p_i]
            age = max(0, cur_year - int(birth_years[p_i]))
            admit = now - timedelta(
                days=int(offsets[i]), seconds=random.randint(0, 86399)
            )
            admit_d = admit.date()
            prov = random.choice(physician_ids)
            dept = random.choice(dept_ids)

            if etype == "Inpatient":
                los = random.randint(1, 14)
                discharge = admit + timedelta(days=los)
                drg = random.choice(R.DRG)
                charge = round(random.uniform(9_000, 90_000), 2)
                disp = random.choices(
                    R.DISCHARGE_DISPS, weights=R.DISCHARGE_DISP_WEIGHTS
                )[0]
            elif etype == "ED":
                discharge = admit + timedelta(hours=random.randint(2, 24))
                drg = None
                charge = round(random.uniform(1_200, 14_000), 2)
                disp = random.choices(
                    R.DISCHARGE_DISPS, weights=R.DISCHARGE_DISP_WEIGHTS
                )[0]
            else:
                discharge = admit + timedelta(hours=random.randint(1, 4))
                drg = None
                charge = round(random.uniform(120, 3_800), 2)
                disp = "Home"

            enc_id = uuid.uuid4()
            payment = round(charge * random.uniform(0.55, 0.92), 2)
            enc_rows.append(
                (
                    enc_id,
                    pid,
                    prov,
                    dept,
                    etype,
                    admit,
                    discharge if random.random() > 0.04 else None,
                    disp,
                    drg[0] if drg else None,
                    drg[1] if drg else None,
                    _dec(charge),
                    _dec(payment),
                )
            )

            conds = _gen_diagnoses(enc_id, pid, admit_d, age, int(c_dx[i]), dx_rows)
            _gen_labs(enc_id, pid, admit, prov, int(c_lab[i]), conds, lab_rows)
            _gen_meds(enc_id, pid, admit_d, prov, int(c_med[i]), conds, med_rows)
            _gen_procedures(enc_id, pid, admit, prov, int(c_proc[i]), proc_rows)
            _gen_vitals(enc_id, pid, admit, int(c_vs[i]), vs_rows)
            if bool(c_claim[i]):
                _gen_claim(enc_id, pid, admit_d, charge, claim_rows)

        # COPY this chunk's tables (parents first for FK integrity).
        await conn.copy_records_to_table(
            "encounters", records=enc_rows, columns=list(COLS["encounters"])
        )
        for tbl, rows in (
            ("diagnoses", dx_rows),
            ("lab_results", lab_rows),
            ("medications", med_rows),
            ("procedures", proc_rows),
            ("vital_signs", vs_rows),
            ("claims", claim_rows),
        ):
            if rows:
                await conn.copy_records_to_table(
                    tbl, records=rows, columns=list(COLS[tbl])
                )
            counts[tbl] += len(rows)

        counts["encounters"] += len(enc_rows)
        done += this
        print(
            f"  encounters {done:>12,}/{total:,}  "
            f"(dx {counts['diagnoses']:,} · labs {counts['lab_results']:,} · "
            f"rx {counts['medications']:,} · claims {counts['claims']:,})",
            end="\r",
            flush=True,
        )
    print()
    return counts


_CHILD_W = {
    "diagnoses": DX_W,
    "lab_results": LAB_W,
    "medications": MED_W,
    "procedures": PROC_W,
    "vital_signs": VS_W,
    "claims": CLAIM_W,
}


async def regenerate_child(
    conn: asyncpg.Connection, table: str, scale: Scale, *, flush: int = 50_000
) -> int:
    """Generate a single child table from the encounters already in the DB.

    Used by the standalone per-entity scripts (seed_diagnoses / seed_lab_results
    / seed_claims). Streams encounters with a server-side cursor so it scales to
    millions of rows without loading them into memory. Cross-table condition
    bias is not applied here (that only happens in the full streaming pipeline).
    """
    if table not in _CHILD_W:
        raise ValueError(f"regenerate_child does not support {table!r}")

    total_enc = int(await conn.fetchval("SELECT count(*) FROM encounters"))
    if total_enc == 0:
        print("  No encounters in DB — seed encounters first.")
        return 0
    target = getattr(scale, table)
    lam = _lambdas(target, total_enc, _CHILD_W[table])
    if table == "claims":
        lam = [min(0.98, x) for x in lam]

    prov_ids = [
        r["id"]
        for r in await conn.fetch(
            "SELECT id FROM providers WHERE provider_type = 'physician' LIMIT 5000"
        )
    ] or [r["id"] for r in await conn.fetch("SELECT id FROM providers LIMIT 5000")]

    cols = COLS[table]
    buf: list[tuple] = []
    loaded = 0
    cur_year = date.today().year
    query = (
        "SELECT e.id, e.patient_id, e.encounter_type, e.admit_date, "
        "e.total_charge, p.date_of_birth "
        "FROM encounters e JOIN patients p ON p.id = e.patient_id"
    )

    async def flush_buf():
        nonlocal loaded, buf
        if buf:
            await conn.copy_records_to_table(table, records=buf, columns=list(cols))
            loaded += len(buf)
            print(f"  [{table}] {loaded:>12,} rows", end="\r", flush=True)
            buf = []

    async with conn.transaction():
        async for rec in conn.cursor(query, prefetch=2000):
            etype = rec["encounter_type"]
            li = lam[_TYPE_IDX.get(etype, 0)]
            enc_id, pid, admit = rec["id"], rec["patient_id"], rec["admit_date"]
            admit_d = admit.date()
            prov = random.choice(prov_ids)
            if table == "claims":
                if random.random() < li:
                    _gen_claim(
                        enc_id, pid, admit_d, float(rec["total_charge"] or 0), buf
                    )
            else:
                n = int(np.random.poisson(li))
                if n:
                    if table == "diagnoses":
                        age = max(0, cur_year - rec["date_of_birth"].year)
                        _gen_diagnoses(enc_id, pid, admit_d, age, n, buf)
                    elif table == "lab_results":
                        _gen_labs(enc_id, pid, admit, prov, n, set(), buf)
                    elif table == "medications":
                        _gen_meds(enc_id, pid, admit_d, prov, n, set(), buf)
                    elif table == "procedures":
                        _gen_procedures(enc_id, pid, admit, prov, n, buf)
                    elif table == "vital_signs":
                        _gen_vitals(enc_id, pid, admit, n, buf)
            if len(buf) >= flush:
                await flush_buf()
        await flush_buf()
    print(f"\n  [{table}] {loaded:,} rows generated from {total_enc:,} encounters")
    return loaded


async def build_readmissions(conn: asyncpg.Connection) -> int:
    """Derive 30-day readmissions from the inpatient encounter timeline (in-DB)."""
    await conn.execute(
        """
        INSERT INTO readmissions
            (id, index_encounter_id, readmit_encounter_id, patient_id,
             days_to_readmit, readmit_reason, created_at, updated_at)
        SELECT gen_random_uuid(), idx.id, nxt.id, idx.patient_id,
               (nxt.admit_date::date - idx.discharge_date::date),
               (ARRAY[%s])[floor(random()*%s + 1)],
               now(), now()
        FROM encounters idx
        JOIN LATERAL (
            SELECT e2.id, e2.admit_date
            FROM encounters e2
            WHERE e2.patient_id = idx.patient_id
              AND e2.encounter_type = 'Inpatient'
              AND e2.admit_date > idx.discharge_date
              AND e2.admit_date <= idx.discharge_date + INTERVAL '30 days'
            ORDER BY e2.admit_date
            LIMIT 1
        ) nxt ON true
        WHERE idx.encounter_type = 'Inpatient'
          AND idx.discharge_date IS NOT NULL
        """
        % (
            ",".join("'" + r.replace("'", "''") + "'" for r in R.READMIT_REASONS),
            len(R.READMIT_REASONS),
        )
    )
    n = await conn.fetchval("SELECT count(*) FROM readmissions")
    print(f"  [readmissions] {n:,} rows (derived in-database)")
    return int(n)
