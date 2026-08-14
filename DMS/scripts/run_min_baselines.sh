#!/usr/bin/env bash
# Minimum：依次跑 a / b / dms。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRIALS="${TRIALS:-5}"
SEED="${SEED:-30}"

for BACKEND in a b dms; do
  echo ""
  echo "########## Minimum baselines: ${BACKEND} ##########"
  BACKEND="${BACKEND}" TRIALS="${TRIALS}" SEED="${SEED}" \
    bash "${SCRIPT_DIR}/run_min.sh"
done

echo ""
echo "==== All Minimum baselines finished ===="
