#!/usr/bin/env bash
set -Eeuo pipefail

# Formal 80-rollout matrix: B1/P* x fixed-medium/adaptive x two target styles
# x held-out groups 81--90. P* is read only from the validation-only freeze.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
V3_ROOT="${V3_ROOT:-${CORE_DIR}/results/capacity_history_v3}"
SELECTION_FREEZE="${SELECTION_FREEZE:-${V3_ROOT}/postprocess/selection_freeze.json}"
TRAINING_ROOT="${TRAINING_ROOT:-${V3_ROOT}/training}"
CALIBRATION_ROOT="${CALIBRATION_ROOT:-${V3_ROOT}/postprocess/calibration}"
MERGED_DIR="${MERGED_DIR:?Set MERGED_DIR to the frozen groups-1--45 dataset}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/l5kit_clusters_16.npy}"
TUNING_CONFIG="${TUNING_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
PROTOCOL_ROOT="${PROTOCOL_ROOT:-${V3_ROOT}/protocol}"
RESULTS_DIR="${RESULTS_DIR:-${V3_ROOT}/closed_loop}"
INIT_DIR="${PROTOCOL_ROOT}/inits/closed_loop"
MANIFEST="${RESULTS_DIR}/CLOSED_LOOP_MANIFEST.json"
PREFLIGHT="${RESULTS_DIR}/DEPLOYMENT_PREFLIGHT.json"
REACTIVE_CONFIG_JSON="${REACTIVE_CONFIG_JSON:?Set REACTIVE_CONFIG_JSON to the prospectively frozen reactive-policy JSON}"
ADAPTIVE_CONFIG='{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}'
PREFLIGHT_ONLY=0

if [[ "${1:-}" == "--preflight-only" ]]; then
  PREFLIGHT_ONLY=1
  shift
fi
if (($#)); then
  echo "Usage: $0 [--preflight-only]" >&2
  exit 2
fi

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
for required in "${SELECTION_FREEZE}" "${MERGED_DIR}/train.jsonl" "${ANCHORS}" \
  "${TUNING_CONFIG}" "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py"; do
  test -e "${required}" || { echo "Missing V3 closed-loop input: ${required}" >&2; exit 2; }
done
mkdir -p "${RESULTS_DIR}" "${PROTOCOL_ROOT}"
export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"

# The registry/inits operation is immutable and safely reusable after offline collection.
"${PYTHON_BIN}" "${MODELS_DIR}/capacity_study_v3_collection.py" freeze \
  --output-root "${PROTOCOL_ROOT}"

NUISANCE="${RESULTS_DIR}/nuisance_settings.json"
"${PYTHON_BIN}" - "${TUNING_CONFIG}" "${ANCHORS}" "${NUISANCE}" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
payload={"town":"Town05","scenario":"scenario_uk_give_way.json","tuning_sha256":digest(sys.argv[1]),"anchors_sha256":digest(sys.argv[2]),"supervisor_authority":"enabled","target_speed_mps":9.0,"target_offset_m":0.0}
path=Path(sys.argv[3]); rendered=json.dumps(payload,indent=2,sort_keys=True)+"\n"
if path.exists() and path.read_text()!=rendered: raise SystemExit("nuisance-setting drift")
path.write_text(rendered)
PY
"${PYTHON_BIN}" "${MODELS_DIR}/capacity_study_v3_closed_loop.py" freeze \
  --selection-freeze "${SELECTION_FREEZE}" --nuisance-json "${NUISANCE}" \
  --output "${MANIFEST}"

SOLVER_PREFLIGHT="${RESULTS_DIR}/solver_preflight.json"
"${PYTHON_BIN}" - "${SOLVER_PREFLIGHT}" <<'PY'
import json,os,sys
from pathlib import Path
import casadi as ca
payload={"status":"pass" if ca.has_conic("gurobi") else "fail","gurobi":bool(ca.has_conic("gurobi")),"casadi_version":ca.__version__}
path=Path(sys.argv[1]); temporary=path.with_suffix(".tmp"); temporary.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n"); os.replace(temporary,path)
if payload["status"] != "pass": raise SystemExit("Gurobi solver preflight failed")
PY
"${PYTHON_BIN}" -c 'import carla; c=carla.Client("127.0.0.1",2000); c.set_timeout(10.0); print("CARLA map:",c.get_world().get_map().name)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'
"${PYTHON_BIN}" "${MODELS_DIR}/verify_capacity_history_v3_deployment.py" \
  --selection-freeze "${SELECTION_FREEZE}" --closed-loop-manifest "${MANIFEST}" \
  --training-root "${TRAINING_ROOT}" --calibration-root "${CALIBRATION_ROOT}" \
  --merged-dir "${MERGED_DIR}" --anchors "${ANCHORS}" \
  --solver-preflight-json "${SOLVER_PREFLIGHT}" --output-json "${PREFLIGHT}"

if ((PREFLIGHT_ONLY)); then
  echo "V3 closed-loop preflight complete: ${PREFLIGHT}"
  exit 0
fi

readarray -t SELECTED_RUNS < <("${PYTHON_BIN}" - "${SELECTION_FREEZE}" <<'PY'
import json,sys
f=json.load(open(sys.argv[1])); print(f["B1"]["representative_run_id"]); print(f["P_star"]["representative_run_id"])
PY
)
B1_RUN="${SELECTED_RUNS[0]}"
PSTAR_RUN="${SELECTED_RUNS[1]}"

postprocess_cell() {
  local cell_dir="$1" policy_name="$2"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" \
    "${cell_dir}" --required-policies "${policy_name}"
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" \
    --results_dir "${cell_dir}" --compute_metrics
  "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${cell_dir}"
}

run_cell() {
  local predictor="$1" risk="$2" target_style="$3"
  local run_id model calibration policy_name risk_profile
  local adaptive_args=()
  if [[ "${predictor}" == "B1" ]]; then run_id="${B1_RUN}"; else run_id="${PSTAR_RUN}"; fi
  model="${TRAINING_ROOT}/${run_id}/best_model"
  calibration="${CALIBRATION_ROOT}/${run_id}/calibration.json"
  case "${risk}" in
    fixed_medium) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_medium ;;
    adaptive)
      policy_name=smpc_var_risk; risk_profile=adaptive_interaction_severity
      adaptive_args=(--adaptive_risk_config_json "${ADAPTIVE_CONFIG}")
      ;;
    *) echo "Unknown risk policy: ${risk}" >&2; exit 4 ;;
  esac
  local cell_id="${predictor}__${risk}__${target_style}"
  local cell_dir="${RESULTS_DIR}/${cell_id}"
  mkdir -p "${cell_dir}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
    --scenario_glob scenario_uk_give_way.json \
    --init_glob "${INIT_DIR}/ego_init_*.json" \
    --results_dir "${cell_dir}" --policies "${policy_name}" \
    --risk_profile "${risk_profile}" --tuning_config "${TUNING_CONFIG}" \
    --prediction_model_weights "${model}" --prediction_model_anchors "${ANCHORS}" \
    --prediction_model_calibration "${calibration}" \
    --target_style "${target_style}" --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
    --enable_prediction_logging --prediction_logging_stride 1 \
    --prediction_logging_horizon 10 \
    --prediction_protocol_id capacity_history_predictor_risk_v3 \
    --prediction_cell_id "${cell_id}" --prediction_ego_policy_label "${risk}" \
    --prediction_git_commit "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
    --disable_camera_viz --skip_completed_subruns --postprocess_no_plots \
    "${adaptive_args[@]}"
  postprocess_cell "${cell_dir}" "${policy_name}"
}

