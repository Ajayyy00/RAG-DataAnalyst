"""
Spider Benchmark Evaluation
==============================
Measures execution accuracy on Spider dev set.

Metrics computed:
  - Execution Accuracy (EX): % queries where predicted result == gold result
  - Exact Match (EM): % queries where predicted SQL == gold SQL (normalised)
  - Valid SQL Rate: % predictions that are syntactically valid
  - Component F1: per-clause precision/recall (SELECT, WHERE, GROUP BY, ORDER BY)

Usage:
    python evaluation/eval_spider.py \\
        --model-path outputs/qlora-codellama-7b-text2sql/final \\
        --spider-dir data/spider \\
        --output-file results/eval_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import torch
from tqdm import tqdm
import datasets
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.prepare_dataset import build_inference_prompt, SpiderSchemaExtractor

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# SQL Normalizer
# ─────────────────────────────────────────────────────────────

class SQLNormalizer:
    """Normalizes SQL queries for fair comparison."""

    KEYWORDS = {
        "select", "from", "where", "group", "by", "order", "having",
        "limit", "join", "inner", "left", "right", "outer", "on",
        "and", "or", "not", "in", "like", "between", "is", "null",
        "distinct", "count", "sum", "avg", "min", "max", "as",
        "asc", "desc", "union", "intersect", "except",
    }

    def normalize(self, sql: str) -> str:
        if not sql:
            return ""
        # Lowercase
        sql = sql.lower().strip()
        # Remove trailing semicolon
        sql = sql.rstrip(";")
        # Collapse whitespace
        sql = re.sub(r"\s+", " ", sql)
        # Remove backticks and double quotes around identifiers
        sql = re.sub(r'[`"]', '', sql)
        # Normalize string literals to lowercase
        sql = re.sub(r"'([^']*)'\)", lambda m: f"'{m.group(1).lower()}'", sql)
        return sql.strip()

    def extract_clauses(self, sql: str) -> Dict[str, str]:
        """Extract SQL clauses for component F1 evaluation."""
        sql = self.normalize(sql)
        clauses: Dict[str, str] = {}

        patterns = [
            ("select",   r"select\s+(.*?)(?:\s+from|$)"),
            ("from",     r"from\s+(.*?)(?:\s+where|\s+group|\s+order|\s+limit|\s+having|$)"),
            ("where",    r"where\s+(.*?)(?:\s+group|\s+order|\s+limit|\s+having|$)"),
            ("group_by", r"group\s+by\s+(.*?)(?:\s+order|\s+limit|\s+having|$)"),
            ("order_by", r"order\s+by\s+(.*?)(?:\s+limit|$)"),
            ("having",   r"having\s+(.*?)(?:\s+order|\s+limit|$)"),
            ("limit",    r"limit\s+(\d+)"),
        ]

        for clause_name, pattern in patterns:
            m = re.search(pattern, sql, re.IGNORECASE | re.DOTALL)
            if m:
                clauses[clause_name] = m.group(1).strip()

        return clauses


# ─────────────────────────────────────────────────────────────
# SQL Executor
# ─────────────────────────────────────────────────────────────

def execute_sql(db_path: str, sql: str, timeout: int = 30) -> Optional[List]:
    """Execute SQL on a SQLite database and return results."""
    if not os.path.exists(db_path):
        return None
    try:
        conn = sqlite3.connect(db_path, timeout=timeout)
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.cursor()
        cursor.execute(sql)
        results = cursor.fetchall()
        conn.close()
        # Normalise results: sort rows, lowercase strings
        normalised = set()
        for row in results:
            normalised.add(tuple(
                str(v).lower().strip() if v is not None else "null"
                for v in row
            ))
        return sorted(normalised)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# Evaluation Metrics
# ─────────────────────────────────────────────────────────────

@dataclass
class EvalResult:
    question: str
    db_id: str
    gold_sql: str
    pred_sql: str
    exact_match: bool
    execution_match: bool
    valid_sql: bool
    gold_clauses: Dict[str, str] = field(default_factory=dict)
    pred_clauses: Dict[str, str] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class EvalMetrics:
    total: int = 0
    exact_match: int = 0
    execution_match: int = 0
    valid_sql: int = 0

    # Per-clause component F1
    clause_tp: Dict[str, int] = field(default_factory=lambda: {c: 0 for c in ["select","from","where","group_by","order_by"]})
    clause_pred: Dict[str, int] = field(default_factory=lambda: {c: 0 for c in ["select","from","where","group_by","order_by"]})
    clause_gold: Dict[str, int] = field(default_factory=lambda: {c: 0 for c in ["select","from","where","group_by","order_by"]})

    @property
    def exact_match_acc(self) -> float:
        return self.exact_match / self.total if self.total else 0.0

    @property
    def execution_acc(self) -> float:
        return self.execution_match / self.total if self.total else 0.0

    @property
    def valid_sql_rate(self) -> float:
        return self.valid_sql / self.total if self.total else 0.0

    def component_f1(self, clause: str) -> Tuple[float, float, float]:
        tp = self.clause_tp[clause]
        pred = self.clause_pred[clause]
        gold = self.clause_gold[clause]
        precision = tp / pred if pred else 0.0
        recall    = tp / gold if gold else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        return precision, recall, f1

    def to_dict(self) -> Dict:
        component_f1 = {}
        for clause in self.clause_tp:
            p, r, f1 = self.component_f1(clause)
            component_f1[clause] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4)}
        return {
            "total": self.total,
            "exact_match_acc": round(self.exact_match_acc, 4),
            "execution_acc": round(self.execution_acc, 4),
            "valid_sql_rate": round(self.valid_sql_rate, 4),
            "component_f1": component_f1,
            "meets_target": self.execution_acc >= 0.80,
        }


# ─────────────────────────────────────────────────────────────
# Model Inference
# ─────────────────────────────────────────────────────────────

def load_eval_model(model_path: str):
    """Load a trained model for evaluation."""
    from transformers import BitsAndBytesConfig
    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    # Check if it's a merged model or PEFT adapter
    if (Path(model_path) / "adapter_config.json").exists():
        logger.info("Loading PEFT adapter model", path=model_path)
        from peft import AutoPeftModelForCausalLM
        model = AutoPeftModelForCausalLM.from_pretrained(
            model_path,
            device_map="auto",
            quantization_config=bnb_cfg,
            torch_dtype=torch.float16,
        )
    else:
        logger.info("Loading merged model", path=model_path)
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            device_map="auto",
            quantization_config=bnb_cfg,
            torch_dtype=torch.float16,
            trust_remote_code=True,
        )
    model.eval()
    return model, tokenizer


def predict_sql(
    model,
    tokenizer,
    prompt: str,
    max_new_tokens: int = 256,
    temperature: float = 0.1,
) -> str:
    """Generate SQL prediction for a single prompt."""
    inputs = tokenizer(
        prompt, return_tensors="pt", truncation=True, max_length=1900
    ).to(model.device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            do_sample=False,
            repetition_penalty=1.1,
            eos_token_id=tokenizer.eos_token_id,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated = tokenizer.decode(
        outputs[0][inputs["input_ids"].shape[1]:],
        skip_special_tokens=True,
    )

    # Extract SQL from generation
    sql = generated.split("</s>")[0].strip()
    sql = re.sub(r"^(###\s*SQL\s*:?\s*)", "", sql, flags=re.IGNORECASE).strip()
    return sql


# ─────────────────────────────────────────────────────────────
# Main Evaluator
# ─────────────────────────────────────────────────────────────

class SpiderEvaluator:
    """Full Spider evaluation pipeline."""

    def __init__(self, spider_db_root: Path, timeout: int = 30):
        self.db_root  = spider_db_root
        self.timeout  = timeout
        self.norm     = SQLNormalizer()

    def _db_path(self, db_id: str) -> str:
        return str(self.db_root / db_id / f"{db_id}.sqlite")

    def evaluate_one(self, item: Dict) -> EvalResult:
        question = item["question"]
        db_id    = item["db_id"]
        gold_sql = item["gold_sql"]
        pred_sql = item["pred_sql"]

        db_path = self._db_path(db_id)
        normalizer = SQLNormalizer()

        gold_norm = normalizer.normalize(gold_sql)
        pred_norm = normalizer.normalize(pred_sql)
        exact_match = (gold_norm == pred_norm)

        gold_clauses = normalizer.extract_clauses(gold_sql)
        pred_clauses = normalizer.extract_clauses(pred_sql)

        # Check if prediction is valid SQL
        gold_result = execute_sql(db_path, gold_sql, self.timeout)
        pred_result = execute_sql(db_path, pred_sql, self.timeout)
        valid_sql   = pred_result is not None

        # Execution match
        if gold_result is not None and pred_result is not None:
            exec_match = (gold_result == pred_result)
        else:
            exec_match = False

        return EvalResult(
            question=question,
            db_id=db_id,
            gold_sql=gold_sql,
            pred_sql=pred_sql,
            exact_match=exact_match,
            execution_match=exec_match,
            valid_sql=valid_sql,
            gold_clauses=gold_clauses,
            pred_clauses=pred_clauses,
        )

    def compute_metrics(self, results: List[EvalResult]) -> EvalMetrics:
        metrics = EvalMetrics(total=len(results))
        for r in results:
            if r.exact_match:      metrics.exact_match      += 1
            if r.execution_match:  metrics.execution_match  += 1
            if r.valid_sql:        metrics.valid_sql        += 1
            for clause in metrics.clause_tp:
                gold_val = r.gold_clauses.get(clause, "")
                pred_val = r.pred_clauses.get(clause, "")
                if gold_val: metrics.clause_gold[clause] += 1
                if pred_val: metrics.clause_pred[clause] += 1
                if gold_val and pred_val and gold_val == pred_val:
                    metrics.clause_tp[clause] += 1
        return metrics

    def run(
        self,
        model,
        tokenizer,
        spider_data: datasets.Dataset,
        schema_extractor: SpiderSchemaExtractor,
        batch_size: int = 8,
        max_samples: Optional[int] = None,
    ) -> Tuple[EvalMetrics, List[EvalResult]]:
        items = list(spider_data)
        if max_samples:
            items = items[:max_samples]

        results: List[EvalResult] = []

        for i, item in enumerate(tqdm(items, desc="Evaluating")):
            schema   = schema_extractor.get_schema(item["db_id"])
            prompt   = build_inference_prompt(schema, item["question"])
            pred_sql = predict_sql(model, tokenizer, prompt)

            results.append(self.evaluate_one({
                "question": item["question"],
                "db_id":    item["db_id"],
                "gold_sql": item["query"],
                "pred_sql": pred_sql,
            }))

            if (i + 1) % 50 == 0:
                partial = self.compute_metrics(results)
                logger.info(
                    "Partial results",
                    processed=i + 1,
                    exec_acc=round(partial.execution_acc, 3),
                    exact_match=round(partial.exact_match_acc, 3),
                )

        metrics = self.compute_metrics(results)
        return metrics, results


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import structlog
    structlog.configure(logger_factory=structlog.PrintLoggerFactory())

    parser = argparse.ArgumentParser(description="Spider Evaluation")
    parser.add_argument("--model-path",   required=True)
    parser.add_argument("--spider-dir",   required=True)
    parser.add_argument("--output-file",  default="results/eval_results.json")
    parser.add_argument("--max-samples",  type=int, default=None)
    parser.add_argument("--batch-size",   type=int, default=4)
    args = parser.parse_args()

    spider_dir = Path(args.spider_dir)
    model, tokenizer = load_eval_model(args.model_path)

    logger.info("Loading Spider dev set")
    spider_ds = datasets.load_dataset("spider", split="validation", trust_remote_code=True)

    schema_ext = SpiderSchemaExtractor(spider_dir / "database")
    evaluator  = SpiderEvaluator(spider_db_root=spider_dir / "database")

    logger.info("Starting evaluation", model=args.model_path, samples=args.max_samples or len(spider_ds))
    metrics, results = evaluator.run(
        model=model,
        tokenizer=tokenizer,
        spider_data=spider_ds,
        schema_extractor=schema_ext,
        max_samples=args.max_samples,
    )

    # ── Print report ────────────────────────────────────────────
    metrics_dict = metrics.to_dict()
    print("\n" + "=" * 60)
    print("  Spider Evaluation Results")
    print("=" * 60)
    print(f"  Total examples    : {metrics.total}")
    print(f"  Execution Accuracy: {metrics.execution_acc:.2%}  (target: 80%)")
    print(f"  Exact Match       : {metrics.exact_match_acc:.2%}")
    print(f"  Valid SQL Rate    : {metrics.valid_sql_rate:.2%}")
    print("")
    print("  Component F1:")
    for clause, vals in metrics_dict["component_f1"].items():
        print(f"    {clause:<12}  P={vals['precision']:.3f}  R={vals['recall']:.3f}  F1={vals['f1']:.3f}")
    target_met = metrics.execution_acc >= 0.80
    print("")
    print(f"  Target (80% EX): {'MET' if target_met else 'NOT MET'}")
    print("=" * 60)

    # ── Save results ───────────────────────────────────────────
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump({
            "metrics": metrics_dict,
            "results": [asdict(r) for r in results],
        }, f, indent=2)
    print(f"\n  Full results saved to: {output_path}")
