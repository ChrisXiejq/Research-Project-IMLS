#!/usr/bin/env bash
set -Eeuo pipefail

# Reporting-only B0 bridge.  This script never changes the Day 8 selection or
# retroactively substitutes calibrated B0 into the completed Day 10 matrix.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
DAY7_RESULTS="${DAY7_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1}"
DAY10_RESULTS="${DAY10_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day10/day10_formal_v1}"
B0_OFFLINE_RESULTS="${B0_OFFLINE_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day10_gaps/b0_offline_v1}"
B0_MODEL="${B0_MODEL:-${SCRIPT_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/l5kit_clusters_16.npy}"
BATCH_SIZE="${BATCH_SIZE:-16}"

for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" \
  "${DAY7_RESULTS}/val.jsonl" \
  "${DAY7_RESULTS}/test.jsonl" \
  "${DAY8_RESULTS}/DAY8_COMPLETE.json" \
  "${DAY8_RESULTS}/final_test_v1/day8_frozen_test_summary.json" \
  "${DAY10_RESULTS}/DAY10_COMPLETE.json" \
  "${DAY10_RESULTS}/day10_run_contract.json" \
  "${B0_MODEL}/saved_model.pb" \
  "${ANCHORS}"; do
  test -e "${required}" || { echo "Missing B0 offline input: ${required}" >&2; exit 2; }
done

mkdir -p "${B0_OFFLINE_RESULTS}"
exec > >(tee -a "${B0_OFFLINE_RESULTS}/b0_offline_runner.log") 2>&1

if "${PYTHON_BIN}" - "${B0_OFFLINE_RESULTS}/B0_OFFLINE_COMPLETE.json" <<'PY'
import json,sys
try: payload=json.load(open(sys.argv[1]))
except Exception: raise SystemExit(1)
raise SystemExit(0 if payload.get("status")=="pass" else 1)
PY
then
  echo "B0 frozen offline bridge already complete"
  cat "${B0_OFFLINE_RESULTS}/B0_OFFLINE_COMPLETE.json"
  exit 0
fi

LOCK="${B0_OFFLINE_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another B0 offline runner is active: PID $(cat "${LOCK}/pid")" >&2
    exit 3
  fi
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() { rm -f "${LOCK}/pid"; rmdir "${LOCK}" 2>/dev/null || true; }
trap cleanup EXIT

"${PYTHON_BIN}" -c 'import sys,tensorflow as tf; g=tf.config.list_physical_devices("GPU"); print("B0 offline GPUs:",g); sys.exit(0 if g else 3)'

"${PYTHON_BIN}" - "${SCRIPT_DIR}" "${B0_MODEL}" "${DAY10_RESULTS}/day10_run_contract.json" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from evaluate_multipath_model_on_dataset import artifact_hash
model=Path(sys.argv[2]).resolve(); contract=json.load(open(sys.argv[3]))
observed=artifact_hash(model).get("sha256_tree")
expected=contract["predictors"]["B0"]["model_sha256_tree"]
if observed != expected: raise SystemExit(f"Frozen B0 hash mismatch: {observed} != {expected}")
print("Frozen B0 hash:",observed)
PY

CALIBRATION="${B0_OFFLINE_RESULTS}/b0_validation_calibration.json"
VALIDATION="${B0_OFFLINE_RESULTS}/b0_validation_evaluation.json"
if [[ ! -e "${CALIBRATION}" && ! -e "${VALIDATION}" ]]; then
  "${PYTHON_BIN}" "${SCRIPT_DIR}/evaluate_multipath_model_on_dataset.py" \
    --merged_dir "${DAY7_RESULTS}" --split val --subset all \
    --model "${B0_MODEL}" --anchors "${ANCHORS}" --batch_size "${BATCH_SIZE}" \
    --fit-calibration --calibration-output-json "${CALIBRATION}" \
    --output_json "${VALIDATION}"
elif [[ -f "${CALIBRATION}" && ! -e "${VALIDATION}" ]]; then
  echo "Resume B0 validation evaluation from completed validation-only calibration"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/evaluate_multipath_model_on_dataset.py" \
    --merged_dir "${DAY7_RESULTS}" --split val --subset all \
    --model "${B0_MODEL}" --anchors "${ANCHORS}" --batch_size "${BATCH_SIZE}" \
    --calibration-json "${CALIBRATION}" --output_json "${VALIDATION}"
