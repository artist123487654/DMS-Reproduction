#!/usr/bin/env bash
# Test 任务：只跑 1 个短任务 × 1 round，低成本验证全流程。
#   bash scripts/run_test.sh
#   BACKEND=a bash scripts/run_test.sh
#   TASK=MarkorCreateNote bash scripts/run_test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

BACKEND="${BACKEND:-dms}"
TRIALS="${TRIALS:-1}"
SEED="${SEED:-30}"

echo "==== Test | backend=${BACKEND} trials=${TRIALS} ===="

# 若指定 TASK，则覆盖默认 test 套件中的单任务
if [[ -n "${TASK:-}" ]]; then
  "${DMS_PYTHON}" runners/run_androidworld.py \
    --tasks "${TASK}" \
    --backend "${BACKEND}" \
    --trials "${TRIALS}" \
    --seed "${SEED}" \
    "$@"
else
  "${DMS_PYTHON}" runners/run_androidworld.py \
    --suite test \
    --backend "${BACKEND}" \
    --trials "${TRIALS}" \
    --seed "${SEED}" \
    "$@"
fi

echo ""
echo "Test 结束。请检查 results/ 下 aw_*_test_* 目录中的 task_results.json / round_metrics.json。"
