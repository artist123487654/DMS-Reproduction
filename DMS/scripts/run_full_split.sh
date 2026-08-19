#!/usr/bin/env bash
# Full Split：AndroidWorld 完整任务集（约 116）。
#   bash scripts/run_full_split.sh
#   DETACH=1 bash scripts/run_full_split.sh --model qwen/qwen3-vl-8b-instruct
#   BACKEND=b TRIALS=5 bash scripts/run_full_split.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

BACKEND="${BACKEND:-dms}"
TRIALS="${TRIALS:-5}"
SEED="${SEED:-30}"

echo "==== Full Split (android_world) | backend=${BACKEND} trials=${TRIALS} ===="
dms_exec "${DMS_PYTHON}" runners/run_androidworld.py \
  --suite full \
  --backend "${BACKEND}" \
  --trials "${TRIALS}" \
  --seed "${SEED}" \
  "$@"
