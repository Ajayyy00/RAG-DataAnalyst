#!/usr/bin/env bash
# ── Merge LoRA Adapters into Base Model ──────────────────────────
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && cd .. && pwd)"
cd "$ROOT_DIR"

ADAPTER_PATH="outputs/qlora-codellama-7b-text2sql/final"
OUTPUT_PATH="outputs/merged-codellama-7b-text2sql"
BASE_MODEL="codellama/CodeLlama-7b-hf"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --adapter-path) ADAPTER_PATH="$2"; shift 2 ;;
    --output-path)  OUTPUT_PATH="$2";  shift 2 ;;
    --base-model)   BASE_MODEL="$2";   shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

echo "Merging adapters from $ADAPTER_PATH into $OUTPUT_PATH"

python - <<'PYEOF'
import sys, torch
from pathlib import Path
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer

adapter_path = sys.argv[1] if len(sys.argv) > 1 else "outputs/qlora-codellama-7b-text2sql/final"
output_path  = sys.argv[2] if len(sys.argv) > 2 else "outputs/merged-codellama-7b-text2sql"

print(f"Loading adapter from {adapter_path}...")
model = AutoPeftModelForCausalLM.from_pretrained(
    adapter_path,
    device_map="auto",
    torch_dtype=torch.float16,
)
print("Merging and unloading...")
model = model.merge_and_unload()
model.save_pretrained(output_path)

tokenizer = AutoTokenizer.from_pretrained(adapter_path)
tokenizer.save_pretrained(output_path)
print(f"Merged model saved to {output_path}")
PYEOF

echo "Done! Merged model at: $OUTPUT_PATH"
