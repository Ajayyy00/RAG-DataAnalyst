#!/usr/bin/env bash
# ── Inference Server Launch Script ───────────────────────────────
# Usage: ./scripts/run_serve.sh --model-path outputs/merged-codellama-7b

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

MODEL_PATH="outputs/merged-codellama-7b-text2sql"
HOST="0.0.0.0"
PORT="9000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model-path) MODEL_PATH="$2"; shift 2 ;;
    --host)       HOST="$2";       shift 2 ;;
    --port)       PORT="$2";       shift 2 ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

export CUDA_VISIBLE_DEVICES=0
export TOKENIZERS_PARALLELISM=false

echo "================================================"
echo "  Text-to-SQL Inference Server"
echo "  Model : $MODEL_PATH"
echo "  URL   : http://$HOST:$PORT"
echo "================================================"

python inference/pipeline.py \
  --model-path "$MODEL_PATH" \
  --serve \
  --host "$HOST" \
  --port "$PORT"
