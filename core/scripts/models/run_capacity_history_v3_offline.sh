#!/usr/bin/env bash
set -Eeuo pipefail

# Full GPU-server offline workflow. Every phase is completion-marker driven and
# rerunnable; fresh sets are not passed to any command until selection freezes.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
V3_ROOT="${V3_ROOT:-${CORE_DIR}/results/capacity_history_v3}"
MERGED_DIR="${MERGED_DIR:?Set MERGED_DIR to the sealed groups-1--45 train/validation dataset}"
BASE_MODEL="${BASE_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/l5kit_clusters_16.npy}"
GENERAL_TEST="${GENERAL_TEST:-${V3_ROOT}/general_test/sealed}"
INTERACTION_CHALLENGE="${INTERACTION_CHALLENGE:-${V3_ROOT}/interaction_challenge/sealed}"
RUN_ROOT="${V3_ROOT}/training"
SELECTION_ROOT="${V3_ROOT}/selection"
CALIBRATION_ROOT="${V3_ROOT}/calibration"
LATENCY_ROOT="${V3_ROOT}/latency"
EVALUATION_ROOT="${V3_ROOT}/fresh_evaluation"

mkdir -p "${SELECTION_ROOT}" "${CALIBRATION_ROOT}" "${LATENCY_ROOT}" "${EVALUATION_ROOT}"
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"

MERGED_DIR="${MERGED_DIR}" BASE_MODEL="${BASE_MODEL}" ANCHORS="${ANCHORS}" \
  V3_ROOT="${V3_ROOT}" PYTHON_BIN="${PYTHON_BIN}" \
  bash "${SCRIPT_DIR}/run_capacity_history_v3_training.sh" execute

INITIAL_SELECTION="${SELECTION_ROOT}/initial_selection.json"
INITIAL_CONVERGENCE="${SELECTION_ROOT}/initial_convergence.json"
FRACTION_SELECTION="${SELECTION_ROOT}/fraction_selection.json"
INITIAL_FRACTION_CONVERGENCE="${SELECTION_ROOT}/initial_fraction_convergence.json"
"${PYTHON_BIN}" "${SCRIPT_DIR}/capacity_study_v3_pipeline.py" select \
  --training-root "${RUN_ROOT}" \
  --selection-output "${INITIAL_SELECTION}" \
  --convergence-output "${INITIAL_CONVERGENCE}" \
  --validation-rows-output "${SELECTION_ROOT}/initial_validation_rows.json" \
  --fraction-selection-output "${FRACTION_SELECTION}" \
  --fraction-convergence-output "${INITIAL_FRACTION_CONVERGENCE}" \
  --fraction-validation-rows-output "${SELECTION_ROOT}/fraction_validation_rows.json"

"${PYTHON_BIN}" "${SCRIPT_DIR}/capacity_study_v3_pipeline.py" extensions \
  --convergence "${INITIAL_CONVERGENCE}" --merged-dir "${MERGED_DIR}" \
  --base-model "${BASE_MODEL}" --anchors "${ANCHORS}" \
  --output-root "${RUN_ROOT}" --python-bin "${PYTHON_BIN}" \
  --plan-output "${SELECTION_ROOT}/extension_execution_plan.json" --execute

"${PYTHON_BIN}" "${SCRIPT_DIR}/capacity_study_v3_pipeline.py" extensions \
  --convergence "${INITIAL_FRACTION_CONVERGENCE}" --merged-dir "${MERGED_DIR}" \
  --base-model "${BASE_MODEL}" --anchors "${ANCHORS}" \
  --output-root "${RUN_ROOT}" --python-bin "${PYTHON_BIN}" \
  --plan-output "${SELECTION_ROOT}/fraction_extension_execution_plan.json" --execute

FINAL_SELECTION="${SELECTION_ROOT}/final_selection.json"
FINAL_CONVERGENCE="${SELECTION_ROOT}/final_convergence.json"
FINAL_FRACTION_CONVERGENCE="${SELECTION_ROOT}/final_fraction_convergence.json"
"${PYTHON_BIN}" "${SCRIPT_DIR}/capacity_study_v3_pipeline.py" select \
  --training-root "${RUN_ROOT}" --extension-root "${RUN_ROOT}" \
  --selection-output "${FINAL_SELECTION}" \
  --convergence-output "${FINAL_CONVERGENCE}" \
  --validation-rows-output "${SELECTION_ROOT}/final_validation_rows.json" \
  --fraction-selection-output "${FRACTION_SELECTION}" \
  --fraction-convergence-output "${FINAL_FRACTION_CONVERGENCE}" \
  --fraction-validation-rows-output "${SELECTION_ROOT}/fraction_validation_rows.json"
