# Performance Benchmark Report

- Database size: **90 MB**
- Core fact rows (patients+encounters+dx+labs+meds+claims): **219,489**
- Runs per query: 9  ·  warm cache

| Query | min | p50 | p95 | max |
|---|--:|--:|--:|--:|
| Q1 patient count | 49.6 | 50.0 | 50.3 | 50.3 | (ms)
| Q2 most prescribed meds (30d) | 49.7 | 50.3 | 59.1 | 59.1 | (ms)
| Q3 readmission trend (6mo) | 49.4 | 49.9 | 50.4 | 50.4 | (ms)
| Q4 diabetic cohort + avg A1c | 47.5 | 49.8 | 51.8 | 51.8 | (ms)
| Q5 hospital utilization | 60.1 | 68.7 | 70.9 | 70.9 | (ms)
| Q6 payer revenue mix | 49.7 | 50.1 | 51.5 | 51.5 | (ms)
| Q7 abnormal labs by test | 54.1 | 60.0 | 60.4 | 60.4 | (ms)
| Q8 top chronic diagnoses | 59.3 | 60.4 | 70.3 | 70.3 | (ms)
