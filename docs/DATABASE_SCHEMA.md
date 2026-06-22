# Database Schema

PostgreSQL / Supabase. 19 tables: **12 clinical/reference** (queryable by the
copilot), **7 application/system** (auth, audit, copilot, alerts — never exposed
to AI-generated SQL). UUID primary keys, `created_at`/`updated_at` everywhere.

## Entity-Relationship diagram (clinical core)

```mermaid
erDiagram
    facilities   ||--o{ departments  : has
    departments  ||--o{ providers    : staffs
    departments  ||--o{ encounters   : hosts
    providers    ||--o{ encounters   : attends
    patients     ||--o{ encounters   : has
    encounters   ||--o{ diagnoses    : codes
    encounters   ||--o{ procedures   : performs
    encounters   ||--o{ medications  : orders
    encounters   ||--o{ lab_results  : results
    encounters   ||--o{ vital_signs  : records
    encounters   ||--o{ claims       : bills
    patients     ||--o{ diagnoses    : has
    patients     ||--o{ medications  : takes
    patients     ||--o{ lab_results  : has
    encounters   ||--o{ readmissions : "index/readmit"

    facilities {
        uuid id PK
        string name
        string city
        string state
        string facility_type
    }
    departments {
        uuid id PK
        string name
        string dept_type
        uuid facility_id FK
    }
    providers {
        uuid id PK
        string npi UK
        string provider_type "physician | nurse"
        string specialty
        uuid department_id FK
    }
    patients {
        uuid id PK
        string mrn UK
        date date_of_birth
        string gender
        string race
        string ethnicity
        string zip_code
        string insurance_type
    }
    encounters {
        uuid id PK
        uuid patient_id FK
        uuid provider_id FK
        uuid department_id FK
        string encounter_type "Inpatient|ED|Outpatient|Telehealth"
        timestamptz admit_date
        timestamptz discharge_date
        string drg_code
        numeric total_charge
        numeric total_payment
    }
    diagnoses {
        uuid id PK
        uuid encounter_id FK
        uuid patient_id FK
        string icd10_code
        string diagnosis_type
        bool is_chronic
    }
    medications {
        uuid id PK
        uuid encounter_id FK
        uuid patient_id FK
        string drug_name
        string rxnorm_code
        date start_date
        date end_date
    }
    lab_results {
        uuid id PK
        uuid encounter_id FK
        uuid patient_id FK
        string loinc_code
        numeric numeric_value
        string abnormal_flag "N|H|HH|L|LL"
        timestamptz result_date
    }
    claims {
        uuid id PK
        uuid encounter_id FK
        uuid patient_id FK
        string payer_name
        numeric billed_amount
        numeric paid_amount
        string claim_status "Paid|Denied|Pending"
    }
    readmissions {
        uuid id PK
        uuid index_encounter_id FK
        uuid readmit_encounter_id FK
        uuid patient_id FK
        int days_to_readmit
    }
```
(`procedures` and `vital_signs` follow the same encounter/patient pattern; omitted
above for readability.)

## Tables

### Clinical & reference (12 — copilot-queryable; on the SQL allow-list)
| Table | Grain | Key columns |
|---|---|---|
| `facilities` | one row per hospital/clinic/lab | `name, city, state, facility_type` |
| `departments` | dept within a facility | `name, dept_type, facility_id` |
| `providers` | clinician | `npi, provider_type, specialty, department_id` |
| `patients` | patient master | `mrn, date_of_birth, gender, race, ethnicity, zip_code, insurance_type` |
| `encounters` | visit / "appointment" | `encounter_type, admit_date, discharge_date, drg_code, total_charge, total_payment` |
| `diagnoses` | ICD-10 per encounter | `icd10_code, diagnosis_type, is_chronic` |
| `procedures` | CPT per encounter | `cpt_code, charge_amount` |
| `medications` | order / "prescription" | `drug_name, rxnorm_code, start_date, end_date` |
| `lab_results` | LOINC result | `loinc_code, numeric_value, abnormal_flag, result_date` |
| `vital_signs` | vitals reading | `systolic_bp, heart_rate, temperature_f, spo2_pct` |
| `claims` | insurance claim | `payer_name, billed_amount, paid_amount, claim_status` |
| `readmissions` | 30-day readmit link | `index_encounter_id, readmit_encounter_id, days_to_readmit` |

### Application / system (7 — NOT exposed to AI-generated SQL)
`users` (RBAC; `first_name`/`last_name` Fernet-encrypted at rest),
`audit_logs`, `copilot_sessions`, `copilot_messages`, `nl_sql_pairs`,
`schema_registry`, `alerts`.

## Security controls on the schema
- **Row-Level Security** (`ENABLE` + `FORCE`) on all clinical tables. Policy pair
  per table: `*_trusted` (no `app.current_user_role` GUC → trusted backend, full
  access) and `*_role_read` (GUC set → role-gated `SELECT` only). `claims` is
  restricted to `admin`/`analyst`.
- **Least-privilege role** `hc_readonly` executes AI-generated SQL: `SELECT` on
  the 12 clinical/reference tables only; no access to `users`/`audit_logs`/
  `copilot_*`.
- **PHI encryption at rest:** `users.first_name/last_name` stored as `TEXT`
  Fernet ciphertext via the `EncryptedString` type.

Regenerate the Supabase DDL from these models any time:
`python backend/scripts/emit_supabase_sql.py` → `supabase/{migration,rollback,rls_policies}.sql`.
