#!/usr/bin/env bash
set -euo pipefail

# Collect prediction datasets from CARLA rollouts for MultiPath calibration or
# future fine-tuning. Prediction logging is enabled explicitly and writes each
# subrun's files under <subrun>/prediction_dataset/.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
RESULTS_DIR="${RESULTS_DIR:-${CORE_DIR}/results/$(date +%Y%m%d_%H%M%S)_prediction_dataset_collection}"
PYTHON_BIN="${PYTHON_BIN:-python}"
INIT_COUNT="${INIT_COUNT:-10}"
POLICIES="${POLICIES:-smpc_var_risk}"
SAVE_RASTER="${SAVE_RASTER:-0}"
LOG_STRIDE="${LOG_STRIDE:-1}"
LOG_HORIZON="${LOG_HORIZON:-10}"
ENABLE_CAMERA_VIZ="${ENABLE_CAMERA_VIZ:-0}"

if [[ -z "${CARLA_ROOT:-}" ]]; then
  cat >&2 <<'EOF'
ERROR: CARLA_ROOT is not set.

Please export the CARLA 0.9.14 root before running this batch, for example:
  export CARLA_ROOT=/root/autodl-tmp/CARLA_0.9.14
EOF
  exit 2
fi

if [[ ! -f "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py" ]]; then
  cat >&2 <<EOF
ERROR: CARLA_ROOT does not look like a valid CARLA 0.9.14 root:
  CARLA_ROOT=${CARLA_ROOT}

Expected file not found:
  ${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py

Locate the correct root with:
  find /root /root/autodl-tmp -maxdepth 5 -type f -name global_route_planner.py 2>/dev/null

Then export CARLA_ROOT to the directory that contains PythonAPI, for example:
  export CARLA_ROOT=/root/autodl-tmp/CARLA_0.9.14
EOF
  exit 2
fi

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${PYTHONPATH:-}"

mkdir -p "${RESULTS_DIR}"
cd "${SCRIPT_DIR}"

TMP_INIT_DIR="${RESULTS_DIR}/_ego_init_01_${INIT_COUNT}"
mkdir -p "${TMP_INIT_DIR}"
for idx_num in $(seq 1 "${INIT_COUNT}"); do
  idx="$(printf '%02d' "${idx_num}")"
  ln -sfn "${SCRIPT_DIR}/scenarios/inits/paper_intersection_50/ego_init_${idx}.json" \
    "${TMP_INIT_DIR}/ego_init_${idx}.json"
done

camera_args=()
if [[ "${ENABLE_CAMERA_VIZ}" == "1" ]]; then
  camera_args+=(--enable_camera_viz)
else
  camera_args+=(--disable_camera_viz)
fi

raster_args=()
if [[ "${SAVE_RASTER}" == "1" ]]; then
  raster_args+=(--prediction_logging_save_raster)
fi

read -r -a policy_args <<< "${POLICIES}"

cat > "${RESULTS_DIR}/prediction_dataset_collection_config.json" <<EOF
{
  "script": "$(basename "$0")",
  "results_dir": "${RESULTS_DIR}",
  "init_count": ${INIT_COUNT},
  "policies": "${POLICIES}",
  "save_raster": ${SAVE_RASTER},
  "log_stride": ${LOG_STRIDE},
  "log_horizon": ${LOG_HORIZON},
  "scenario_glob": "scenario_uk_give_way.json",
  "risk_profile": "adaptive_interaction_severity"
}
EOF

"${PYTHON_BIN}" run_all_scenarios.py \
  --scenario_glob "scenario_uk_give_way.json" \
  --init_glob "${TMP_INIT_DIR}/ego_init_*.json" \
  --results_dir "${RESULTS_DIR}" \
  --policies "${policy_args[@]}" \
  --risk_profile adaptive_interaction_severity \
  --enable_prediction_logging \
  --prediction_logging_stride "${LOG_STRIDE}" \
  --prediction_logging_horizon "${LOG_HORIZON}" \
  "${raster_args[@]}" \
  "${camera_args[@]}" \
  --postprocess_no_plots

find "${RESULTS_DIR}" -path "*/prediction_dataset/prediction_dataset_manifest.json" \
  | sort > "${RESULTS_DIR}/prediction_dataset_manifests.txt"

echo "Prediction dataset collection complete: ${RESULTS_DIR}"
echo "Manifest list: ${RESULTS_DIR}/prediction_dataset_manifests.txt"
