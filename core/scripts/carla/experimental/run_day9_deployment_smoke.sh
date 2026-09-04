#!/usr/bin/env bash
set -Eeuo pipefail

# Day 9 is a development smoke only. It uses train init01 and never contributes
# to the formal Day 10 matrix.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
DAY7_RESULTS="${DAY7_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day8/day8_validation_v1}"
DAY9_RESULTS="${DAY9_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day9/day9_smoke_v1}"
B1_MODEL="${B1_MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
B0_MODEL="${B0_MODEL:-${MODELS_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/assets/l5kit_clusters_16.npy}"
TUNING_SOURCE="${TUNING_SOURCE:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
FROZEN_COLLECTION="${FROZEN_COLLECTION:-${REPO_DIR}/docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json}"

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" \
  "${DAY7_RESULTS}/train.jsonl" \
  "${DAY8_RESULTS}/DAY8_COMPLETE.json" \
  "${DAY8_RESULTS}/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json" \
  "${B1_MODEL}/saved_model.pb" \
  "${B1_CALIBRATION}" \
  "${B0_MODEL}/saved_model.pb" \
  "${ANCHORS}" \
  "${TUNING_SOURCE}" \
  "${FROZEN_COLLECTION}" \
  "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py"; do
  test -e "${required}" || { echo "Missing required Day 9 asset: ${required}" >&2; exit 2; }
done

mkdir -p "${DAY9_RESULTS}"
exec > >(tee -a "${DAY9_RESULTS}/day9_runner.log") 2>&1
if "${PYTHON_BIN}" - "${DAY9_RESULTS}/DAY9_COMPLETE.json" <<'PY'
import json, sys
try:
    payload=json.load(open(sys.argv[1]))
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if payload.get("status") == "pass" else 1)
PY
then
  echo "Day 9 already completed"
  cat "${DAY9_RESULTS}/DAY9_COMPLETE.json"
  exit 0
fi

LOCK="${DAY9_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another Day 9 runner is active: PID $(cat "${LOCK}/pid")" >&2
    exit 3
  fi
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

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"
if [[ -z "${GUROBI_HOME:-}" && -d "${REPO_DIR}/gurobi/gurobi1103/linux64" ]]; then
  export GUROBI_HOME="${REPO_DIR}/gurobi/gurobi1103/linux64"
fi
export GUROBI_VERSION="${GUROBI_VERSION:-110}"
if [[ -z "${GRB_LICENSE_FILE:-}" && -f "${REPO_DIR}/gurobi/gurobi.lic" ]]; then
  export GRB_LICENSE_FILE="${REPO_DIR}/gurobi/gurobi.lic"
fi
if [[ -n "${GUROBI_HOME:-}" ]]; then
  export LD_LIBRARY_PATH="${GUROBI_HOME}/lib:${LD_LIBRARY_PATH:-}"
fi

"${PYTHON_BIN}" -c 'import casadi as ca, sys; print("CasADi/Gurobi:", ca.__version__, ca.has_conic("gurobi")); sys.exit(0 if ca.has_conic("gurobi") else 2)'
"${PYTHON_BIN}" -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(10.0); print("CARLA map:",c.get_world().get_map().name)'
"${PYTHON_BIN}" -c 'import tensorflow as tf, sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'

PREFLIGHT="${DAY9_RESULTS}/day9_deployment_preflight.json"
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/verify_day9_deployment.py" \
  --day7-results "${DAY7_RESULTS}" \
  --day8-results "${DAY8_RESULTS}" \
  --model "${B1_MODEL}" \
  --calibration "${B1_CALIBRATION}" \
  --anchors "${ANCHORS}" \
  --baseline-model "${B0_MODEL}" \
  --output-json "${PREFLIGHT}"

TUNING_CONFIG="${DAY9_RESULTS}/tuning_day9_frozen.json"
if [[ -f "${TUNING_CONFIG}" ]]; then
  cmp --silent "${TUNING_SOURCE}" "${TUNING_CONFIG}" || {
    echo "Frozen Day 9 tuning config drift" >&2
    exit 4
  }
else
  cp "${TUNING_SOURCE}" "${TUNING_CONFIG}"
fi

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c '
import json, sys
frozen=json.load(open(sys.argv[1]))["reactive_parameters"]
keys=("caution_speed_mps","minimum_speed_mps","activation_distance_m","release_clearance_m","arrival_time_gap_s","closest_approach_time_s","closest_approach_distance_m","release_hold_s")
print(json.dumps({key:frozen[key] for key in keys},separators=(",",":")))
' "${FROZEN_COLLECTION}")"

CONTRACT="${DAY9_RESULTS}/day9_run_contract.json"
"${PYTHON_BIN}" - "${PREFLIGHT}" "${CONTRACT}" "${TUNING_CONFIG}" "${REACTIVE_CONFIG_JSON}" <<'PY'
import hashlib, json, os, subprocess, sys
from pathlib import Path
preflight_path, output, tuning_path = map(Path, sys.argv[1:4])
reactive=json.loads(sys.argv[4])
preflight=json.loads(preflight_path.read_text())
arms=[]
for predictor in ("B1","B0"):
    for policy in ("fixed_medium","adaptive"):
        for style in ("assertive","reactive"):
            arms.append({"arm_id":f"{predictor}_{policy}_{style}","predictor":predictor,"risk_policy":policy,"target_style":style})
