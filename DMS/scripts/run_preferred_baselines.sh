#!/usr/bin/env bash
# Preferred：依次跑 Baseline A / B / DMS。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIALS="${TRIALS:-5}"
PER_APP="${PER_APP:-2}"
SEED="${SEED:-30}"

for BACKEND in a b dms; do
  echo ""
  echo "########## Preferred baselines: ${BACKEND} ##########"
  BACKEND="${BACKEND}" TRIALS="${TRIALS}" PER_APP="${PER_APP}" SEED="${SEED}" \
    bash "${SCRIPT_DIR}/run_preferred.sh"
done

echo ""
echo "==== All Preferred baselines finished ===="
