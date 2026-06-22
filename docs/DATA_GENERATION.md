# Synthetic Data Generation Guide

A scalable, streaming pipeline that produces a realistic healthcare analytics
dataset (no real PHI). It uses PostgreSQL **binary COPY** for throughput and
generates encounter child-records **in memory-bounded chunks**, so peak RAM is
flat from 100K to 5M+ rows.

## Layout
```
backend/
  seeding/
    scales.py        # demo | small | medium | prod  → target row counts
    reference.py     # ICD-10 / LOINC / RxNorm / CPT / DRG + US distributions
    bulk.py          # asyncpg connection + chunked COPY loader (Supabase-aware)
    pipeline.py      # streaming generators + in-DB readmission derivation
  scripts/seed/
    seed_all.py      # orchestrator (run this)
    seed_doctors.py  # hospitals + departments + providers (physicians/nurses)
    seed_patients.py # patient population
    seed_diagnoses.py / seed_lab_results.py / seed_claims.py  # per-entity, from existing encounters
```

## Quick start
```bash
cd backend
# full requested volume (~6.6M rows), wipe-and-reload, plus demo login users:
python -m scripts.seed.seed_all --scale prod --truncate --users
# fast smoke test:
python -m scripts.seed.seed_all --scale demo --truncate --users
```
Prereqs: `alembic upgrade head` (or `supabase/migration.sql`) already applied,
and `.env` pointing at the target DB (`SUPABASE_DB_URL` or `POSTGRES_*`).

## Scale presets (`seeding/scales.py`)

| Entity | demo | small | medium | **prod** |
|---|--:|--:|--:|--:|
| Hospitals (facilities) | 10 | 50 | 200 | **500** |
| Doctors (physicians) | 40 | 500 | 2,500 | **5,000** |
| Nurses | 80 | 1,000 | 5,000 | **10,000** |
| Patients | 500 | 10,000 | 50,000 | **100,000** |
| Appointments (encounters) | 2,000 | 50,000 | 1,000,000 | **2,000,000** |
| Diagnoses | 1,500 | 20,000 | 250,000 | **500,000** |
| Lab Results | 4,000 | 80,000 | 1,000,000 | **2,000,000** |
| Prescriptions (medications) | 2,000 | 40,000 | 500,000 | **1,000,000** |
| Claims | 1,000 | 20,000 | 250,000 | **500,000** |
| Procedures (suppl.) | 1,200 | 24,000 | 200,000 | **400,000** |
| Vital signs (suppl.) | 3,000 | 60,000 | 300,000 | **600,000** |
| **Total rows** | ~15K | ~306K | ~3.5M | **~6.6M** |

> **Schema mapping.** The requested entities map onto the existing validated
> 12-table clinical schema: *Hospitals→`facilities`*, *Doctors/Nurses→`providers`*
> (distinguished by the new `providers.provider_type`), *Appointments→`encounters`*,
> *Prescriptions→`medications`*. This preserves the SQL allow-list, RLS policies,
> RAG schema vectors, and dashboards — nothing downstream had to change.

## What makes the data realistic
- **Demographics:** US-representative age (utilization-weighted toward 65+),
  gender, race/ethnicity, and state-population-weighted geography. Medicare skews
  to 65+.
- **Prevalence-weighted, age-gated diagnoses:** hypertension/diabetes/CKD/CHF
  appear with realistic relative frequency; pediatric patients can't get
  adult-onset codes.
- **Cross-table correlation:** a diabetic encounter produces elevated
  glucose/HbA1c labs **and** metformin/insulin orders; hypertensive/cardiac
  encounters get matching drug classes.
- **Encounter intensity:** inpatient/ED encounters carry far more diagnoses,
  labs, procedures and vitals than outpatient/telehealth (Poisson-rated so totals
  land on the scale targets — see `pipeline._lambdas`).
- **Financials:** charges by encounter type, payer mix, paid/denied/pending
  claim statuses with denial reasons.
- **30-day readmissions** are derived in-database from the inpatient timeline
  (`pipeline.build_readmissions`), so they're internally consistent.

## Per-entity / resumable seeding
Each named script is standalone. The child scripts stream existing encounters via
a server-side cursor (so they scale without loading rows into memory):
```bash
python scripts/seed/seed_doctors.py   --scale prod      # workforce first
python scripts/seed/seed_patients.py  --scale prod
# (encounters via seed_all, or seed_all then re-roll a child table:)
python scripts/seed/seed_diagnoses.py    --scale prod
python scripts/seed/seed_lab_results.py  --scale prod
python scripts/seed/seed_claims.py       --scale prod
```

## Throughput, time & storage (measured + extrapolated)
Measured on local PostgreSQL 16, `small` scale: **~306K rows → 90 MB** including
indexes. COPY sustains tens of thousands of rows/sec; generation (Python/Faker)
is the bottleneck.

| Scale | Rows | Est. DB size¹ | Est. wall time² |
|---|--:|--:|--:|
| demo | ~15K | ~6 MB | seconds |
| small | ~306K | ~90 MB (measured) | ~30–60 s |
| medium | ~3.5M | ~1.2–1.6 GB | ~8–15 min |
| **prod** | ~6.6M | **~2.5–4 GB** | ~20–40 min |

¹ Includes indexes; varies with Postgres/Supabase fillfactor.
² Single process; dominated by row generation, not COPY. Network-bound when
seeding a remote Supabase from a laptop — seed from a VM in the same region for
the prod scale, or use `medium` and scale up.

> **Tip for remote Supabase:** for the `prod` load, prefer the **direct
> connection or session pooler (:5432)** over the transaction pooler — COPY
> throughput is higher. Run `ANALYZE` is issued automatically at the end.