payload={
    "schema_version":"day9_deployment_smoke_contract_v1",
    "status":"frozen",
    "smoke_only_not_formal_evidence":True,
    "ego_init_id":1,
    "target_offset_m":0.0,
    "target_speed_mps":9.0,
    "authority_regime":"A3_risk_owned_yield",
    "predictors":{
        "B1":{
            "seed":37,
            "model_sha256_tree":preflight["b1"]["deployment"]["model_artifact"]["sha256_tree"],
            "calibration_sha256":preflight["b1"]["deployment"]["calibration_artifact"]["sha256"],
            "calibration_parameters":preflight["b1"]["deployment"]["calibration_parameters"],
        },
        "B0":{
            "model_sha256_tree":preflight["b0"]["deployment"]["model_artifact"]["sha256_tree"],
            "calibration":"identity_no_calibration_artifact",
        },
    },
    "arms":arms,
    "reactive_parameters":reactive,
    "tuning_sha256":hashlib.sha256(tuning_path.read_bytes()).hexdigest(),
    "preflight_sha256":hashlib.sha256(preflight_path.read_bytes()).hexdigest(),
    "git_commit":subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip(),
}
if output.exists() and json.loads(output.read_text()) != payload:
    raise SystemExit(f"Day 9 contract drift: {output}")
temporary=output.with_suffix(output.suffix+".tmp")
temporary.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
os.replace(temporary,output)
PY

INIT_DIR="${DAY9_RESULTS}/_ego_init_01"
mkdir -p "${INIT_DIR}"
ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_01.json" "${INIT_DIR}/ego_init_01.json"

postprocess_arm() {
  local arm_dir="$1"
  local required_policy="$2"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" \
    "${arm_dir}" --required-policies "${required_policy}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" \
    --results_dir "${arm_dir}" --compute_metrics
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${arm_dir}"
}

run_arm() {
  local predictor="$1"
  local policy="$2"
  local style="$3"
  local arm_id="${predictor}_${policy}_${style}"
  local arm_dir="${DAY9_RESULTS}/${arm_id}"
  local model calibration_arg=() policy_name risk_profile target_style adaptive_arg=()
  if [[ "${predictor}" == "B1" ]]; then
    model="${B1_MODEL}"
    calibration_arg=(--prediction_model_calibration "${B1_CALIBRATION}")
  else
    model="${B0_MODEL}"
  fi
  if [[ "${policy}" == "fixed_medium" ]]; then
    policy_name="smpc_fixed_risk"
    risk_profile="fixed_frontier_medium"
  else
    policy_name="smpc_var_risk"
    risk_profile="adaptive_interaction_severity"
    adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}')
  fi
  if [[ "${style}" == "reactive" ]]; then
    target_style="defensive_reactive"
  else
    target_style="assertive_constant_speed"
  fi
  mkdir -p "${arm_dir}"
  echo "[$(date --iso-8601=seconds)] Day9 arm=${arm_id}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
    --scenario_glob scenario_uk_give_way.json \
    --init_glob "${INIT_DIR}/ego_init_01.json" \
    --results_dir "${arm_dir}" \
    --policies "${policy_name}" \
    --risk_profile "${risk_profile}" \
    --tuning_config "${TUNING_CONFIG}" \
    --prediction_model_weights "${model}" \
    --prediction_model_anchors "${ANCHORS}" \
    "${calibration_arg[@]}" \
    --target_style "${target_style}" \
    --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
    --enable_prediction_logging \
    --prediction_logging_stride 1 \
    --prediction_logging_horizon 10 \
    --disable_camera_viz \
    --skip_completed_subruns \
    --postprocess_no_plots \
    "${adaptive_arg[@]}"
  postprocess_arm "${arm_dir}" "${policy_name}"
}

for predictor in B1 B0; do
  for policy in fixed_medium adaptive; do
    for style in assertive reactive; do
      run_arm "${predictor}" "${policy}" "${style}"
    done
  done
done

AUDIT="${DAY9_RESULTS}/day9_smoke_audit.json"
"${PYTHON_BIN}" "${MODELS_DIR}/experimental/audit_day9_smoke.py" \
  --results-dir "${DAY9_RESULTS}" \
  --contract-json "${CONTRACT}" \
  --output-json "${AUDIT}"

"${PYTHON_BIN}" - "${AUDIT}" "${PREFLIGHT}" "${DAY9_RESULTS}/DAY9_COMPLETE.json" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
audit_path, preflight_path, output=map(Path,sys.argv[1:])
audit=json.loads(audit_path.read_text()); preflight=json.loads(preflight_path.read_text())
if audit.get("status") != "pass" or preflight.get("status") != "pass":
    raise SystemExit("Day 9 completion gate failed")
payload={
    "schema_version":"day9_complete_v1",
    "status":"pass",
    "smoke_only_not_formal_evidence":True,
    "selected_variant":"B1",
    "selected_seed":37,
    "observed_arms":audit["observed_arms"],
    "deployment_preflight_sha256":hashlib.sha256(preflight_path.read_bytes()).hexdigest(),
    "smoke_audit_sha256":hashlib.sha256(audit_path.read_bytes()).hexdigest(),
}
temporary=output.with_suffix(output.suffix+".tmp")
temporary.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
os.replace(temporary,output)
PY

"${PYTHON_BIN}" "${MODELS_DIR}/experimental/package_day9_smoke_snapshot.py" \
  --results-dir "${DAY9_RESULTS}" \
  --output "${DAY9_RESULTS}/day9_smoke_snapshot.tar.gz"

echo "[$(date --iso-8601=seconds)] Day 9 complete"
cat "${DAY9_RESULTS}/DAY9_COMPLETE.json"
