#!/usr/bin/env bash
set -Eeuo pipefail

PREPARE_ONLY=0
if [[ "${1:-}" == "--prepare-only" ]]; then
  PREPARE_ONLY=1
  shift
fi
if (($# != 0)); then
  echo "Usage: $0 [--prepare-only]" >&2
  exit 2
fi

# Resume the frozen SF4 matrix after exactly one rollout exhausted its original
# attempt cap exclusively during a CARLA API outage.  Treatment/statistical
# sources and the original contract remain byte-identical.  A frozen amendment
# inside the affected attempt tree preserves every failed attempt and extends
# the cap for that key only.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
DAY7_RESULTS="${DAY7_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day8/day8_validation_v1}"
SF4_RESULTS="${SF4_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/distinction_v1/sf4_supervisor_behavioural_authority_v1}"
B1_MODEL="${B1_MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/l5kit_clusters_16.npy}"
SCENARIO_SOURCE="${SCENARIO_SOURCE:-${SCRIPT_DIR}/scenarios/scenario_uk_give_way.json}"
INIT_SOURCE="${INIT_SOURCE:-${SCRIPT_DIR}/scenarios/inits/distinction_sf4_supervisor_authority_ablation}"
PREREG_JSON="${PREREG_JSON:-${REPO_DIR}/docs/paper/generated/distinction_sf4_supervisor_authority_ablation/prereg/SF4_SUPERVISOR_BEHAVIOURAL_AUTHORITY_PREREG.json}"
CONTRACT="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_run_contract.json"
PREFLIGHT="${SF4_RESULTS}/SF4_PREFLIGHT_COMPLETE.json"
SMOKE="${SF4_RESULTS}/SF4_SMOKE_COMPLETE.json"
SPAWN_PREFLIGHT="${SF4_RESULTS}/sf4_town05_spawn_preflight.json"
DEPLOYMENT_PREFLIGHT="${SF4_RESULTS}/sf4_b1_deployment_preflight.json"
ATTEMPT_MANAGER="${MODELS_DIR}/r3_attempt_manager.py"
RECOVERY_PREPARE="${MODELS_DIR}/prepare_sf4_infrastructure_recovery.py"
ANALYZER="${MODELS_DIR}/analyze_sf4_supervisor_behavioural_authority.py"
PACKAGER="${MODELS_DIR}/package_sf4_compact_evidence.py"
FULL_PACKAGER="${MODELS_DIR}/package_sf4_full_raw_snapshot.py"
ORIGINAL_MAX_ATTEMPTS=10
RECOVERY_MAX_ATTEMPTS="${SF4_RECOVERY_MAX_ATTEMPTS:-20}"
PROTOCOL_ID="sf4_supervisor_behavioural_authority_v1"

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
if [[ "${RECOVERY_MAX_ATTEMPTS}" != "20" ]]; then
  echo "SF4 recovery cap is frozen at 20" >&2
  exit 2
fi
for required in \
  "${CONTRACT}" "${PREFLIGHT}" "${SMOKE}" "${SPAWN_PREFLIGHT}" \
  "${DEPLOYMENT_PREFLIGHT}" "${B1_MODEL}/saved_model.pb" \
  "${B1_CALIBRATION}" "${ANCHORS}" "${SCENARIO_SOURCE}" \
  "${ATTEMPT_MANAGER}" "${RECOVERY_PREPARE}" "${ANALYZER}" \
  "${PACKAGER}" "${FULL_PACKAGER}"; do
  test -e "${required}" || { echo "Missing SF4 recovery asset: ${required}" >&2; exit 2; }
done
if [[ -n "$(git -C "${REPO_DIR}" status --porcelain --untracked-files=no)" ]]; then
  echo "SF4 recovery requires a clean tracked Git worktree" >&2
  exit 3
fi
if [[ -s "${SF4_RESULTS}/sf4_runner.pid" ]] \
  && kill -0 "$(cat "${SF4_RESULTS}/sf4_runner.pid")" 2>/dev/null; then
  echo "Original SF4 runner is still active; recovery must run alone" >&2
  exit 3
fi

mkdir -p "${SF4_RESULTS}"
exec > >(tee -a "${SF4_RESULTS}/sf4_recovery_runner.log") 2>&1
LOCK="${SF4_RESULTS}/.recovery_runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another SF4 recovery runner is active: PID $(cat "${LOCK}/pid")" >&2
    exit 4
  fi
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() { rm -f "${LOCK}/pid"; rmdir "${LOCK}" 2>/dev/null || true; }
trap cleanup EXIT

export PYTHONPATH="${CARLA_ROOT}/PythonAPI/carla:${CARLA_ROOT}/PythonAPI/carla/agents:${MODELS_DIR}:${PYTHONPATH:-}"
GUROBI_BUNDLE_ROOT="${GUROBI_BUNDLE_ROOT:-${IMLS_REPO:-/path/to/Research-Project-IMLS}/gurobi}"
if [[ -z "${GUROBI_HOME:-}" ]]; then
  for candidate in "${REPO_DIR}/gurobi/gurobi1103/linux64" "${GUROBI_BUNDLE_ROOT}/gurobi1103/linux64"; do
    if [[ -d "${candidate}" ]]; then export GUROBI_HOME="${candidate}"; break; fi
  done
fi
export GUROBI_VERSION="${GUROBI_VERSION:-110}"
if [[ -z "${GRB_LICENSE_FILE:-}" ]]; then
  for candidate in "${REPO_DIR}/gurobi/gurobi.lic" "${GUROBI_BUNDLE_ROOT}/gurobi.lic"; do
    if [[ -f "${candidate}" ]]; then export GRB_LICENSE_FILE="${candidate}"; break; fi
  done
fi
if [[ -n "${GUROBI_HOME:-}" ]]; then export LD_LIBRARY_PATH="${GUROBI_HOME}/lib:${LD_LIBRARY_PATH:-}"; fi

"${PYTHON_BIN}" -c 'import casadi as ca,sys; print("CasADi/Gurobi:",ca.__version__,ca.has_conic("gurobi")); sys.exit(0 if ca.has_conic("gurobi") else 2)'
"${PYTHON_BIN}" -c 'import carla,sys; c=carla.Client("127.0.0.1",2000); c.set_timeout(10); w=c.get_world(); m=w.get_map().name; a=[x for x in w.get_actors() if x.type_id.startswith(("vehicle.","sensor."))]; print("CARLA:",m,"experiment actors:",len(a)); sys.exit(0 if m.endswith("Town05") and not a else 4)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'

RECOVERY_JSON="$("${PYTHON_BIN}" "${RECOVERY_PREPARE}" prepare \
  --results-dir "${SF4_RESULTS}" --repo "${REPO_DIR}" \
  --contract "${CONTRACT}" --preflight "${PREFLIGHT}" --smoke "${SMOKE}" \
  --recovery-runner "${BASH_SOURCE[0]}" --extended-max "${RECOVERY_MAX_ATTEMPTS}")"
echo "${RECOVERY_JSON}"
read -r RECOVERY_CELL RECOVERY_INIT ORIGINAL_MAX_ATTEMPTS CONTRACT_COMMIT AMENDMENT < <(
  "${PYTHON_BIN}" -c 'import json,sys; p=json.loads(sys.stdin.read()); print(p["cell_id"],p["ego_init_id"],p["original_max_attempts"],p["contract_git_commit"],p["amendment"])' \
    <<<"${RECOVERY_JSON}"
)

if ((PREPARE_ONLY)); then
  echo "SF4 infrastructure recovery prepare-only: PASS"
  echo "No CARLA rollout was launched. Frozen amendment: ${AMENDMENT}"
  exit 0
fi

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["reactive_parameters"],separators=(",",":")))' "${CONTRACT}")"

