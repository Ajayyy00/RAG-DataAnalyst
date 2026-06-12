#!/usr/bin/env bash
# ── Spider Evaluation Script ─────────────────────────────────────
# Usage: ./scripts/run_eval.sh --model-path outputs/final

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

MODEL_PATH="outputs/qlora-codellama-7b-text2sql/final"
SPIDER_DIR="data/spider"
OUTPUT_FILE="results/eval_$(date +%Y%m%d_%H%M%S).json"
MAX_SAMPLES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model-path)   MODEL_PATH="$2";   shift 2 ;;
    --spider-dir)   SPIDER_DIR="$2";   shift 2 ;;
    --output-file)  OUTPUT_FILE="$2";  shift 2 ;;
    --max-samples)  MAX_SAMPLES="$2";  shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

export CUDA_VISIBLE_DEVICES=0
export TOKENIZERS_PARALLELISM=false

mkdir -p results

echo "================================================"
echo "  Spider Evaluation"
echo "  Model  : $MODEL_PATH"
echo "  Spider : $SPIDER_DIR"
echo "  Output : $OUTPUT_FILE"
echo "================================================"

SAMPLES_ARG=""
if [ -n "$MAX_SAMPLES" ]; then
  SAMPLES_ARG="--max-samples $MAX_SAMPLES"
fi

python evaluation/eval_spider.py \
  --model-path "$MODEL_PATH" \
  --spider-dir "$SPIDER_DIR" \
  --output-file "$OUTPUT_FILE" \
  $SAMPLES_ARG

echo "Results saved to $OUTPUT_FILE"
