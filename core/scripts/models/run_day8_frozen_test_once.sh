#!/usr/bin/env bash
set -Eeuo pipefail

# Required environment:
#   DAY7_RESULTS=/.../day7_v2_merged_v1
#   DAY8_RESULTS=/.../day8_validation_v1
# Optional: PYTHON_BIN, ANCHORS, BATCH_SIZE

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/l5kit_clusters_16.npy}"
BATCH_SIZE="${BATCH_SIZE:-16}"

: "${DAY7_RESULTS:?Set DAY7_RESULTS to the completed Day 7 merge directory}"
: "${DAY8_RESULTS:?Set DAY8_RESULTS to the completed Day 8 validation directory}"

TEST_DIR="${DAY8_RESULTS}/final_test_v1"
mkdir -p "${TEST_DIR}"
LOG="${TEST_DIR}/day8_test_runner.log"
exec > >(tee -a "${LOG}") 2>&1

if "${PYTHON_BIN}" - "${TEST_DIR}/DAY8_TEST_COMPLETE.json" <<'PY'
import json, sys
try:
    payload = json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if payload.get("status") == "pass" else 1)
PY
then
  echo "Day 8 frozen test already completed; no test data will be accessed again"
  cat "${TEST_DIR}/DAY8_TEST_COMPLETE.json"
  exit 0
fi

LOCK="${TEST_DIR}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another Day 8 test runner is active: PID $(cat "${LOCK}/pid")"
    exit 2
  fi
  echo "Removing stale Day 8 test runner lock"
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
test -f "${DAY8_RESULTS}/DAY8_VALIDATION_COMPLETE.json"

SELECTION="${TEST_DIR}/DAY8_MODEL_SELECTION_FROZEN.json"
"${PYTHON_BIN}" "${SCRIPT_DIR}/freeze_day8_model_selection.py" \
  --results-dir "${DAY8_RESULTS}" \
  --output-json "${SELECTION}"

require_gpu() {
  "${PYTHON_BIN}" -c 'import sys, tensorflow as tf; devices=tf.config.list_physical_devices("GPU"); print("Day8 test GPU devices:", devices); sys.exit(0 if devices else 3)'
}

frozen_seed() {
  "${PYTHON_BIN}" - "${SELECTION}" "$1" <<'PY'
import json, sys
print(json.load(open(sys.argv[1]))["representatives_for_single_test_pass"][sys.argv[2]]["seed"])
PY
}

json_matches_freeze() {
  "${PYTHON_BIN}" - "$1" "$2" "$3" "${SELECTION}" <<'PY'
import json, sys
path, variant, subset, freeze_path = sys.argv[1:]
try:
    payload = json.load(open(path))
    freeze = json.load(open(freeze_path))
    frozen = freeze["representatives_for_single_test_pass"][variant]
    status_ok = payload.get("status") == "pass" or (
        payload.get("status") == "not_applicable"
        and subset in ("pre_response", "response_active")
        and int(payload.get("samples", -1)) == 0
    )
    valid = (
        status_ok
        and payload.get("evaluation_schema_version") == "multipath_accuracy_calibration_v2"
        and payload.get("split") == "test"
        and payload.get("subset") == subset
        and payload.get("calibration_fit_uses_test") is False
        and payload.get("model_artifact", {}).get("sha256_tree")
            == frozen["model"]["sha256_tree"]
        and payload.get("calibration", {}).get("fit_split") == "val"
        and payload.get("calibration", {}).get("parameters")
            == frozen["calibration_parameters"]
    )
except Exception:
    valid = False
raise SystemExit(0 if valid else 1)
PY
}

