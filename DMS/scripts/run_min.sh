#!/usr/bin/env bash
# Minimum：默认 5 个代表性任务 × 5 rounds。
#   bash scripts/run_min.sh
#   BACKEND=a bash scripts/run_min.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

BACKEND="${BACKEND:-dms}"
TRIALS="${TRIALS:-5}"
SEED="${SEED:-30}"

echo "==== Minimum suite | backend=${BACKEND} trials=${TRIALS} ===="
"${DMS_PYTHON}" runners/run_androidworld.py \
  --suite min \
  --backend "${BACKEND}" \
  --trials "${TRIALS}" \
  --seed "${SEED}" \
  "$@"