max_attempts_for() {
  if [[ "$1" == "${RECOVERY_CELL}" && "$2" == "${RECOVERY_INIT}" ]]; then
    echo "${RECOVERY_MAX_ATTEMPTS}"
  else
    echo "${ORIGINAL_MAX_ATTEMPTS}"
  fi
}

run_rollout() {
  local cell_id="$1" policy="$2" style="$3" mode="$4" init_id="$5"
  local cell_dir="${SF4_RESULTS}/${cell_id}"
  local tuning="${SF4_RESULTS}/_frozen_tuning/supervisor_authority_${mode}.json"
  local policy_name risk_profile target_style max_attempts
  local attempt_dir attempt_log prepare_json prepare_status finalize_json finalize_status
  local scenario_status=1 attempt=0 retry_allowed=0
  local adaptive_arg=()
  mkdir -p "${cell_dir}"
  max_attempts="$(max_attempts_for "${cell_id}" "${init_id}")"
  case "${policy}" in
    fixed_medium) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_medium ;;
    adaptive)
      policy_name=smpc_var_risk; risk_profile=adaptive_interaction_severity
      adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}')
      ;;
    *) echo "Unknown SF4 policy: ${policy}" >&2; return 5 ;;
  esac
  if [[ "${style}" == "reactive" ]]; then target_style=defensive_reactive; else target_style=assertive_constant_speed; fi
  while true; do
    prepare_status=0
    prepare_json="$(${PYTHON_BIN} "${ATTEMPT_MANAGER}" prepare \
      --cell-dir "${cell_dir}" --cell-id "${cell_id}" --init-id "${init_id}" \
      --max-attempts "${max_attempts}" --receipt-prefix SF4)" || prepare_status=$?
    echo "${prepare_json}"
    if [[ "${prepare_json}" == *'"status": "complete"'* ]]; then
      echo "[$(date --iso-8601=seconds)] SF4 recovery skip verified ${cell_id}/init${init_id}"
      return 0
    fi
    if ((prepare_status != 0)); then return "${prepare_status}"; fi
    read -r attempt attempt_dir attempt_log < <("${PYTHON_BIN}" -c \
      'import json,sys; p=json.loads(sys.stdin.read()); print(p["attempt"],p["attempt_dir"],p["attempt_log"])' <<<"${prepare_json}")
    echo "[$(date --iso-8601=seconds)] SF4 recovery ${cell_id}/init${init_id} attempt=${attempt}/${max_attempts}"
    if (
      set -Eeuo pipefail
      "${PYTHON_BIN}" "${ATTEMPT_MANAGER}" hygiene --attempt-dir "${attempt_dir}" \
        --host 127.0.0.1 --port 2000 --timeout 10
      "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
        --scenario_glob scenario_uk_give_way.json \
        --init_glob "${INIT_SOURCE}/ego_init_${init_id}.json" \
        --results_dir "${attempt_dir}" --policies "${policy_name}" \
        --risk_profile "${risk_profile}" --tuning_config "${tuning}" \
        --prediction_model_weights "${B1_MODEL}" --prediction_model_anchors "${ANCHORS}" \
        --prediction_model_calibration "${B1_CALIBRATION}" \
        --target_style "${target_style}" --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
        --enable_prediction_logging --prediction_logging_stride 1 --prediction_logging_horizon 10 \
        --prediction_dataset_version distinction_sf4_supervisor_behavioural_authority \
        --prediction_protocol_id "${PROTOCOL_ID}" --prediction_cell_id "${cell_id}" \
        --prediction_ego_policy_label "${policy}" --prediction_git_commit "${CONTRACT_COMMIT}" \
        --disable_camera_viz --postprocess_no_plots "${adaptive_arg[@]}"
    ) 2>&1 | tee "${attempt_log}"; then scenario_status=0; else scenario_status=$?; fi
    finalize_status=0
    finalize_json="$(${PYTHON_BIN} "${ATTEMPT_MANAGER}" finalize \
      --cell-dir "${cell_dir}" --cell-id "${cell_id}" --init-id "${init_id}" \
      --max-attempts "${max_attempts}" --receipt-prefix SF4 \
      --attempt-dir "${attempt_dir}" --exit-code "${scenario_status}")" || finalize_status=$?
    echo "${finalize_json}"
    if [[ "${finalize_json}" == *'"status": "accepted"'* ]]; then return 0; fi
    retry_allowed="$(${PYTHON_BIN} -c 'import json,sys; print(1 if json.loads(sys.stdin.read()).get("retry_allowed") else 0)' <<<"${finalize_json}")"
    if ((finalize_status != 0 || retry_allowed != 1)); then return 5; fi
    if ((attempt >= max_attempts)); then return 4; fi
    sleep $((5 * attempt))
  done
}

