// Demo mock data — used by Demo Mode to populate the UI without a backend

export const DEMO_USER = {
  id: 'demo-user-001',
  username: 'Dr. Demo',
  email: 'demo@healthcopilot.ai',
  role: 'analyst',
  is_active: true,
}

export const DEMO_TOKEN = 'demo-jwt-token-not-real'

export const DEMO_SESSIONS = [
  { id: 'sess-001', title: 'Top diagnoses this quarter', created_at: new Date(Date.now() - 86400000).toISOString() },
  { id: 'sess-002', title: 'Readmission rates by dept', created_at: new Date(Date.now() - 172800000).toISOString() },
  { id: 'sess-003', title: 'Average length of stay', created_at: new Date(Date.now() - 259200000).toISOString() },
]

export const DEMO_MESSAGES = [
  {
    id: 'msg-001',
    role: 'user',
    content: 'What are the top 10 diagnoses by frequency this quarter?',
    timestamp: new Date(Date.now() - 120000).toISOString(),
  },
  {
    id: 'msg-002',
    role: 'assistant',
    timestamp: new Date(Date.now() - 90000).toISOString(),
    sql: `SELECT
  d.icd10_code,
  d.description,
  COUNT(*) AS frequency,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct
FROM diagnoses d
JOIN encounters e ON e.id = d.encounter_id
WHERE e.admit_date >= DATE_TRUNC('quarter', CURRENT_DATE)
GROUP BY d.icd10_code, d.description
ORDER BY frequency DESC
LIMIT 10;`,
    isValid: true,
    columns: ['icd10_code', 'description', 'frequency', 'pct'],
    rows: [
      { icd10_code: 'J96.00', description: 'Acute respiratory failure', frequency: 842, pct: 12.4 },
      { icd10_code: 'I50.9',  description: 'Heart failure, unspecified', frequency: 731, pct: 10.8 },
      { icd10_code: 'N18.3',  description: 'Chronic kidney disease, stage 3', frequency: 698, pct: 10.3 },
      { icd10_code: 'E11.9',  description: 'Type 2 diabetes mellitus', frequency: 654, pct: 9.6 },
      { icd10_code: 'I10',    description: 'Essential hypertension', frequency: 589, pct: 8.7 },
      { icd10_code: 'J18.9',  description: 'Pneumonia, unspecified', frequency: 512, pct: 7.5 },
      { icd10_code: 'A41.9',  description: 'Sepsis, unspecified', frequency: 478, pct: 7.0 },
      { icd10_code: 'K92.1',  description: 'Melena (GI bleed)', frequency: 401, pct: 5.9 },
      { icd10_code: 'G30.9',  description: "Alzheimer's disease", frequency: 374, pct: 5.5 },
      { icd10_code: 'C34.10', description: 'Lung cancer, upper lobe', frequency: 319, pct: 4.7 },
    ],
    rowCount: 10,
    chartType: 'bar',
    chartConfig: {
      data: [
        { icd10_code: 'J96.00', frequency: 842 },
        { icd10_code: 'I50.9',  frequency: 731 },
        { icd10_code: 'N18.3',  frequency: 698 },
        { icd10_code: 'E11.9',  frequency: 654 },
        { icd10_code: 'I10',    frequency: 589 },
        { icd10_code: 'J18.9',  frequency: 512 },
        { icd10_code: 'A41.9',  frequency: 478 },
        { icd10_code: 'K92.1',  frequency: 401 },
        { icd10_code: 'G30.9',  frequency: 374 },
        { icd10_code: 'C34.10', frequency: 319 },
      ],
      xKey: 'icd10_code',
      yKey: 'frequency',
      yKeys: ['frequency'],
    },
    insights: [
      'Acute respiratory failure (J96.00) is the leading diagnosis at 12.4% of encounters, suggesting potential gaps in preventive pulmonary care protocols.',
      'Heart failure and CKD together account for 21.1% of diagnoses — co-morbidity management programmes may significantly reduce readmission burden.',
      'Type 2 diabetes (E11.9) at 9.6% indicates a high-risk metabolic disease burden requiring structured HbA1c monitoring pathways.',
      'Sepsis (A41.9) represents 7.0% of diagnoses — early-warning scoring systems and antibiotic stewardship programmes should be reviewed.',
      'The top 5 diagnoses are all chronic or preventable conditions, suggesting significant opportunity for outpatient intervention programmes.',
    ],
  },
  {
    id: 'msg-003',
    role: 'user',
    content: 'Show me monthly readmission trends for the last 6 months',
    timestamp: new Date(Date.now() - 60000).toISOString(),
  },
  {
    id: 'msg-004',
    role: 'assistant',
    timestamp: new Date(Date.now() - 30000).toISOString(),
    sql: `SELECT
  DATE_TRUNC('month', r.readmission_date) AS month,
  COUNT(*) AS readmissions,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER (), 0), 1) AS rate_pct
FROM readmissions r
WHERE r.readmission_date >= CURRENT_DATE - INTERVAL '6 months'
GROUP BY month
ORDER BY month;`,
    isValid: true,
    columns: ['month', 'readmissions', 'rate_pct'],
    rows: [
      { month: 'Jan 2026', readmissions: 142, rate_pct: 14.2 },
      { month: 'Feb 2026', readmissions: 128, rate_pct: 12.8 },
      { month: 'Mar 2026', readmissions: 155, rate_pct: 15.5 },
      { month: 'Apr 2026', readmissions: 119, rate_pct: 11.9 },
      { month: 'May 2026', readmissions: 134, rate_pct: 13.4 },
      { month: 'Jun 2026', readmissions: 98,  rate_pct: 9.8 },
    ],
    rowCount: 6,
    chartType: 'line',
    chartConfig: {
      data: [
        { month: 'Jan', readmissions: 142, rate_pct: 14.2 },
        { month: 'Feb', readmissions: 128, rate_pct: 12.8 },
        { month: 'Mar', readmissions: 155, rate_pct: 15.5 },
        { month: 'Apr', readmissions: 119, rate_pct: 11.9 },
        { month: 'May', readmissions: 134, rate_pct: 13.4 },
        { month: 'Jun', readmissions: 98,  rate_pct: 9.8 },
      ],
      xKey: 'month',
      yKey: 'readmissions',
      yKeys: ['readmissions', 'rate_pct'],
    },
    insights: [
      '30-day readmissions peaked in March 2026 (155 cases, 15.5%) — this spike correlates with the seasonal respiratory illness surge.',
      'June 2026 shows the lowest readmission count (98) and rate (9.8%), a 36.8% improvement over the March peak.',
      'The overall 6-month trend is downward, suggesting care transition improvements are having measurable impact.',
      'February dip followed by March surge is a recurring seasonal pattern — proactive capacity planning is recommended for Q1 2027.',
    ],
  },
]
