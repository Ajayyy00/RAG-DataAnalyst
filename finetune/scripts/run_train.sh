#!/usr/bin/env bash
# ── QLoRA Training Launch Script ─────────────────────────────────
# Usage: ./scripts/run_train.sh [--resume CHECKPOINT_DIR]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

# Defaults
CONFIG="configs/qlora_config.yaml"
RESUME=""
GPUS="0"

# Parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config)   CONFIG="$2";  shift 2 ;;
    --resume)   RESUME="$2"; shift 2 ;;
    --gpus)     GPUS="$2";   shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

export CUDA_VISIBLE_DEVICES="$GPUS"
export TOKENIZERS_PARALLELISM=false
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

echo "================================================"
echo "  Text-to-SQL QLoRA Training"
echo "  Config : $CONFIG"
echo "  GPUs   : $GPUS"
echo "  Resume : ${RESUME:-none}"
echo "================================================"

RESUME_ARG=""
if [ -n "$RESUME" ]; then
  RESUME_ARG="--resume-from $RESUME"
fi

# Prepare data if not already done
if [ ! -d "data/processed" ]; then
  echo ">> Preparing dataset..."
  python data/prepare_dataset.py \
    --model codellama/CodeLlama-7b-hf \
    --output-dir data/processed
  echo ">> Dataset ready."
fi

# Launch training
python training/train.py \
  --config "$CONFIG" \
  $RESUME_ARG

echo "================================================"
echo "  Training complete!"
echo "================================================"
