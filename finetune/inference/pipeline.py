"""
Text-to-SQL Inference Pipeline
================================
Production-ready inference pipeline for the fine-tuned CodeLlama-7B model.

Features:
  - Single and batch inference
  - Schema-aware prompting
  - SQL post-processing and safety validation
  - Confidence scoring
  - FastAPI REST server

Usage:
    # Direct Python
    from inference.pipeline import TextToSQLPipeline
    pipe = TextToSQLPipeline.from_pretrained("outputs/merged-codellama-7b")
    result = pipe.predict(schema="CREATE TABLE patients (...)", question="How many patients?")
    print(result.sql)

    # REST API server
    python inference/pipeline.py --model-path outputs/merged-codellama-7b --serve
"""
from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Dict, List, Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
import structlog

logger = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are an expert SQL query generator. Given a database schema and a "
    "natural language question, generate the correct SQL query. "
    "Output ONLY the SQL query with no explanation."
)


def build_inference_prompt(schema: str, question: str) -> str:
    return (
        f"<s>[INST] <<SYS>>\n{SYSTEM_PROMPT}\n<</SYS>>\n\n"
        f"### Database Schema:\n{schema}\n\n"
        f"### Question:\n{question} [/INST]\n\n### SQL:\n"
    )


# ─────────────────────────────────────────────────────────────
# SQL Post-Processor
# ─────────────────────────────────────────────────────────────

class SQLPostProcessor:
    """Cleans and safety-checks raw model output."""

    _DANGEROUS = re.compile(
        r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)\b",
        re.IGNORECASE,
    )

    def process(self, raw: str) -> str:
        sql = raw.split("</s>")[0].split("[INST]")[0].strip()
        sql = re.sub(r"```(?:sql)?\s*", "", sql)
        sql = re.sub(r"```", "", sql)
        sql = re.sub(r"^#{1,3}\s*SQL\s*:?\s*", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"\s+", " ", sql).strip()
        if sql and not sql.endswith(";"):
            sql += ";"
        return sql

    def is_safe(self, sql: str) -> bool:
        return not bool(self._DANGEROUS.search(sql))

    def is_valid_select(self, sql: str) -> bool:
        clean = sql.strip().upper()
        return clean.startswith("SELECT") or clean.startswith("WITH")


# ─────────────────────────────────────────────────────────────
# Inference Result
# ─────────────────────────────────────────────────────────────

@dataclass
class InferenceResult:
    sql: str
    is_safe: bool
    is_valid: bool
    latency_ms: float
    raw_output: str
    confidence: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────
# Main Pipeline
# ─────────────────────────────────────────────────────────────

