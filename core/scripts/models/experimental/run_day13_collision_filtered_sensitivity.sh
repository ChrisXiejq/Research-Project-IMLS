#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DAY7_RESULTS="${DAY7_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day8/day8_validation_v1}"
DAY12_RESULTS="${DAY12_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day12/day12_evidence_freeze_v1}"
DAY13_RESULTS="${DAY13_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day13/day13_collision_filtered_v1}"
FILTERED_DAY7="${FILTERED_DAY7:-${DAY13_RESULTS}/filtered_day7}"
FILTERED_VALIDATION="${FILTERED_VALIDATION:-${DAY13_RESULTS}/filtered_validation}"

if [[ -n "${PYTHON_BIN:-}" ]]; then
  test -x "$PYTHON_BIN"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
else
  echo "No Python interpreter found; set PYTHON_BIN" >&2
  exit 2
fi

mkdir -p "$DAY13_RESULTS"
exec > >(tee -a "$DAY13_RESULTS/day13_runner.log") 2>&1

echo "[$(date -Iseconds)] Build conservative collision-rollout-filtered training dataset"
"$PYTHON_BIN" "$SCRIPT_DIR/experimental/prepare_day13_collision_filtered_dataset.py" \
  --day7-results "$DAY7_RESULTS" \
  --collision-audit "$DAY12_RESULTS/collision_attribution/day12_collision_window_audit.json" \
  --collision-rollouts "$DAY12_RESULTS/collision_attribution/day12_collision_rollouts.csv" \
  --output-dir "$FILTERED_DAY7"

echo "[$(date -Iseconds)] Run matched 5-variant x 3-seed validation-only matrix"
DAY7_RESULTS="$FILTERED_DAY7" \
DAY8_RESULTS="$FILTERED_VALIDATION" \
PYTHON_BIN="$PYTHON_BIN" \
bash "$SCRIPT_DIR/experimental/run_day8_train_and_validate.sh"

echo "[$(date -Iseconds)] Compare original and filtered validation matrices"
"$PYTHON_BIN" "$SCRIPT_DIR/experimental/analyze_day13_filtered_sensitivity.py" \
  --original-summary "$DAY8_RESULTS/day8_validation_summary.json" \
  --filtered-summary "$FILTERED_VALIDATION/day8_validation_summary.json" \
  --filter-audit "$FILTERED_DAY7/day13_filter_audit.json" \
  --output-dir "$DAY13_RESULTS/analysis"

cp "$DAY13_RESULTS/analysis/DAY13_FILTERED_SENSITIVITY_COMPLETE.json" "$DAY13_RESULTS/DAY13_COMPLETE.json"
echo "[$(date -Iseconds)] Day13 collision-filtered sensitivity complete; test split untouched"
cat "$DAY13_RESULTS/DAY13_COMPLETE.json"
