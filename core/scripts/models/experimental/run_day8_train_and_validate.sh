#!/usr/bin/env bash
set -Eeuo pipefail

# Required environment:
#   DAY7_RESULTS=/.../day7_v2_merged_v1
#   DAY8_RESULTS=/.../day8_validation_v1
# Optional: PYTHON_BIN, BASE_MODEL, ANCHORS, EPOCHS, BATCH_SIZE, LEARNING_RATE, PATIENCE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
BASE_MODEL="${BASE_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/assets/l5kit_clusters_16.npy}"
EPOCHS="${EPOCHS:-20}"
BATCH_SIZE="${BATCH_SIZE:-16}"
LEARNING_RATE="${LEARNING_RATE:-0.0001}"
PATIENCE="${PATIENCE:-5}"

: "${DAY7_RESULTS:?Set DAY7_RESULTS to the completed Day 7 merge directory}"
: "${DAY8_RESULTS:?Set DAY8_RESULTS to a new Day 8 result directory}"

mkdir -p "${DAY8_RESULTS}/runs"
LOG="${DAY8_RESULTS}/day8_runner.log"
exec > >(tee -a "${LOG}") 2>&1

LOCK="${DAY8_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another Day 8 runner is active: PID $(cat "${LOCK}/pid")"
    exit 2
  fi
  echo "Removing stale Day 8 runner lock"
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() {
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}" 2>/dev/null || true
}
trap cleanup EXIT

test -f "${DAY7_RESULTS}/DAY7_COMPLETE.json"
test -f "${DAY7_RESULTS}/DAY7_MODEL_IMPLEMENTATION_COMPLETE.json"

require_gpu() {
  "${PYTHON_BIN}" -c 'import sys, tensorflow as tf; devices=tf.config.list_physical_devices("GPU"); print("Day8 GPU devices:", devices); sys.exit(0 if devices else 3)'
}

"${PYTHON_BIN}" - "${DAY8_RESULTS}/day8_run_contract.json" <<PY
import json, os, sys
from pathlib import Path
path = Path(sys.argv[1])
contract = {
    "schema_version": "day8_validation_runner_v1",
    "day7_results": str(Path("${DAY7_RESULTS}").resolve()),
    "base_model": str(Path("${BASE_MODEL}").resolve()),
    "anchors": str(Path("${ANCHORS}").resolve()),
    "variants": ["B1", "B2-M", "B2-D", "T1", "T2"],
    "seeds": [11, 23, 37],
    "epochs": int("${EPOCHS}"),
    "batch_size": int("${BATCH_SIZE}"),
    "learning_rate": float("${LEARNING_RATE}"),
    "patience": int("${PATIENCE}"),
    "selection_data": "validation_only",
    "test_accessed": False,
}
if path.exists() and json.loads(path.read_text()) != contract:
    raise SystemExit(f"Day 8 runner contract drift: {path}")
temporary = path.with_suffix(path.suffix + ".tmp")
temporary.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
os.replace(temporary, path)
PY

json_pass() {
  "${PYTHON_BIN}" - "$1" <<'PY'
import json, sys
try:
    payload = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(1)
if payload.get("evaluation_schema_version") != "multipath_accuracy_calibration_v2":
    raise SystemExit(1)
raise SystemExit(0 if payload.get("status") in ("pass", "not_applicable") else 1)
PY
}

preflight_dir="${DAY8_RESULTS}/preflight/T2_seed_11"
mkdir -p "${preflight_dir}"
if ! json_pass "${preflight_dir}/validation_all.json"; then
  require_gpu
  echo "[$(date --iso-8601=seconds)] Day 8 TensorFlow preflight"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/train_prediction_model_v2_day8.py" \
    --merged-dir "${DAY7_RESULTS}" \
    --base-model "${BASE_MODEL}" \
    --anchors "${ANCHORS}" \
    --variant T2 \
    --seed 11 \
    --output-dir "${preflight_dir}" \
    --epochs 1 \
    --batch-size 8 \
    --learning-rate "${LEARNING_RATE}" \
    --patience 1 \
    --max-train-samples 32 \
    --max-val-samples 16
  require_gpu
  "${PYTHON_BIN}" "${SCRIPT_DIR}/training/evaluate_multipath_model_on_dataset.py" \
    --merged_dir "${DAY7_RESULTS}" \
    --split val \
    --subset all \
    --model "${preflight_dir}/best_model" \
    --anchors "${ANCHORS}" \
    --batch_size 8 \
    --max_samples 8 \
    --fit-calibration \
    --calibration-output-json "${preflight_dir}/calibration.json" \
    --output_json "${preflight_dir}/validation_all.json"