class TextToSQLPipeline:
    """
    End-to-end Text-to-SQL inference pipeline for fine-tuned CodeLlama-7B.
    """

    def __init__(
        self,
        model: AutoModelForCausalLM,
        tokenizer: AutoTokenizer,
        max_new_tokens: int = 256,
        temperature: float = 0.1,
        repetition_penalty: float = 1.1,
        max_schema_length: int = 1500,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.repetition_penalty = repetition_penalty
        self.max_schema_length = max_schema_length
        self._pp = SQLPostProcessor()

    @classmethod
    def from_pretrained(cls, model_path: str, load_in_4bit: bool = True, **kwargs) -> "TextToSQLPipeline":
        bnb_cfg = None
        if load_in_4bit:
            bnb_cfg = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
            )

        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        tokenizer.pad_token = tokenizer.eos_token

        model_kwargs: Dict = {"device_map": "auto", "torch_dtype": torch.float16, "trust_remote_code": True}
        if bnb_cfg:
            model_kwargs["quantization_config"] = bnb_cfg

        if (Path(model_path) / "adapter_config.json").exists():
            from peft import AutoPeftModelForCausalLM
            model = AutoPeftModelForCausalLM.from_pretrained(model_path, **model_kwargs)
        else:
            model = AutoModelForCausalLM.from_pretrained(model_path, **model_kwargs)

        model.eval()
        logger.info("Pipeline loaded", path=model_path)
        return cls(model=model, tokenizer=tokenizer, **kwargs)

    def _score_confidence(self, sql: str, question: str) -> float:
        score = 0.5
        up = sql.upper()
        if up.startswith("SELECT"):              score += 0.10
        if "FROM" in up:                         score += 0.10
        if len(sql) > 20:                        score += 0.10
        if len(sql) > 80:                        score += 0.10
        if sql.count("(") == sql.count(")"):     score += 0.05
        q_words = [w.lower() for w in question.split()[:5]]
        if any(w in sql.lower() for w in q_words): score += 0.05
        return min(round(score, 3), 1.0)

    def predict(self, schema: str, question: str) -> InferenceResult:
        start = time.perf_counter()
        if len(schema) > self.max_schema_length:
            schema = schema[:self.max_schema_length] + "\n-- (truncated)"

        prompt = build_inference_prompt(schema, question)
        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1900).to(self.model.device)

        try:
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    temperature=self.temperature,
                    do_sample=(self.temperature > 0),
                    repetition_penalty=self.repetition_penalty,
                    eos_token_id=self.tokenizer.eos_token_id,
                    pad_token_id=self.tokenizer.eos_token_id,
                )
            raw = self.tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            sql = self._pp.process(raw)
            is_safe  = self._pp.is_safe(sql)
            is_valid = self._pp.is_valid_select(sql)
            confidence = self._score_confidence(sql, question) if (is_safe and is_valid) else 0.0
        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            return InferenceResult(sql="", is_safe=False, is_valid=False,
                                   latency_ms=elapsed, raw_output="", error=str(exc))

        elapsed = (time.perf_counter() - start) * 1000
        return InferenceResult(
            sql=sql, is_safe=is_safe, is_valid=is_valid,
            latency_ms=round(elapsed, 1), raw_output=raw, confidence=confidence,
        )

    def predict_batch(self, items: List[Dict[str, str]]) -> List[InferenceResult]:
        return [self.predict(item["schema"], item["question"]) for item in items]


# ─────────────────────────────────────────────────────────────
# FastAPI Server
# ─────────────────────────────────────────────────────────────

def create_server(pipeline: TextToSQLPipeline):
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

    app = FastAPI(title="Text-to-SQL API", description="CodeLlama-7B fine-tuned on Spider+WikiSQL", version="1.0.0")

    class PredictRequest(BaseModel):
        schema_ddl: str
        question: str

    class BatchRequest(BaseModel):
        items: List[Dict[str, str]]

    @app.get("/health")
    def health():
        return {"status": "healthy", "model": "codellama-7b-text2sql"}

    @app.post("/predict")
    def predict(req: PredictRequest):
        result = pipeline.predict(schema=req.schema_ddl, question=req.question)
        if not result.is_safe:
            raise HTTPException(400, "Generated SQL failed safety check")
        return result.to_dict()

    @app.post("/predict/batch")
    def predict_batch(req: BatchRequest):
        results = pipeline.predict_batch(req.items)
        return {"results": [r.to_dict() for r in results]}

    return app


# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    import structlog
    structlog.configure(logger_factory=structlog.PrintLoggerFactory())

    parser = argparse.ArgumentParser()
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--serve",    action="store_true")
    parser.add_argument("--host",     default="0.0.0.0")
    parser.add_argument("--port",     type=int, default=9000)
    parser.add_argument("--question", default=None)
    parser.add_argument("--schema",   default=None)
    args = parser.parse_args()

    pipe = TextToSQLPipeline.from_pretrained(args.model_path)

    if args.serve:
        server = create_server(pipe)
        uvicorn.run(server, host=args.host, port=args.port)
    elif args.question and args.schema:
        r = pipe.predict(schema=args.schema, question=args.question)
        print(f"SQL        : {r.sql}")
        print(f"Confidence : {r.confidence}")
        print(f"Latency    : {r.latency_ms}ms")
        print(f"Safe       : {r.is_safe}")
    else:
        print("Use --serve for API server, or --question + --schema for single prediction.")
