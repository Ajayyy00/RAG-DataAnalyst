# Text-to-SQL Fine-Tuning Pipeline

**Base model:** CodeLlama-7B  
**Method:** QLoRA (4-bit NF4 + LoRA rank-64)  
**Datasets:** Spider + WikiSQL  
**Target:** ≥80% execution accuracy on Spider benchmark

---

## Architecture

```
CodeLlama-7B (frozen, 4-bit)
       │
  LoRA Adapters
  (r=64, α=128)
  q/k/v/o + gate/up/down proj
       │
  Fine-tuned on
  Spider (7,000 train) + WikiSQL (56,355 train)
  Combined: ~63,000 instruction examples
       │
  Evaluation: Spider dev (1,034 examples)
  Metrics: EX Acc, EM, Valid SQL %, Component F1
```

## Pipeline Components

| Component | File | Description |
|---|---|---|
| **Config** | `configs/qlora_config.yaml` | All hyperparameters in one place |
| **Data** | `data/prepare_dataset.py` | Spider + WikiSQL → instruction format |
| **Train** | `training/train.py` | QLoRA trainer with callbacks |
| **Eval** | `evaluation/eval_spider.py` | Execution accuracy on Spider dev |
| **Infer** | `inference/pipeline.py` | FastAPI serving + batch inference |
| **Docker** | `docker/` | Training + serving containers |

---

## Quick Start

### 1. Install dependencies

```bash
# Training
pip install -r requirements-train.txt

# Serving only
pip install -r requirements-serve.txt
```

### 2. Prepare dataset

```bash
# Downloads Spider + WikiSQL from HuggingFace Hub automatically
python data/prepare_dataset.py \
  --model codellama/CodeLlama-7b-hf \
  --output-dir data/processed
```

### 3. Train

```bash
# Single GPU (A100 40GB recommended)
bash scripts/run_train.sh --config configs/qlora_config.yaml

# Resume from checkpoint
bash scripts/run_train.sh --resume outputs/qlora-codellama-7b-text2sql/checkpoint-1000

# With Docker
docker compose -f docker/docker-compose.yml --profile train up trainer
```

Expected training time: ~6h on A100 40GB (3 epochs, batch size 32 effective)

### 4. Evaluate

```bash
bash scripts/run_eval.sh \
  --model-path outputs/qlora-codellama-7b-text2sql/final \
  --spider-dir data/spider

# Quick sanity check (100 examples)
bash scripts/run_eval.sh \
  --model-path outputs/qlora-codellama-7b-text2sql/final \
  --spider-dir data/spider \
  --max-samples 100
```

### 5. Merge adapters (optional, for deployment)

```bash
bash scripts/merge_adapters.sh \
  --adapter-path outputs/qlora-codellama-7b-text2sql/final \
  --output-path  outputs/merged-codellama-7b-text2sql
```

### 6. Serve

```bash
# Local
bash scripts/run_serve.sh --model-path outputs/merged-codellama-7b-text2sql

# Docker
MODEL_DIR=./outputs/merged-codellama-7b-text2sql \
docker compose -f docker/docker-compose.yml --profile serve up inference
```

API is at `http://localhost:9000` — docs at `http://localhost:9000/docs`.

---

## REST API

### Single prediction

```bash
curl -X POST http://localhost:9000/predict \
  -H 'Content-Type: application/json' \
  -d '{
    "schema_ddl": "CREATE TABLE patients (id INT, name TEXT, age INT, gender TEXT);",
    "question": "How many male patients are older than 60?"
  }'
```

```json
{
  "sql": "SELECT COUNT(*) FROM patients WHERE gender = 'male' AND age > 60;",
  "is_safe": true,
  "is_valid": true,
  "latency_ms": 384.2,
  "confidence": 0.85
}
```

### Batch prediction

```bash
curl -X POST http://localhost:9000/predict/batch \
  -H 'Content-Type: application/json' \
  -d '{
    "items": [
      {"schema": "CREATE TABLE orders (id INT, total FLOAT);", "question": "Total revenue?"},
      {"schema": "CREATE TABLE products (name TEXT, price FLOAT);", "question": "Most expensive product?"}
    ]
  }'
```

---

## Evaluation Results (Expected)

| Metric | Base CodeLlama-7B | After QLoRA |
|---|---|---|
| Execution Accuracy | ~42% | **≥80%** |
| Exact Match | ~38% | ~72% |
| Valid SQL Rate | ~78% | ~96% |
| SELECT F1 | 0.61 | 0.89 |
| WHERE F1 | 0.44 | 0.81 |
| GROUP BY F1 | 0.39 | 0.77 |

---

## Training Configuration

| Parameter | Value | Rationale |
|---|---|---|
| Base model | CodeLlama-7B | Best open code LLM at 7B scale |
| Quantization | 4-bit NF4 | Reduces VRAM from 14GB → 5GB |
| LoRA rank | 64 | Balances capacity vs params |
| LoRA alpha | 128 | 2× rank → stronger adaptation |
| Target modules | All proj layers | Full attention + FFN coverage |
| Batch size | 4 × 8 accum = 32 | Stable gradients |
| Learning rate | 2e-4 | cosine decay from warmup |
| Epochs | 3 | Validated via eval loss |
| Optimizer | paged_adamw_32bit | VRAM-efficient for QLoRA |

---

## Prompt Format

```
<s>[INST] <<SYS>>
You are an expert SQL query generator...
<</SYS>>

### Database Schema:
CREATE TABLE patients (id INT PRIMARY KEY, ...);
CREATE TABLE encounters (id INT, patient_id INT, ...);

### Question:
How many patients had more than 3 encounters last year? [/INST]

### SQL:
SELECT COUNT(DISTINCT p.id)
FROM patients p
JOIN encounters e ON p.id = e.patient_id
WHERE YEAR(e.admit_date) = YEAR(CURDATE()) - 1
GROUP BY p.id
HAVING COUNT(e.id) > 3; </s>
```

---

## Monitoring

- **TensorBoard**: `http://localhost:6006` (start with `--profile train`)
- **Checkpoints**: saved every 500 steps to `outputs/`
- **Best model**: auto-loaded based on `eval_loss`
- **Early stopping**: patience=3 evaluation cycles

---

## File Structure

```
finetune/
├── configs/
│   └── qlora_config.yaml        # All hyperparameters
├── data/
│   └── prepare_dataset.py       # Spider + WikiSQL processor
├── training/
│   └── train.py                 # QLoRA trainer
├── evaluation/
│   └── eval_spider.py           # Spider benchmark evaluator
├── inference/
│   └── pipeline.py              # FastAPI inference server
├── docker/
│   ├── Dockerfile.train         # Training container
│   ├── Dockerfile.serve         # Serving container
│   └── docker-compose.yml       # Full stack orchestration
├── scripts/
│   ├── run_train.sh             # Training launcher
│   ├── run_eval.sh              # Evaluation launcher
│   ├── run_serve.sh             # Server launcher
│   └── merge_adapters.sh        # LoRA → full model merge
├── requirements-train.txt
├── requirements-serve.txt
└── README.md
```
