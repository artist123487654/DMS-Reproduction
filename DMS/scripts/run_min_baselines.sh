#!/usr/bin/env bash
# Minimum：只跑 Baseline A / B（不含 DMS；DMS 用 run_min.sh）。
#   DETACH=1 bash scripts/run_min_baselines.sh --model qwen/qwen3-vl-8b-instruct
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 整段 a→b 一起后台，避免内层各自 detach 抢同一模拟器
if [[ "${DETACH:-0}" == "1" || "${DETACH:-}" == "true" || "${DETACH:-}" == "yes" ]]; then
  mkdir -p "${ROOT}/logs"
  stamp="$(date +%Y%m%d_%H%M%S)"
  log="${ROOT}/logs/run_min_baselines_${stamp}.log"
  pidf="${ROOT}/logs/run_min_baselines_${stamp}.pid"
  {
    echo "========== DMS detach (min baselines) =========="
    echo "time: $(date -Is)"
    echo "args: $*"
    echo "================================================"
  } >"${log}"
  DETACH=0 nohup bash "${SCRIPT_DIR}/run_min_baselines.sh" "$@" >>"${log}" 2>&1 </dev/null &
  echo $! >"${pidf}"
  disown $! 2>/dev/null || true
  echo "[detach] pid=$(cat "${pidf}")"
  echo "[detach] log=${log}"
  echo "[detach] 查看: tail -f ${log}"
  echo "[detach] 停止: kill \$(cat ${pidf})"
  exit 0
fi

TRIALS="${TRIALS:-5}"
SEED="${SEED:-30}"

for BACKEND in a b; do
  echo ""
  echo "########## Minimum baselines: ${BACKEND} ##########"
  BACKEND="${BACKEND}" TRIALS="${TRIALS}" SEED="${SEED}" \
    bash "${SCRIPT_DIR}/run_min.sh" "$@"
done

echo ""
echo "==== Baselines A/B finished（DMS 请单独: bash scripts/run_min.sh） ===="