"${PYTHON_BIN}" - "${FINAL_CONVERGENCE}" "${FINAL_FRACTION_CONVERGENCE}" <<'PY'
import json,sys
for path in sys.argv[1:]:
    value=json.load(open(path))
    if value.get("status") != "pass" or not value.get("fresh_test_access_allowed"):
        raise SystemExit(f"fresh evaluation remains blocked by convergence in {path}: {value.get('status')}")
PY

"${PYTHON_BIN}" "${SCRIPT_DIR}/capacity_study_v3_pipeline.py" calibrate \
  --selection "${FINAL_SELECTION}" --fraction-selection "${FRACTION_SELECTION}" \
  --training-root "${RUN_ROOT}" --calibration-root "${CALIBRATION_ROOT}" \
  --latency-root "${LATENCY_ROOT}" --merged-dir "${MERGED_DIR}" \
  --anchors "${ANCHORS}" --python-bin "${PYTHON_BIN}" \
  --plan-output "${SELECTION_ROOT}/calibration_latency_plan.json" --execute

DATA_PROVENANCE="${SELECTION_ROOT}/training_data_provenance.json"
"${PYTHON_BIN}" - "${MERGED_DIR}" "${DATA_PROVENANCE}" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
root,output=map(Path,sys.argv[1:])
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
payload={"schema_version":"capacity_history_training_data_provenance_v3","status":"pass","training_groups":list(range(1,41)),"validation_groups":list(range(41,46)),"fresh_groups_accessed":False,"train_jsonl_sha256":digest(root/"train.jsonl"),"val_jsonl_sha256":digest(root/"val.jsonl"),"merged_dir":str(root.resolve())}
temporary=output.with_suffix(".tmp"); temporary.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n"); os.replace(temporary,output)
PY
SELECTION_FREEZE="${SELECTION_ROOT}/SELECTION_FREEZE.json"
"${PYTHON_BIN}" "${SCRIPT_DIR}/capacity_study_v3_pipeline.py" freeze \
  --selection "${FINAL_SELECTION}" --fraction-selection "${FRACTION_SELECTION}" \
  --fraction-convergence "${FINAL_FRACTION_CONVERGENCE}" \
  --convergence "${FINAL_CONVERGENCE}" --training-root "${RUN_ROOT}" \
  --calibration-root "${CALIBRATION_ROOT}" --latency-root "${LATENCY_ROOT}" \
  --data-provenance "${DATA_PROVENANCE}" \
  --source-revision "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
  --output "${SELECTION_FREEZE}"

for required in "${GENERAL_TEST}/FRESH_DATASET_COMPLETE.json" \
  "${INTERACTION_CHALLENGE}/FRESH_DATASET_COMPLETE.json"; do
  test -f "${required}" || { echo "Fresh set is not sealed: ${required}" >&2; exit 5; }
done
"${PYTHON_BIN}" "${SCRIPT_DIR}/capacity_study_v3_pipeline.py" fresh-evaluate \
  --freeze "${SELECTION_FREEZE}" --training-root "${RUN_ROOT}" \
  --calibration-root "${CALIBRATION_ROOT}" --general-test "${GENERAL_TEST}" \
  --interaction-challenge "${INTERACTION_CHALLENGE}" \
  --output-root "${EVALUATION_ROOT}" --anchors "${ANCHORS}" \
  --python-bin "${PYTHON_BIN}" \
  --plan-output "${SELECTION_ROOT}/fresh_evaluation_plan.json" --execute

"${PYTHON_BIN}" "${SCRIPT_DIR}/capacity_study_v3_synthesis.py" \
  --freeze "${SELECTION_FREEZE}" \
  --evaluation-plan "${SELECTION_ROOT}/fresh_evaluation_plan.json" \
  --output "${EVALUATION_ROOT}/OFFLINE_SYNTHESIS.json"

echo "V3 offline study execution complete; synthesis may now consume ${EVALUATION_ROOT}"