fi

variants=(B1 B2-M B2-D T1 T2)
seeds=(11 23 37)
subsets=(assertive reactive pre_response response_active)

for variant in "${variants[@]}"; do
  for seed in "${seeds[@]}"; do
    run_dir="${DAY8_RESULTS}/runs/${variant}/seed_${seed}"
    mkdir -p "${run_dir}"
    require_gpu
    echo "[$(date --iso-8601=seconds)] train ${variant} seed=${seed}"
    "${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/train_prediction_model_v2_day8.py" \
      --merged-dir "${DAY7_RESULTS}" \
      --base-model "${BASE_MODEL}" \
      --anchors "${ANCHORS}" \
      --variant "${variant}" \
      --seed "${seed}" \
      --output-dir "${run_dir}" \
      --epochs "${EPOCHS}" \
      --batch-size "${BATCH_SIZE}" \
      --learning-rate "${LEARNING_RATE}" \
      --patience "${PATIENCE}"

    if ! json_pass "${run_dir}/validation_all.json"; then
      require_gpu
      echo "[$(date --iso-8601=seconds)] validate/calibrate ${variant} seed=${seed} subset=all"
      "${PYTHON_BIN}" "${SCRIPT_DIR}/training/evaluate_multipath_model_on_dataset.py" \
        --merged_dir "${DAY7_RESULTS}" \
        --split val \
        --subset all \
        --model "${run_dir}/best_model" \
        --anchors "${ANCHORS}" \
        --batch_size "${BATCH_SIZE}" \
        --fit-calibration \
        --calibration-output-json "${run_dir}/calibration.json" \
        --output_json "${run_dir}/validation_all.json"
    fi

    for subset in "${subsets[@]}"; do
      if ! json_pass "${run_dir}/validation_${subset}.json"; then
        require_gpu
        echo "[$(date --iso-8601=seconds)] validate ${variant} seed=${seed} subset=${subset}"
        "${PYTHON_BIN}" "${SCRIPT_DIR}/training/evaluate_multipath_model_on_dataset.py" \
          --merged_dir "${DAY7_RESULTS}" \
          --split val \
          --subset "${subset}" \
          --model "${run_dir}/best_model" \
          --anchors "${ANCHORS}" \
          --batch_size "${BATCH_SIZE}" \
          --calibration-json "${run_dir}/calibration.json" \
          --output_json "${run_dir}/validation_${subset}.json"
      fi
    done
  done
done

SUMMARY="${DAY8_RESULTS}/day8_validation_summary.json"
"${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/summarize_day8_validation.py" \
  --results-dir "${DAY8_RESULTS}" \
  --output-json "${SUMMARY}"

"${PYTHON_BIN}" - "${SUMMARY}" "${DAY8_RESULTS}/DAY8_VALIDATION_COMPLETE.json" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
source, output = map(Path, sys.argv[1:])
payload = json.loads(source.read_text())
if payload.get("status") != "pass" or payload.get("test_accessed") is not False:
    raise SystemExit("Validation summary did not pass the no-test gate")
completion = {
    "status": "pass",
    "observed_runs": payload["observed_runs"],
    "provisional_selected_variant": payload["provisional_selected_variant"],
    "provisional_representative_seed": payload["provisional_representative_seed"],
    "test_accessed": False,
    "validation_summary": str(source.resolve()),
    "validation_summary_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
}
temporary = output.with_suffix(output.suffix + ".tmp")
temporary.write_text(json.dumps(completion, indent=2, sort_keys=True) + "\n")
os.replace(temporary, output)
PY

"${PYTHON_BIN}" "${SCRIPT_DIR}/experimental/package_day8_validation_snapshot.py" \
  --results-dir "${DAY8_RESULTS}" \
  --output "${DAY8_RESULTS}/day8_validation_snapshot.tar.gz"

echo "[$(date --iso-8601=seconds)] Day 8 validation stage complete; test split remains untouched"
cat "${DAY8_RESULTS}/DAY8_VALIDATION_COMPLETE.json"