variants=(B1 B2-M B2-D T1 T2)
subsets=(all assertive reactive pre_response response_active)
for variant in "${variants[@]}"; do
  seed="$(frozen_seed "${variant}")"
  run_dir="${DAY8_RESULTS}/runs/${variant}/seed_${seed}"
  test_run_dir="${TEST_DIR}/${variant}/seed_${seed}"
  mkdir -p "${test_run_dir}"
  for subset in "${subsets[@]}"; do
    output="${test_run_dir}/test_${subset}.json"
    if json_matches_freeze "${output}" "${variant}" "${subset}"; then
      echo "[$(date --iso-8601=seconds)] skip verified ${variant} seed=${seed} test subset=${subset}"
      continue
    fi
    if [[ -e "${output}" ]]; then
      echo "Existing test output is invalid and will not be overwritten: ${output}" >&2
      echo "Preserve it for audit, move it aside manually, then rerun." >&2
      exit 4
    fi
    require_gpu
    echo "[$(date --iso-8601=seconds)] evaluate frozen ${variant} seed=${seed} test subset=${subset}"
    "${PYTHON_BIN}" "${SCRIPT_DIR}/evaluate_multipath_model_on_dataset.py" \
      --merged_dir "${DAY7_RESULTS}" \
      --split test \
      --subset "${subset}" \
      --model "${run_dir}/best_model" \
      --anchors "${ANCHORS}" \
      --batch_size "${BATCH_SIZE}" \
      --calibration-json "${run_dir}/calibration.json" \
      --output_json "${output}"
  done
done

SUMMARY="${TEST_DIR}/day8_frozen_test_summary.json"
"${PYTHON_BIN}" "${SCRIPT_DIR}/summarize_day8_frozen_test.py" \
  --results-dir "${DAY8_RESULTS}" \
  --test-dir "${TEST_DIR}" \
  --selection-json "${SELECTION}" \
  --output-json "${SUMMARY}"

"${PYTHON_BIN}" - "${SUMMARY}" "${SELECTION}" "${TEST_DIR}/DAY8_TEST_COMPLETE.json" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
summary_path, selection_path, output = map(Path, sys.argv[1:])
summary = json.loads(summary_path.read_text())
selection = json.loads(selection_path.read_text())
if summary.get("status") != "pass" or summary.get("test_used_for_selection") is not False:
    raise SystemExit("Frozen test summary failed")
payload = {
    "status": "pass",
    "test_accessed": True,
    "test_used_for_selection": False,
    "evaluated_frozen_representatives": 5,
    "closed_loop_selected_variant": selection["closed_loop_selected_variant"],
    "closed_loop_selected_seed": selection["closed_loop_selected_seed"],
    "selection_freeze_sha256": hashlib.sha256(selection_path.read_bytes()).hexdigest(),
    "test_summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
}
temporary = output.with_suffix(output.suffix + ".tmp")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
os.replace(temporary, output)
PY

SNAPSHOT="${TEST_DIR}/day8_frozen_test_snapshot.tar.gz"
"${PYTHON_BIN}" "${SCRIPT_DIR}/package_day8_test_snapshot.py" \
  --test-dir "${TEST_DIR}" \
  --output "${SNAPSHOT}"

"${PYTHON_BIN}" - "${DAY8_RESULTS}/DAY8_VALIDATION_COMPLETE.json" "${TEST_DIR}/DAY8_TEST_COMPLETE.json" "${SNAPSHOT}.json" "${DAY8_RESULTS}/DAY8_COMPLETE.json" <<'PY'
import json, os, sys
from pathlib import Path
validation_path, test_path, manifest_path, output = map(Path, sys.argv[1:])
validation = json.loads(validation_path.read_text())
test = json.loads(test_path.read_text())
manifest = json.loads(manifest_path.read_text())
if any(item.get("status") != "pass" for item in (validation, test, manifest)):
    raise SystemExit("Cannot complete Day 8: a stage did not pass")
payload = {
    "schema_version": "day8_complete_v1",
    "status": "pass",
    "validation_complete": True,
    "frozen_test_complete": True,
    "test_used_for_selection": False,
    "closed_loop_selected_variant": test["closed_loop_selected_variant"],
    "closed_loop_selected_seed": test["closed_loop_selected_seed"],
    "test_snapshot_sha256": manifest["archive_sha256"],
}
temporary = output.with_suffix(output.suffix + ".tmp")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
os.replace(temporary, output)
PY

echo "[$(date --iso-8601=seconds)] Day 8 complete"
cat "${DAY8_RESULTS}/DAY8_COMPLETE.json"