while IFS=$'\t' read -r cell_id policy style mode init_id; do
  run_rollout "${cell_id}" "${policy}" "${style}" "${mode}" "${init_id}"
done < <("${PYTHON_BIN}" - "${CONTRACT}" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1]))["execution_order"]:
 print(item["cell_id"],item["risk_policy"],item["target_style"],item["supervisor_authority_mode"],item["ego_init_id"],sep="\t")
PY
)

for policy in adaptive fixed_medium; do
  for style in assertive reactive; do
    for mode in on off; do
      cell_id="SF4_B1_${policy}_${style}_supervisor_${mode}"
      cell_dir="${SF4_RESULTS}/${cell_id}"
      if [[ "${policy}" == adaptive ]]; then required_policy=smpc_var_risk; else required_policy=smpc_fixed_risk; fi
      gate_status=0
      "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${cell_dir}" \
        --required-policies "${required_policy}" --require-fixed-geometry-yield \
        --footprint-margin-m 0.25 --footprint-margins-m 0.0,0.25,0.35,0.50 \
        --conflict-radius-m 4.0 --clearance-tolerance-s 0.2 || gate_status=$?
      echo "[$(date --iso-8601=seconds)] SF4 recovery scientific gate status=${gate_status} cell=${cell_id}"
      test -s "${cell_dir}/postcarla_trajectory_gate.json"
      for init_id in $(seq 106 115); do
        max_attempts="$(max_attempts_for "${cell_id}" "${init_id}")"
        "${PYTHON_BIN}" "${ATTEMPT_MANAGER}" verify \
          --cell-dir "${cell_dir}" --cell-id "${cell_id}" --init-id "${init_id}" \
          --max-attempts "${max_attempts}" --receipt-prefix SF4
      done
    done
  done
