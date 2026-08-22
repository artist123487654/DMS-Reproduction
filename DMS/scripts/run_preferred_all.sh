#!/usr/bin/env bash
# Preferred：顺序跑 DMS → B → A（共用一台模拟器，禁止并行）。
#   bash scripts/run_preferred_all.sh --model qwen/qwen3-vl-8b-instruct
#   DETACH=1 bash scripts/run_preferred_all.sh --model qwen/qwen3-vl-8b-instruct
# 可选：TRIALS=5 PER_APP=2 SEED=30 BACKENDS="dms b a"
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 整段 dms→b→a 一起后台，避免内层各自 detach 抢同一模拟器
if [[ "${DETACH:-0}" == "1" || "${DETACH:-}" == "true" || "${DETACH:-}" == "yes" ]]; then
  mkdir -p "${ROOT}/logs"
  stamp="$(date +%Y%m%d_%H%M%S)"
  log="${ROOT}/logs/run_preferred_all_${stamp}.log"
  pidf="${ROOT}/logs/run_preferred_all_${stamp}.pid"
  {
    echo "========== DMS detach (preferred all: dms→b→a) =========="
    echo "time: $(date -Is)"
    echo "args: $*"
    echo "========================================================="
  } >"${log}"
  DETACH=0 nohup bash "${SCRIPT_DIR}/run_preferred_all.sh" "$@" >>"${log}" 2>&1 </dev/null &
  echo $! >"${pidf}"
  disown $! 2>/dev/null || true
  echo "[detach] pid=$(cat "${pidf}")"
  echo "[detach] log=${log}"
  echo "[detach] 查看: tail -f ${log}"
  echo "[detach] 停止: kill \$(cat ${pidf})"
  exit 0
fi

TRIALS="${TRIALS:-5}"
PER_APP="${PER_APP:-2}"
SEED="${SEED:-30}"
# 空格分隔；默认三后端顺序执行
BACKENDS="${BACKENDS:-dms b a}"

echo "==== Preferred ALL | backends=[${BACKENDS}] trials=${TRIALS} per_app=${PER_APP} seed=${SEED} ===="

for BACKEND in ${BACKENDS}; do
  echo ""
  echo "########## Preferred: ${BACKEND} ##########"
  BACKEND="${BACKEND}" TRIALS="${TRIALS}" PER_APP="${PER_APP}" SEED="${SEED}" \
    bash "${SCRIPT_DIR}/run_preferred.sh" "$@"
done

echo ""
echo "==== Preferred ALL finished (dms→b→a) ===="