elif [[ ! -f "${CALIBRATION}" || ! -f "${VALIDATION}" ]]; then
  echo "Invalid B0 validation artifact state; existing files will not be overwritten" >&2
  exit 4
fi

"${PYTHON_BIN}" - "${CALIBRATION}" "${VALIDATION}" "${DAY10_RESULTS}/day10_run_contract.json" <<'PY'
import json,sys
c,v,d=(json.load(open(path)) for path in sys.argv[1:])
expected=d["predictors"]["B0"]["model_sha256_tree"]
valid=(c.get("fit_split")=="val" and c.get("model_artifact",{}).get("sha256_tree")==expected
 and v.get("status")=="pass" and v.get("split")=="val" and v.get("subset")=="all"
 and v.get("model_artifact",{}).get("sha256_tree")==expected
 and (v.get("calibration") or {}).get("parameters")==c.get("parameters"))
if not valid: raise SystemExit("Invalid frozen B0 validation/calibration artifacts")
PY

subsets=(all assertive reactive pre_response response_active)
for subset in "${subsets[@]}"; do
  output="${B0_OFFLINE_RESULTS}/b0_test_${subset}.json"
  if "${PYTHON_BIN}" - "${output}" "${subset}" "${CALIBRATION}" "${DAY10_RESULTS}/day10_run_contract.json" <<'PY'
import json,sys
try:
 p=json.load(open(sys.argv[1])); c=json.load(open(sys.argv[3])); d=json.load(open(sys.argv[4]))
 valid=(p.get("status") in ("pass","not_applicable") and p.get("split")=="test" and p.get("subset")==sys.argv[2]
  and p.get("calibration_fit_uses_test") is False
  and p.get("model_artifact",{}).get("sha256_tree")==d["predictors"]["B0"]["model_sha256_tree"]
  and (p.get("calibration") or {}).get("parameters")==c.get("parameters"))
except Exception: valid=False
raise SystemExit(0 if valid else 1)
PY
  then
    echo "skip verified B0 test subset=${subset}"
    continue
  fi
  if [[ -e "${output}" ]]; then
    echo "Invalid existing B0 output will not be overwritten: ${output}" >&2
    exit 5
  fi
  echo "[$(date --iso-8601=seconds)] evaluate frozen B0 test subset=${subset}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/evaluate_multipath_model_on_dataset.py" \
    --merged_dir "${DAY7_RESULTS}" --split test --subset "${subset}" \
    --model "${B0_MODEL}" --anchors "${ANCHORS}" --batch_size "${BATCH_SIZE}" \
    --calibration-json "${CALIBRATION}" --output_json "${output}"
done

SUMMARY="${B0_OFFLINE_RESULTS}/b0_frozen_offline_summary.json"
"${PYTHON_BIN}" "${SCRIPT_DIR}/summarize_b0_frozen_offline.py" \
  --results-dir "${B0_OFFLINE_RESULTS}" \
  --day8-test-summary "${DAY8_RESULTS}/final_test_v1/day8_frozen_test_summary.json" \
  --day10-contract "${DAY10_RESULTS}/day10_run_contract.json" \
  --output-json "${SUMMARY}"

"${PYTHON_BIN}" - "${SUMMARY}" "${B0_OFFLINE_RESULTS}/B0_OFFLINE_COMPLETE.json" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
source,output=map(Path,sys.argv[1:]); payload=json.loads(source.read_text())
if payload.get("status")!="pass" or payload.get("test_used_for_selection") is not False: raise SystemExit("B0 summary failed")
done={"schema_version":"b0_offline_complete_v1","status":"pass","test_used_for_selection":False,
      "closed_loop_selection_unchanged":payload["closed_loop_selection_unchanged"],
      "summary_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(done,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY

"${PYTHON_BIN}" "${SCRIPT_DIR}/package_b0_frozen_offline.py" \
  --results-dir "${B0_OFFLINE_RESULTS}" \
  --output "${B0_OFFLINE_RESULTS}/b0_frozen_offline_snapshot.tar.gz"

echo "[$(date --iso-8601=seconds)] B0 frozen offline bridge complete"
cat "${B0_OFFLINE_RESULTS}/B0_OFFLINE_COMPLETE.json"