done

"${PYTHON_BIN}" "${ANALYZER}" --results-dir "${SF4_RESULTS}" \
  --contract "${CONTRACT}" --prereg "${PREREG_JSON}" \
  --output-dir "${SF4_RESULTS}/analysis"

FULL_RAW_SNAPSHOT="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz"
"${PYTHON_BIN}" "${FULL_PACKAGER}" --results-dir "${SF4_RESULTS}" \
  --prereg "${PREREG_JSON}" --output "${FULL_RAW_SNAPSHOT}"
"${PYTHON_BIN}" "${FULL_PACKAGER}" --verify-only --output "${FULL_RAW_SNAPSHOT}"
FULL_RAW_MARKER="${SF4_RESULTS}/SF4_FULL_RAW_SNAPSHOT_COMPLETE.json"

"${PYTHON_BIN}" "${RECOVERY_PREPARE}" complete \
  --results-dir "${SF4_RESULTS}" --contract "${CONTRACT}" \
  --prereg "${PREREG_JSON}" --spawn "${SPAWN_PREFLIGHT}" \
  --deployment "${DEPLOYMENT_PREFLIGHT}" \
  --analysis "${SF4_RESULTS}/analysis/SF4_ANALYSIS_COMPLETE.json" \
  --archive "${FULL_RAW_SNAPSHOT}" --full-marker "${FULL_RAW_MARKER}" \
  --amendment "${AMENDMENT}"

COMPACT_PACKAGE="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_compact_evidence.tar.gz"
"${PYTHON_BIN}" "${PACKAGER}" --results-dir "${SF4_RESULTS}" --output "${COMPACT_PACKAGE}"
"${PYTHON_BIN}" "${PACKAGER}" --verify-only --output "${COMPACT_PACKAGE}"
echo "[$(date --iso-8601=seconds)] SF4 infrastructure recovery and formal matrix complete"
cat "${SF4_RESULTS}/SF4_COMPLETE.json"
