"""
Dataset Preparation Pipeline
==============================
Downloads, processes and tokenizes Spider + WikiSQL datasets
into a unified format for CodeLlama QLoRA fine-tuning.

Output format (instruction-following):
  ### Schema:
  {table definitions}

  ### Question:
  {natural language question}

  ### SQL:
  {gold SQL query}
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import datasets
from datasets import Dataset, DatasetDict, concatenate_datasets
from transformers import AutoTokenizer
import structlog

logger = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────
# Prompt templates
# ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert SQL query generator. Given a database schema and a natural language question, generate the correct SQL query. Output ONLY the SQL query with no explanation."""

def build_prompt(schema: str, question: str, sql: str = "", add_eos: bool = True) -> str:
    """Build the instruction-following prompt."""
    prompt = f"""<s>[INST] <<SYS>>
{SYSTEM_PROMPT}
<</SYS>>

### Database Schema:
{schema}

### Question:
{question} [/INST]

### SQL:
{sql}"""
    if add_eos:
        prompt += " </s>"
    return prompt


def build_inference_prompt(schema: str, question: str) -> str:
    """Prompt for inference (no SQL completion)."""
    return f"""<s>[INST] <<SYS>>
{SYSTEM_PROMPT}
<</SYS>>

### Database Schema:
{schema}

### Question:
{question} [/INST]

### SQL:
"""


# ─────────────────────────────────────────────────────────────
# Spider Schema Extractor
# ─────────────────────────────────────────────────────────────

class SpiderSchemaExtractor:
    """Extracts CREATE TABLE statements from Spider database files."""

    def __init__(self, db_root: Path):
        self.db_root = db_root
        self._cache: Dict[str, str] = {}

    def get_schema(self, db_id: str, max_tables: int = 10) -> str:
        if db_id in self._cache:
            return self._cache[db_id]

        db_path = self.db_root / db_id / f"{db_id}.sqlite"
        if not db_path.exists():
            return f"-- Database: {db_id} (schema unavailable)"

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = cursor.fetchall()
            conn.close()

            schema_parts = []
            for name, ddl in tables[:max_tables]:
                if ddl:
                    # Clean up the DDL
                    ddl = re.sub(r"\s+", " ", ddl.strip())
                    schema_parts.append(ddl)

            schema = "\n".join(schema_parts)
            self._cache[db_id] = schema
            return schema
        except Exception as e:
            logger.warning("Schema extraction failed", db_id=db_id, error=str(e))
            return f"-- Database: {db_id}"

    def get_schema_from_tables_json(self, db_id: str, tables_json: List[Dict]) -> str:
        """Build schema from tables.json (Spider format) when SQLite not available."""
        db_info = next((t for t in tables_json if t["db_id"] == db_id), None)
        if not db_info:
            return f"-- Database: {db_id}"

        schema_parts = []
        for i, table_name in enumerate(db_info["table_names_original"]):
            cols = [
                (col_name, db_info["column_types"][j])
                for j, (tab_idx, col_name) in enumerate(db_info["column_names_original"])
                if tab_idx == i
            ]
            col_defs = ", ".join(f"{name} {dtype.upper()}" for name, dtype in cols)
            schema_parts.append(f"CREATE TABLE {table_name} ({col_defs});")

        return "\n".join(schema_parts)


# ─────────────────────────────────────────────────────────────
# Spider Processor
# ─────────────────────────────────────────────────────────────

