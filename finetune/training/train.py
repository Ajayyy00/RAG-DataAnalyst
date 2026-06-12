"""
QLoRA Fine-Tuning Training Script
===================================
Fine-tunes CodeLlama-7B on Spider+WikiSQL using QLoRA (4-bit + LoRA)
for Text-to-SQL generation.

Usage:
    python training/train.py --config configs/qlora_config.yaml
    python training/train.py --config configs/qlora_config.yaml --resume-from outputs/checkpoint-500
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import torch
import yaml
from datasets import load_from_disk
from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForSeq2Seq,
    EarlyStoppingCallback,
    Trainer,
    TrainerCallback,
    TrainerControl,
    TrainerState,
    TrainingArguments,
)
import structlog

sys.path.insert(0, str(Path(__file__).parent.parent))
from data.prepare_dataset import build_dataset

logger = structlog.get_logger(__name__)


# ─────────────────────────────────────────────────────────────
# Training Progress Callback
# ─────────────────────────────────────────────────────────────

class SQLTrainingCallback(TrainerCallback):
    """Custom callback for logging and early stopping heuristics."""

    def __init__(self, patience: int = 5):
        self.patience = patience
        self.best_loss = float("inf")
        self.no_improve_steps = 0

    def on_log(self, args, state: TrainerState, control: TrainerControl, logs=None, **kwargs):
        if logs and "loss" in logs:
            logger.info(
                "Training step",
                step=state.global_step,
                loss=round(logs["loss"], 4),
                lr=logs.get("learning_rate", "N/A"),
                epoch=round(state.epoch or 0, 2),
            )

    def on_evaluate(self, args, state: TrainerState, control: TrainerControl, metrics=None, **kwargs):
        if metrics and "eval_loss" in metrics:
            eval_loss = metrics["eval_loss"]
            logger.info(
                "Evaluation",
                step=state.global_step,
                eval_loss=round(eval_loss, 4),
            )
            if eval_loss < self.best_loss:
                self.best_loss = eval_loss
                self.no_improve_steps = 0
            else:
                self.no_improve_steps += 1
                logger.warning(
                    "No improvement",
                    steps_without_improvement=self.no_improve_steps,
                    patience=self.patience,
                )


# ─────────────────────────────────────────────────────────────
# Model Setup
# ─────────────────────────────────────────────────────────────

def load_model_and_tokenizer(cfg: dict):
    """Load base model with 4-bit quantization and apply LoRA adapters."""
    model_name = cfg["model"]["base_model"]

    # ─ Tokenizer ──────────────────────────────────────────────
    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
        model_max_length=cfg["model"]["model_max_length"],
    )
    tokenizer.pad_token    = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # ─ 4-bit Quantization config ─────────────────────────────
    bnb_cfg = BitsAndBytesConfig(
        load_in_4bit=cfg["quantization"]["load_in_4bit"],
        bnb_4bit_quant_type=cfg["quantization"]["bnb_4bit_quant_type"],
        bnb_4bit_compute_dtype=getattr(
            torch, cfg["quantization"]["bnb_4bit_compute_dtype"]
        ),
        bnb_4bit_use_double_quant=cfg["quantization"]["bnb_4bit_use_double_quant"],
    )

    # ─ Base model ────────────────────────────────────────────
    logger.info("Loading base model", model=model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=bnb_cfg,
        device_map=cfg["model"]["device_map"],
        trust_remote_code=True,
        torch_dtype=getattr(torch, cfg["model"]["torch_dtype"]),
    )
    model.config.use_cache = False  # Required for gradient checkpointing
    model.config.pretraining_tp = 1

    # ─ Prepare for k-bit training ──────────────────────────
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=cfg["training"]["gradient_checkpointing"]
    )

    # ─ LoRA adapters ───────────────────────────────────────
    lora_cfg = LoraConfig(
        r=cfg["lora"]["r"],
        lora_alpha=cfg["lora"]["lora_alpha"],
        target_modules=cfg["lora"]["target_modules"],
        lora_dropout=cfg["lora"]["lora_dropout"],
        bias=cfg["lora"]["bias"],
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total     = sum(p.numel() for p in model.parameters())
    logger.info(
        "Model loaded",
        trainable_params=f"{trainable:,}",
        total_params=f"{total:,}",
        trainable_pct=f"{100 * trainable / total:.2f}%",
    )

    return model, tokenizer


# ─────────────────────────────────────────────────────────────
# Training Entry Point
# ─────────────────────────────────────────────────────────────

def train(cfg: dict, resume_from: str | None = None):
    model, tokenizer = load_model_and_tokenizer(cfg)

    # ─ Dataset ───────────────────────────────────────────────
    processed_path = Path("data/processed")
    if processed_path.exists():
        logger.info("Loading pre-processed dataset from disk")
        from datasets import load_from_disk
        dataset = load_from_disk(str(processed_path))
    else:
        logger.info("Building dataset from scratch")
        spider_dir  = Path(cfg["data"]["spider_path"])  if cfg["data"].get("spider_path")  else None
        wikisql_dir = Path(cfg["data"]["wikisql_path"]) if cfg["data"].get("wikisql_path") else None
        dataset = build_dataset(
            tokenizer=tokenizer,
            spider_dir=spider_dir,
            wikisql_dir=wikisql_dir,
            max_train_samples=cfg["data"].get("max_train_samples"),
            max_eval_samples=cfg["data"].get("max_eval_samples", 1000),
            max_length=cfg["model"]["model_max_length"],
        )
        dataset.save_to_disk(str(processed_path))
        logger.info("Dataset cached", path=str(processed_path))

    train_dataset = dataset["train"]
    eval_dataset  = dataset["validation"]

    # ─ Data collator ───────────────────────────────────────
    data_collator = DataCollatorForSeq2Seq(
        tokenizer=tokenizer,
        model=model,
        padding=True,
        pad_to_multiple_of=8,
        label_pad_token_id=-100,
    )

    # ─ Training arguments ────────────────────────────────
    tc = cfg["training"]
    training_args = TrainingArguments(
        output_dir=tc["output_dir"],
        num_train_epochs=tc["num_train_epochs"],
        per_device_train_batch_size=tc["per_device_train_batch_size"],
        per_device_eval_batch_size=tc["per_device_eval_batch_size"],
        gradient_accumulation_steps=tc["gradient_accumulation_steps"],
        gradient_checkpointing=tc["gradient_checkpointing"],
        optim=tc["optim"],
        learning_rate=tc["learning_rate"],
        weight_decay=tc["weight_decay"],
        lr_scheduler_type=tc["lr_scheduler_type"],
        warmup_ratio=tc["warmup_ratio"],
        max_grad_norm=tc["max_grad_norm"],
        fp16=tc["fp16"],
        bf16=tc["bf16"],
        group_by_length=tc["group_by_length"],
        save_strategy=tc["save_strategy"],
        save_steps=tc["save_steps"],
        evaluation_strategy=tc.get("eval_strategy", tc.get("evaluation_strategy", "steps")),
        eval_steps=tc["eval_steps"],
        logging_steps=tc["logging_steps"],
        load_best_model_at_end=tc["load_best_model_at_end"],
        metric_for_best_model=tc["metric_for_best_model"],
        report_to=tc["report_to"],
        dataloader_num_workers=tc["dataloader_num_workers"],
        remove_unused_columns=tc["remove_unused_columns"],
        save_total_limit=3,
        ddp_find_unused_parameters=False,
        push_to_hub=False,
    )

    # ─ Trainer ─────────────────────────────────────────────
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=tokenizer,
        data_collator=data_collator,
        callbacks=[
            SQLTrainingCallback(patience=5),
            EarlyStoppingCallback(early_stopping_patience=3),
        ],
    )

    # ─ Train ───────────────────────────────────────────────
    logger.info("Starting training", resume_from=resume_from)
    trainer.train(resume_from_checkpoint=resume_from)

    # ─ Save final model ──────────────────────────────────
    final_dir = Path(tc["output_dir"]) / "final"
    trainer.save_model(str(final_dir))
    tokenizer.save_pretrained(str(final_dir))
    logger.info("Training complete", saved_to=str(final_dir))

    # ─ Optionally merge LoRA adapters ──────────────────────
    if cfg.get("merging", {}).get("merge_adapters", False):
        logger.info("Merging LoRA adapters into base model")
        from peft import AutoPeftModelForCausalLM
        merged_model = AutoPeftModelForCausalLM.from_pretrained(
            str(final_dir),
            device_map="auto",
            torch_dtype=getattr(torch, cfg["model"]["torch_dtype"]),
        )
        merged_model = merged_model.merge_and_unload()
        merge_dir = cfg["merging"]["output_dir"]
        merged_model.save_pretrained(merge_dir)
        tokenizer.save_pretrained(merge_dir)
        logger.info("Merged model saved", path=merge_dir)

    return trainer


if __name__ == "__main__":
    import structlog
    structlog.configure(logger_factory=structlog.PrintLoggerFactory())

    parser = argparse.ArgumentParser(description="QLoRA Text-to-SQL Fine-Tuning")
    parser.add_argument("--config", required=True, help="Path to YAML config file")
    parser.add_argument("--resume-from", default=None, help="Checkpoint dir to resume from")
    args = parser.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f)

    train(cfg, resume_from=args.resume_from)
