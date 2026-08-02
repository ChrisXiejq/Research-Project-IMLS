#!/usr/bin/env bash
set -Eeuo pipefail

# Frozen, post-selection T1/T2 diagnostic.  It neither trains nor refits calibration.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python}"
DAY7_RESULTS="${DAY7_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day8/day8_validation_v1}"
ABLATION_RESULTS="${ABLATION_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day10_gaps/context_ablation_v1}"
ANCHORS="${ANCHORS:-${SCRIPT_DIR}/l5kit_clusters_16.npy}"
BATCH_SIZE="${BATCH_SIZE:-16}"
ABLATION_SEED="${ABLATION_SEED:-20260802}"
SELECTION="${DAY8_RESULTS}/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json"
DAY8_SUMMARY="${DAY8_RESULTS}/final_test_v1/day8_frozen_test_summary.json"

for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" "${DAY7_RESULTS}/test.jsonl" \
  "${DAY8_RESULTS}/DAY8_COMPLETE.json" "${SELECTION}" "${DAY8_SUMMARY}" "${ANCHORS}"; do
  test -e "${required}" || { echo "Missing context-ablation input: ${required}" >&2; exit 2; }
done

mkdir -p "${ABLATION_RESULTS}"
exec > >(tee -a "${ABLATION_RESULTS}/context_ablation_runner.log") 2>&1

if "${PYTHON_BIN}" - "${ABLATION_RESULTS}/CONTEXT_ABLATION_COMPLETE.json" <<'PY'
import json,sys
try: payload=json.load(open(sys.argv[1]))
except Exception: raise SystemExit(1)
raise SystemExit(0 if payload.get("status")=="pass" else 1)
PY
then
  echo "Interaction-context ablation already complete"
  cat "${ABLATION_RESULTS}/CONTEXT_ABLATION_COMPLETE.json"
  exit 0
fi

LOCK="${ABLATION_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another context-ablation runner is active: PID $(cat "${LOCK}/pid")" >&2
    exit 3
  fi
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() { rm -f "${LOCK}/pid"; rmdir "${LOCK}" 2>/dev/null || true; }
trap cleanup EXIT

"${PYTHON_BIN}" -c 'import sys,tensorflow as tf; g=tf.config.list_physical_devices("GPU"); print("Context-ablation GPUs:",g); sys.exit(0 if g else 3)'

variants=(T1 T2)
modes=(zero shuffle)
subsets=(all assertive reactive pre_response response_active)
for variant in "${variants[@]}"; do
  seed="$("${PYTHON_BIN}" - "${SELECTION}" "${variant}" <<'PY'
import json,sys
p=json.load(open(sys.argv[1])); print(int(p["representatives_for_single_test_pass"][sys.argv[2]]["seed"]))
PY
)"
  model="${DAY8_RESULTS}/runs/${variant}/seed_${seed}/best_model"
  calibration="${DAY8_RESULTS}/runs/${variant}/seed_${seed}/calibration.json"
  test -f "${model}/saved_model.pb" || { echo "Missing frozen model: ${model}" >&2; exit 4; }
  test -f "${calibration}" || { echo "Missing frozen calibration: ${calibration}" >&2; exit 4; }

  "${PYTHON_BIN}" - "${SCRIPT_DIR}" "${SELECTION}" "${variant}" "${model}" "${calibration}" <<'PY'
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from evaluate_multipath_model_on_dataset import artifact_hash
p=json.load(open(sys.argv[2])); f=p["representatives_for_single_test_pass"][sys.argv[3]]
if artifact_hash(Path(sys.argv[4]).resolve()).get("sha256_tree") != f["model"]["sha256_tree"]:
 raise SystemExit("Frozen model hash mismatch")
if hashlib.sha256(Path(sys.argv[5]).read_bytes()).hexdigest() != f["calibration"]["sha256"]:
 raise SystemExit("Frozen calibration hash mismatch")
PY

  for mode in "${modes[@]}"; do
    mkdir -p "${ABLATION_RESULTS}/${variant}/${mode}"
    for subset in "${subsets[@]}"; do
      output="${ABLATION_RESULTS}/${variant}/${mode}/test_${subset}.json"
      if "${PYTHON_BIN}" - "${output}" "${variant}" "${mode}" "${subset}" "${ABLATION_SEED}" "${SELECTION}" <<'PY'
import json,sys
try:
 p=json.load(open(sys.argv[1])); s=json.load(open(sys.argv[6])); f=s["representatives_for_single_test_pass"][sys.argv[2]]
 a=p.get("interaction_ablation") or {}
 valid=(p.get("status") in ("pass","not_applicable") and p.get("split")=="test" and p.get("subset")==sys.argv[4]
  and p.get("model_artifact",{}).get("sha256_tree")==f["model"]["sha256_tree"]
  and (p.get("calibration") or {}).get("parameters")==f["calibration_parameters"]
  and a.get("mode")==sys.argv[3] and a.get("applied") is True and int(a.get("seed"))==int(sys.argv[5])
  and p.get("calibration_fit_uses_test") is False)
except Exception: valid=False
raise SystemExit(0 if valid else 1)
PY
      then
        echo "skip verified ${variant}/${mode}/${subset}"
        continue
      fi
      if [[ -e "${output}" ]]; then
        echo "Invalid existing context-ablation output will not be overwritten: ${output}" >&2
        exit 5
      fi
      echo "[$(date --iso-8601=seconds)] evaluate ${variant}/${mode}/${subset}"
      "${PYTHON_BIN}" "${SCRIPT_DIR}/evaluate_multipath_model_on_dataset.py" \
        --merged_dir "${DAY7_RESULTS}" --split test --subset "${subset}" \
        --model "${model}" --anchors "${ANCHORS}" --batch_size "${BATCH_SIZE}" \
        --calibration-json "${calibration}" --interaction-ablation "${mode}" \
        --ablation-seed "${ABLATION_SEED}" --output_json "${output}"
    done
  done
done

SUMMARY="${ABLATION_RESULTS}/interaction_context_ablation_summary.json"
"${PYTHON_BIN}" "${SCRIPT_DIR}/summarize_interaction_context_ablation.py" \
  --results-dir "${ABLATION_RESULTS}" --day8-test-summary "${DAY8_SUMMARY}" \
  --selection-json "${SELECTION}" --output-json "${SUMMARY}"

"${PYTHON_BIN}" - "${SUMMARY}" "${ABLATION_RESULTS}/CONTEXT_ABLATION_COMPLETE.json" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
source,output=map(Path,sys.argv[1:]); payload=json.loads(source.read_text())
if payload.get("status")!="pass" or payload.get("test_used_for_selection") is not False: raise SystemExit("Ablation summary failed")
done={"schema_version":"interaction_context_ablation_complete_v1","status":"pass",
      "test_used_for_selection":False,"summary_sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(done,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY

"${PYTHON_BIN}" "${SCRIPT_DIR}/package_interaction_context_ablation.py" \
  --results-dir "${ABLATION_RESULTS}" \
  --output "${ABLATION_RESULTS}/interaction_context_ablation_snapshot.tar.gz"

echo "[$(date --iso-8601=seconds)] interaction-context ablation complete"
cat "${ABLATION_RESULTS}/CONTEXT_ABLATION_COMPLETE.json"
