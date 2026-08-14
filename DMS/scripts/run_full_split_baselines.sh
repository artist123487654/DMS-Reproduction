#!/usr/bin/env bash
# Full Split：依次跑 A / B / DMS（耗时长）。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIALS="${TRIALS:-5}"
SEED="${SEED:-30}"

for BACKEND in a b dms; do
  echo ""
  echo "########## Full Split baselines: ${BACKEND} ##########"
  BACKEND="${BACKEND}" TRIALS="${TRIALS}" SEED="${SEED}" \
    bash "${SCRIPT_DIR}/run_full_split.sh"
done

echo ""
echo "==== All Full Split baselines finished ===="