class SpiderProcessor:
    """Processes the Spider Text-to-SQL dataset."""

    HF_DATASET = "spider"

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir
        self.schema_extractor: Optional[SpiderSchemaExtractor] = None
        if data_dir and (data_dir / "database").exists():
            self.schema_extractor = SpiderSchemaExtractor(data_dir / "database")

    def load(self) -> DatasetDict:
        logger.info("Loading Spider dataset from HuggingFace Hub")
        ds = datasets.load_dataset(self.HF_DATASET, trust_remote_code=True)
        return ds

    def process_split(self, split: datasets.Dataset, tables_json: Optional[List] = None) -> List[Dict]:
        """Convert Spider examples to training format."""
        examples = []
        for item in split:
            db_id = item["db_id"]
            question = item["question"]
            sql = item["query"]

            # Get schema
            if self.schema_extractor:
                schema = self.schema_extractor.get_schema(db_id)
            elif tables_json:
                schema = self.schema_extractor.get_schema_from_tables_json(db_id, tables_json)
            else:
                schema = f"-- Database: {db_id}"

            prompt = build_prompt(schema=schema, question=question, sql=sql)
            examples.append({
                "text": prompt,
                "question": question,
                "sql": sql,
                "db_id": db_id,
                "schema": schema,
                "source": "spider",
            })

        logger.info("Spider split processed", count=len(examples))
        return examples

    def process(self) -> Tuple[List[Dict], List[Dict]]:
        ds = self.load()
        train = self.process_split(ds["train"])
        val   = self.process_split(ds["validation"])
        return train, val


# ─────────────────────────────────────────────────────────────
# WikiSQL Processor
# ─────────────────────────────────────────────────────────────

class WikiSQLProcessor:
    """Processes the WikiSQL dataset."""

    HF_DATASET = "wikisql"

    # WikiSQL aggregation map
    AGG_OPS  = ["", "MAX", "MIN", "COUNT", "SUM", "AVG"]
    COND_OPS = ["=", ">", "<"]

    def load(self) -> DatasetDict:
        logger.info("Loading WikiSQL dataset from HuggingFace Hub")
        return datasets.load_dataset(self.HF_DATASET, trust_remote_code=True)

    def _build_schema(self, table: Dict) -> str:
        """Convert WikiSQL table dict to CREATE TABLE statement."""
        col_defs = ", ".join(
            f"`{name}` TEXT"
            for name in table["header"]
        )
        return f"CREATE TABLE `{table.get('name', 'data')}` ({col_defs});"

    def _sql_from_struct(self, sql_struct: Dict, table: Dict) -> str:
        """Reconstruct SQL string from WikiSQL structured label."""
        try:
            headers = table["header"]
            sel_col = headers[sql_struct["sel"]]
            agg     = self.AGG_OPS[sql_struct["agg"]]

            if agg:
                select_clause = f"SELECT {agg}(`{sel_col}`)"
            else:
                select_clause = f"SELECT `{sel_col}`"

            table_name = table.get("name", "data")
            from_clause = f"FROM `{table_name}`"

            conds = sql_struct.get("conds", {"column_index": [], "operator_index": [], "condition": []})
            where_parts = []
            for col_idx, op_idx, val in zip(
                conds["column_index"],
                conds["operator_index"],
                conds["condition"],
            ):
                col  = headers[col_idx]
                op   = self.COND_OPS[op_idx]
                where_parts.append(f"`{col}` {op} '{val}'")

            sql = f"{select_clause} {from_clause}"
            if where_parts:
                sql += " WHERE " + " AND ".join(where_parts)
            return sql
        except (IndexError, KeyError, TypeError):
            return ""

    def process_split(self, split: datasets.Dataset) -> List[Dict]:
        examples = []
        for item in split:
            table    = item["table"]
            question = item["question"]
            sql      = self._sql_from_struct(item["sql"], table)

            if not sql:
                continue

            schema = self._build_schema(table)
            prompt = build_prompt(schema=schema, question=question, sql=sql)
            examples.append({
                "text": prompt,
                "question": question,
                "sql": sql,
                "db_id": table.get("id", "wikisql"),
                "schema": schema,
                "source": "wikisql",
            })

        logger.info("WikiSQL split processed", count=len(examples))
        return examples

    def process(self) -> Tuple[List[Dict], List[Dict]]:
        ds = self.load()
        train = self.process_split(ds["train"])
        val   = self.process_split(ds["validation"])
        return train, val