for predictor in B1 P_star; do
  for risk in fixed_medium adaptive; do
    for style in assertive_constant_speed defensive_reactive; do
      run_cell "${predictor}" "${risk}" "${style}"
    done
  done
done

"${PYTHON_BIN}" "${MODELS_DIR}/capacity_study_v3_closed_loop.py" materialize-carla \
  --selection-freeze "${SELECTION_FREEZE}" --manifest "${MANIFEST}" \
  --results-dir "${RESULTS_DIR}" --output "${RESULTS_DIR}/MATERIALIZATION_AUDIT.json"
"${PYTHON_BIN}" "${MODELS_DIR}/capacity_study_v3_closed_loop.py" audit \
  --selection-freeze "${SELECTION_FREEZE}" --manifest "${MANIFEST}" \
  --results-dir "${RESULTS_DIR}" --output "${RESULTS_DIR}/CLOSED_LOOP_AUDIT.json"
"${PYTHON_BIN}" - "${RESULTS_DIR}/CLOSED_LOOP_AUDIT.json" <<'PY'
import json,sys
report=json.load(open(sys.argv[1]))
if report.get("status") != "pass" or report.get("observed_rollouts") != 80:
    raise SystemExit("formal V3 closed-loop completion gate failed")
PY
"${PYTHON_BIN}" "${MODELS_DIR}/capacity_study_v3_closed_loop.py" synthesize-carla \
  --selection-freeze "${SELECTION_FREEZE}" --manifest "${MANIFEST}" \
  --results-dir "${RESULTS_DIR}" \
  --rows-output "${RESULTS_DIR}/closed_loop_rows.json" \
  --output "${RESULTS_DIR}/PREDICTOR_BY_RISK_SYNTHESIS.json"
"${PYTHON_BIN}" - "${RESULTS_DIR}" <<'PY'
import sys
from pathlib import Path
from capacity_study_v3_protocol import sha256_file, write_immutable_manifest
root=Path(sys.argv[1])
payload={"schema_version":"capacity_history_closed_loop_complete_v3","status":"pass","formal_evidence":True,"observed_rollouts":80,"artifact_sha256":{"manifest":sha256_file(root/"CLOSED_LOOP_MANIFEST.json"),"preflight":sha256_file(root/"DEPLOYMENT_PREFLIGHT.json"),"audit":sha256_file(root/"CLOSED_LOOP_AUDIT.json"),"rows":sha256_file(root/"closed_loop_rows.json"),"synthesis":sha256_file(root/"PREDICTOR_BY_RISK_SYNTHESIS.json")}}
write_immutable_manifest(root/"CLOSED_LOOP_COMPLETE.json",payload)
PY
echo "V3 formal closed-loop matrix complete: ${RESULTS_DIR}"
