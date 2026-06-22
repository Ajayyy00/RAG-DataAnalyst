# Analytics Scenarios & Sample Queries

The dataset is sized and correlated to support real BI/RAG/text-to-SQL analytics.
Each scenario below pairs a **natural-language prompt** (paste into the copilot)
with the **SQL** it should produce. All queries touch only allow-listed clinical
tables and were validated against the generated data.

## 1. Diabetic patient cohort
> "How many patients have type 2 diabetes, and what's their average HbA1c?"
```sql
SELECT count(DISTINCT d.patient_id) AS diabetic_patients,
       round(avg(l.numeric_value), 2) AS avg_hba1c
FROM diagnoses d
JOIN lab_results l ON l.patient_id = d.patient_id AND l.loinc_code = '4548-4'
WHERE d.icd10_code IN ('E11.9', 'E11.65');
```
> The generator elevates glucose/HbA1c for diabetic encounters, so this returns a
> clinically plausible mean (~7–8%).

## 2. Heart-disease cohort
> "List the most common cardiac diagnoses and how many patients each affects."
```sql
SELECT icd10_code, icd10_desc, count(DISTINCT patient_id) AS patients
FROM diagnoses
WHERE icd10_code IN ('I25.10', 'I50.9', 'I21.9', 'I10')
GROUP BY icd10_code, icd10_desc
ORDER BY patients DESC;
```

## 3. 30-day readmission rate
> "What is the 30-day inpatient readmission rate over the last 6 months?"
```sql
SELECT date_trunc('month', e.admit_date) AS month,
       count(DISTINCT r.index_encounter_id) AS readmissions,
       count(DISTINCT e.id) AS inpatient_encounters,
       round(100.0 * count(DISTINCT r.index_encounter_id)
             / NULLIF(count(DISTINCT e.id), 0), 2) AS readmit_pct
FROM encounters e
LEFT JOIN readmissions r ON r.index_encounter_id = e.id
WHERE e.encounter_type = 'Inpatient'
  AND e.admit_date >= CURRENT_DATE - INTERVAL '6 months'
GROUP BY 1 ORDER BY 1;
```

## 4. Hospital utilization
> "Which hospitals have the most encounters and total charges?"
```sql
SELECT f.name AS hospital,
       count(e.id) AS encounters,
       round(sum(e.total_charge), 2) AS total_charges
FROM facilities f
JOIN departments dp ON dp.facility_id = f.id
JOIN encounters e   ON e.department_id = dp.id
GROUP BY f.name
ORDER BY encounters DESC
LIMIT 20;
```

## 5. Revenue analytics (payer mix)
> "Show revenue and denial rate by payer."
```sql
SELECT payer_name,
       count(*) AS claims,
       round(sum(paid_amount), 2) AS paid,
       round(100.0 * sum((claim_status = 'Denied')::int) / count(*), 1) AS denial_pct
FROM claims
GROUP BY payer_name
ORDER BY paid DESC;
```

## 6. Medication analytics
> "What were the most prescribed medications this month?"
```sql
SELECT drug_name, count(*) AS prescriptions
FROM medications
WHERE start_date >= date_trunc('month', CURRENT_DATE)
GROUP BY drug_name
ORDER BY prescriptions DESC
LIMIT 10;
```
> "Which patients on insulin also have an HbA1c above 9?" (adherence/risk)
```sql
SELECT DISTINCT m.patient_id
FROM medications m
JOIN lab_results l ON l.patient_id = m.patient_id AND l.loinc_code = '4548-4'
WHERE m.drug_name = 'Insulin Glargine' AND l.numeric_value > 9
LIMIT 100;
```

## 7. Claims analysis
> "Break down claims by status with total billed vs paid."
```sql
SELECT claim_status,
       count(*) AS claims,
       round(sum(billed_amount), 2) AS billed,
       round(sum(paid_amount), 2)  AS paid
FROM claims
GROUP BY claim_status
ORDER BY claims DESC;
```

## 8. Workforce (uses the new `provider_type`)
> "How many physicians vs nurses do we have, by department type?"
```sql
SELECT d.dept_type, p.provider_type, count(*) AS headcount
FROM providers p
JOIN departments d ON d.id = p.department_id
GROUP BY d.dept_type, p.provider_type
ORDER BY d.dept_type, headcount DESC;
```

## 9. Abnormal lab surveillance
> "Which lab tests most often come back abnormal?"
```sql
SELECT test_name, count(*) AS abnormal_results
FROM lab_results
WHERE abnormal_flag IN ('H', 'HH', 'L', 'LL')
GROUP BY test_name
ORDER BY abnormal_results DESC
LIMIT 15;
```

---
These eight+ scenarios are also encoded as automated checks in
`backend/scripts/validate_data.py` and timed in `backend/scripts/benchmark.py`.
