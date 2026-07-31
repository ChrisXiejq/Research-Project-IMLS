#!/usr/bin/env bash
set -euo pipefail

# V2 2x2 collection runner:
#   S0/S1 target style x fixed-medium/adaptive-floor-weak ego policy.
# Day 4 defaults to init01; Day 5 may set INIT_END=5; Day 6 uses INIT_END=50.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_prediction_dataset_v2}"
PYTHON_BIN="${PYTHON_BIN:-python}"
INIT_START="${INIT_START:-1}"
INIT_END="${INIT_END:-1}"
LOG_STRIDE="${LOG_STRIDE:-4}"
LOG_HORIZON="${LOG_HORIZON:-10}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"
SKIP_COMPLETED_SUBRUNS="${SKIP_COMPLETED_SUBRUNS:-1}"
PREDICTION_MODEL_WEIGHTS="${PREDICTION_MODEL_WEIGHTS:-l5kit_multipath_10_carla_finetuned_head_best}"
PREDICTION_MODEL_ANCHORS="${PREDICTION_MODEL_ANCHORS:-l5kit_clusters_16.npy}"
TUNING_CONFIG="${TUNING_CONFIG:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v12_current_best.json}"
DATASET_VERSION="give_way_interaction_prediction_v2.0"
PROTOCOL_ID="town05_give_way_2x2_200_rollouts_v1"
FEATURE_SCHEMA_ID="give_way_interaction_sequence_v2"
ADAPTIVE_CONFIG='{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}'
REACTIVE_CONFIG_JSON="${REACTIVE_CONFIG_JSON:-}"

if [[ -z "${CARLA_ROOT:-}" ]]; then
  echo "ERROR: CARLA_ROOT is not set." >&2
  exit 2
fi
if [[ ! -f "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py" ]]; then
  echo "ERROR: invalid CARLA_ROOT=${CARLA_ROOT}" >&2
  exit 2
fi
if (( INIT_START < 1 || INIT_END > 50 || INIT_START > INIT_END )); then
  echo "ERROR: require 1 <= INIT_START <= INIT_END <= 50" >&2
  exit 2
fi

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${PYTHONPATH:-}"
mkdir -p "${RESULTS_DIR}"
GIT_COMMIT="${PREDICTION_GIT_COMMIT:-$(git -C "${REPO_DIR}" rev-parse HEAD)}"
TMP_INIT_DIR="${RESULTS_DIR}/_inits_${INIT_START}_${INIT_END}"
mkdir -p "${TMP_INIT_DIR}"
for idx_num in $(seq "${INIT_START}" "${INIT_END}"); do
  idx="$(printf '%02d' "${idx_num}")"
  ln -sfn \
    "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${idx}.json" \
    "${TMP_INIT_DIR}/ego_init_${idx}.json"
done

camera_args=(--disable_camera_viz)
if [[ "${ENABLE_CAMERA_VIZ}" == "1" ]]; then
  camera_args=(--enable_camera_viz)
fi
resume_args=()
if [[ "${SKIP_COMPLETED_SUBRUNS}" == "1" ]]; then
  resume_args=(--skip_completed_subruns)
fi
reactive_args=()
if [[ -n "${REACTIVE_CONFIG_JSON}" ]]; then
  reactive_args=(--reactive_config_json "${REACTIVE_CONFIG_JSON}")
fi

run_cell() {
  local cell_id="$1"
  local target_style="$2"
  local policy="$3"
  local risk_profile="$4"
  local ego_policy_label="$5"
  shift 5
  local cell_dir="${RESULTS_DIR}/${cell_id}"
  mkdir -p "${cell_dir}"
  "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
    --scenario_glob "scenario_uk_give_way.json" \
    --init_glob "${TMP_INIT_DIR}/ego_init_*.json" \
    --results_dir "${cell_dir}" \
    --policies "${policy}" \
    --risk_profile "${risk_profile}" \
    --tuning_config "${TUNING_CONFIG}" \
    --target_style "${target_style}" \
    --prediction_model_weights "${PREDICTION_MODEL_WEIGHTS}" \
    --prediction_model_anchors "${PREDICTION_MODEL_ANCHORS}" \
    --enable_prediction_logging \
    --prediction_logging_stride "${LOG_STRIDE}" \
    --prediction_logging_horizon "${LOG_HORIZON}" \
    --prediction_logging_save_raster \
    --prediction_dataset_version "${DATASET_VERSION}" \
    --prediction_protocol_id "${PROTOCOL_ID}" \
    --prediction_feature_schema_id "${FEATURE_SCHEMA_ID}" \
    --prediction_cell_id "${cell_id}" \
    --prediction_ego_policy_label "${ego_policy_label}" \
    --prediction_git_commit "${GIT_COMMIT}" \
    "${reactive_args[@]}" \
    "${camera_args[@]}" \
    "${resume_args[@]}" \
    --skip_postprocess \
    "$@"
}

run_cell S0_FIXED assertive_constant_speed smpc_fixed_risk fixed_frontier_medium fixed_medium
run_cell S0_ADAPTIVE assertive_constant_speed smpc_var_risk adaptive_interaction_severity adaptive_floor_weak \
  --adaptive_risk_config_json "${ADAPTIVE_CONFIG}"
run_cell S1_FIXED defensive_reactive smpc_fixed_risk fixed_frontier_medium fixed_medium
run_cell S1_ADAPTIVE defensive_reactive smpc_var_risk adaptive_interaction_severity adaptive_floor_weak \
  --adaptive_risk_config_json "${ADAPTIVE_CONFIG}"

find "${RESULTS_DIR}" -path "*/prediction_dataset/prediction_dataset_manifest.json" \
  -type f | sort > "${RESULTS_DIR}/prediction_dataset_manifests.txt"

echo "V2 collection complete: ${RESULTS_DIR}"
