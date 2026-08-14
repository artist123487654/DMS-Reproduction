#!/usr/bin/env bash
# Preferred：覆盖全部真实 App，每 App 采 1–2 个任务，默认 5 rounds。
#   bash scripts/run_preferred.sh
#   BACKEND=a PER_APP=1 bash scripts/run_preferred.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${SCRIPT_DIR}/_common.sh"

BACKEND="${BACKEND:-dms}"
TRIALS="${TRIALS:-5}"
PER_APP="${PER_APP:-2}"
SEED="${SEED:-30}"

echo "==== Preferred suite | backend=${BACKEND} trials=${TRIALS} per_app=${PER_APP} ===="
"${DMS_PYTHON}" runners/run_androidworld.py \
  --suite preferred \
  --per_app "${PER_APP}" \
  --backend "${BACKEND}" \
  --trials "${TRIALS}" \
  --seed "${SEED}" \
  "$@"