# ─────────────────────────────────────────────────────────────
# Tokenization
# ─────────────────────────────────────────────────────────────

def tokenize_dataset(
    examples: List[Dict],
    tokenizer: AutoTokenizer,
    max_length: int = 2048,
) -> Dataset:
    """Tokenize examples for causal LM training."""
    texts = [ex["text"] for ex in examples]

    def tokenize_fn(batch):
        encoded = tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_length,
            padding=False,
            return_tensors=None,
        )
        # Labels = input_ids (causal LM)
        encoded["labels"] = encoded["input_ids"].copy()
        return encoded

    raw_ds = Dataset.from_list(examples)
    tokenized = raw_ds.map(
        tokenize_fn,
        batched=True,
        remove_columns=[c for c in raw_ds.column_names if c != "text"],
        desc="Tokenizing",
    )
    return tokenized


# ─────────────────────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────────────────────

def build_dataset(
    tokenizer: AutoTokenizer,
    spider_dir: Optional[Path] = None,
    wikisql_dir: Optional[Path] = None,
    max_train_samples: Optional[int] = None,
    max_eval_samples: Optional[int] = None,
    max_length: int = 2048,
    seed: int = 42,
) -> DatasetDict:
    """
    Build the combined Spider + WikiSQL training dataset.

    Returns a DatasetDict with 'train' and 'validation' splits.
    """
    train_examples: List[Dict] = []
    val_examples:   List[Dict] = []

    # ── Spider ────────────────────────────────────────────────
    spider = SpiderProcessor(data_dir=spider_dir)
    sp_train, sp_val = spider.process()
    train_examples.extend(sp_train)
    val_examples.extend(sp_val)

    # ── WikiSQL ───────────────────────────────────────────────
    wikisql = WikiSQLProcessor()
    wk_train, wk_val = wikisql.process()
    train_examples.extend(wk_train)
    # WikiSQL val is huge — cap it
    val_examples.extend(wk_val[:2000])

    # ── Shuffle ───────────────────────────────────────────────
    import random
    rng = random.Random(seed)
    rng.shuffle(train_examples)
    rng.shuffle(val_examples)

    if max_train_samples:
        train_examples = train_examples[:max_train_samples]
    if max_eval_samples:
        val_examples = val_examples[:max_eval_samples]

    logger.info(
        "Dataset built",
        train_size=len(train_examples),
        val_size=len(val_examples),
    )

    # ── Tokenize ──────────────────────────────────────────────
    train_ds = tokenize_dataset(train_examples, tokenizer, max_length)
    val_ds   = tokenize_dataset(val_examples,   tokenizer, max_length)

    return DatasetDict({"train": train_ds, "validation": val_ds})


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Prepare Text-to-SQL dataset")
    parser.add_argument("--model",       default="codellama/CodeLlama-7b-hf")
    parser.add_argument("--output-dir",  default="data/processed")
    parser.add_argument("--spider-dir",  default=None)
    parser.add_argument("--wikisql-dir", default=None)
    parser.add_argument("--max-train",   type=int, default=None)
    parser.add_argument("--max-eval",    type=int, default=1000)
    args = parser.parse_args()

    import structlog
    structlog.configure(logger_factory=structlog.PrintLoggerFactory())

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    ds = build_dataset(
        tokenizer=tokenizer,
        spider_dir=Path(args.spider_dir) if args.spider_dir else None,
        wikisql_dir=Path(args.wikisql_dir) if args.wikisql_dir else None,
        max_train_samples=args.max_train,
        max_eval_samples=args.max_eval,
    )

    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ds.save_to_disk(str(output))
    print(f"Dataset saved to {output}")
    print(f"  Train: {len(ds['train'])} examples")
    print(f"  Val:   {len(ds['validation'])} examples")
