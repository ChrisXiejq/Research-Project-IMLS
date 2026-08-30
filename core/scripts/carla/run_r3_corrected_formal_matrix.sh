#!/usr/bin/env bash
set -Eeuo pipefail

# Prospective corrected R3 v3 matrix:
# B0/B1 x 3 fixed + adaptive x assertive/reactive x 5 new init groups = 80.
# Scientific adverse outcomes are retained; only infrastructure/integrity
# failures stop the final R3 completion gate.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
DAY7_RESULTS="${DAY7_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day7/day7_v2_merged_v1}"
DAY8_RESULTS="${DAY8_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/day8/day8_validation_v1}"
R2_RESULTS="${R2_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/distinction_v1/r2_corrected_pilot_v4}"
R3_RESULTS="${R3_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/distinction_v1/r3_corrected_formal_v3}"
# The server has a history of transient termination.  Ten is a prospective,
# bounded infrastructure-only ceiling; scientific outcomes are never retried.
R3_MAX_ATTEMPTS="${R3_MAX_ATTEMPTS:-10}"
B1_MODEL="${B1_MODEL:-${DAY8_RESULTS}/runs/B1/seed_37/best_model}"
B1_CALIBRATION="${B1_CALIBRATION:-${DAY8_RESULTS}/runs/B1/seed_37/calibration.json}"
B0_MODEL="${B0_MODEL:-${MODELS_DIR}/l5kit_multipath_10}"
ANCHORS="${ANCHORS:-${MODELS_DIR}/l5kit_clusters_16.npy}"
TUNING_SOURCE="${TUNING_SOURCE:-${SCRIPT_DIR}/scenarios/tuning_configs/give_way_reduced_clear_path_release_v13_risk_owned_yield.json}"
SCENARIO_SOURCE="${SCENARIO_SOURCE:-${SCRIPT_DIR}/scenarios/scenario_uk_give_way.json}"
FROZEN_COLLECTION="${FROZEN_COLLECTION:-${REPO_DIR}/docs/paper/generated/day5/day5_final_6b71ccc_frozen_config.json}"
R1_CONTRACT="${R1_CONTRACT:-${REPO_DIR}/docs/paper/generated/distinction_v1/08_corrected_closed_loop/r1/R1_CORRECTED_CONTROL_CONTRACT.json}"
G2_DECISION="${G2_DECISION:-${REPO_DIR}/docs/paper/generated/distinction_v1/08_corrected_closed_loop/g2/G2_ROUTE_DECISION.json}"
M0_CONTRACT="${M0_CONTRACT:-${REPO_DIR}/docs/paper/generated/distinction_v1/09_analysis_contract/M0_R3_ANALYSIS_CONTRACT_v2.json}"
M0_ORIGINAL="${M0_ORIGINAL:-${REPO_DIR}/docs/paper/generated/distinction_v1/09_analysis_contract/M0_R3_ANALYSIS_CONTRACT.json}"
M0_AMENDMENT="${M0_AMENDMENT:-${REPO_DIR}/docs/paper/generated/distinction_v1/09_analysis_contract/M0_AMENDMENT_COMPLETE.json}"
M0_V2_MD="${M0_V2_MD:-${REPO_DIR}/docs/paper/generated/distinction_v1/09_analysis_contract/M0_R3_ANALYSIS_CONTRACT_v2.md}"
R3_INIT_SOURCE="${R3_INIT_SOURCE:-${SCRIPT_DIR}/scenarios/inits/distinction_r3_new}"
ATTEMPT_MANAGER="${MODELS_DIR}/r3_attempt_manager.py"
PROGRESS_SUMMARIZER="${MODELS_DIR}/summarize_r3_progress.py"
PROVENANCE_CAPTURE="${MODELS_DIR}/capture_r3_execution_provenance.py"
R3_ANALYZER="${MODELS_DIR}/analyze_r3_corrected_formal.py"
SNAPSHOT_PACKAGER="${MODELS_DIR}/package_closed_loop_snapshot.py"
R3_PREFLIGHT_ONLY=0
R3_LIST_PENDING=0

usage() {
  cat <<'EOF'
Usage: run_r3_corrected_formal_matrix.sh [--preflight-only | --list-pending]

  --preflight-only  Validate clean Git state, assets, CARLA/GPU/Gurobi,
                    frozen contracts and deployment without launching rollouts.
  --list-pending    Read-only progress/resume summary; CARLA is not required.

R3 requires a dedicated CARLA instance on 127.0.0.1:2000. Do not run any
other CARLA job against that port while this runner is active.
EOF
}

while (($#)); do
  case "$1" in
    --preflight-only) R3_PREFLIGHT_ONLY=1 ;;
    --list-pending) R3_LIST_PENDING=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done
if ((R3_PREFLIGHT_ONLY && R3_LIST_PENDING)); then
  echo "Choose only one of --preflight-only or --list-pending" >&2
  exit 2
fi
if ((R3_LIST_PENDING)); then
  exec "${PYTHON_BIN}" "${PROGRESS_SUMMARIZER}" --results-dir "${R3_RESULTS}"
fi

: "${CARLA_ROOT:?Set CARLA_ROOT to the CARLA 0.9.14 directory}"
if [[ ! "${R3_MAX_ATTEMPTS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "R3_MAX_ATTEMPTS must be a positive integer, got ${R3_MAX_ATTEMPTS}" >&2
  exit 2
fi
for required in \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" "${DAY7_RESULTS}/train.jsonl" \
  "${DAY8_RESULTS}/DAY8_COMPLETE.json" "${DAY8_RESULTS}/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json" \
  "${R2_RESULTS}/R2_COMPLETE.json" "${R2_RESULTS}/r2_corrected_pilot_audit.json" \
  "${B1_MODEL}/saved_model.pb" "${B1_CALIBRATION}" "${B0_MODEL}/saved_model.pb" \
  "${ANCHORS}" "${TUNING_SOURCE}" "${SCENARIO_SOURCE}" "${FROZEN_COLLECTION}" "${R1_CONTRACT}" \
  "${G2_DECISION}" "${M0_CONTRACT}" "${M0_ORIGINAL}" "${M0_AMENDMENT}" "${M0_V2_MD}" \
  "${R3_INIT_SOURCE}/R3_INIT_GENERATION_MANIFEST.json" \
  "${ATTEMPT_MANAGER}" "${PROGRESS_SUMMARIZER}" "${PROVENANCE_CAPTURE}" \
  "${R3_ANALYZER}" "${SNAPSHOT_PACKAGER}" \
  "${CARLA_ROOT}/PythonAPI/carla/agents/navigation/global_route_planner.py"; do
  test -e "${required}" || { echo "Missing R3 asset: ${required}" >&2; exit 2; }
done
for init_id in 101 102 103 104 105; do
  test -f "${R3_INIT_SOURCE}/ego_init_${init_id}.json" || exit 2
done

"${PYTHON_BIN}" - "${R2_RESULTS}/R2_COMPLETE.json" "${G2_DECISION}" "${M0_CONTRACT}" "${M0_AMENDMENT}" <<'PY'
import json,sys
r2,g2,m0,amendment=(json.load(open(path)) for path in sys.argv[1:])
if r2.get("status")!="pass": raise SystemExit("R2 is not complete")
if g2.get("status")!="frozen" or g2.get("decision")!="Route_R_corrected_prospective_core": raise SystemExit("G2 does not freeze Route R")
if m0.get("status") not in ("frozen_before_r3_outcomes","frozen_amendment_before_r3_outcomes"): raise SystemExit("M0 was not frozen before R3")
if amendment.get("status") not in ("pass","frozen") or amendment.get("frozen_before_r3_outcomes") is not True: raise SystemExit("M0 v2 amendment is not prospectively frozen")
PY

mkdir -p "${R3_RESULTS}"
exec > >(tee -a "${R3_RESULTS}/r3_runner.log") 2>&1
SNAPSHOT="${R3_RESULTS}/r3_corrected_formal_snapshot.tar.gz"
if [[ -f "${R3_RESULTS}/R3_COMPLETE.json" ]]; then
  complete_status=0
  "${PYTHON_BIN}" "${SNAPSHOT_PACKAGER}" --verify-only --output "${SNAPSHOT}" || complete_status=$?
  if ((complete_status == 0)) && "${PYTHON_BIN}" - "${R3_RESULTS}/R3_COMPLETE.json" "${SNAPSHOT}.json" "${SNAPSHOT}.files.json" "${R3_RESULTS}/R3_DATA_COMPLETE.json" "${R3_RESULTS}/analysis/R3_STUDY_STOP_GATE.json" <<'PY'
import hashlib,json,sys
from pathlib import Path
complete,snapshot,files_manifest,data,stop=map(Path,sys.argv[1:])
try:
 c=json.loads(complete.read_text()); s=json.loads(snapshot.read_text()); d=json.loads(data.read_text()); g=json.loads(stop.read_text())
except Exception: raise SystemExit(1)
ok=(c.get("status")=="pass" and c.get("additional_large_scale_carla_required") is False
 and d.get("status")=="pass" and g.get("additional_large_scale_carla_required") is False
 and c.get("archive_sha256")==s.get("archive_sha256")
 and c.get("archive_sidecar_sha256")==hashlib.sha256(snapshot.read_bytes()).hexdigest()
 and c.get("archive_files_manifest_sha256")==hashlib.sha256(files_manifest.read_bytes()).hexdigest()
 and c.get("data_complete_sha256")==hashlib.sha256(data.read_bytes()).hexdigest()
 and c.get("study_stop_gate_sha256")==hashlib.sha256(stop.read_bytes()).hexdigest())
raise SystemExit(0 if ok else 1)
PY
  then
    echo "R3 already complete; archive and stop gate re-verified"
    cat "${R3_RESULTS}/R3_COMPLETE.json"
    exit 0
  fi
  echo "Existing R3_COMPLETE failed archive/hash verification; rebuilding only derived evidence from accepted rollouts"
fi

LOCK="${R3_RESULTS}/.runner_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another R3 runner is active: PID $(cat "${LOCK}/pid")" >&2
    exit 3
  fi
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() { rm -f "${LOCK}/pid"; rmdir "${LOCK}" 2>/dev/null || true; }
trap cleanup EXIT

if [[ -n "$(git -C "${REPO_DIR}" status --porcelain --untracked-files=no)" ]]; then
  echo "R3 requires a clean tracked Git worktree. Commit/stash tracked changes before execution." >&2
  git -C "${REPO_DIR}" status --short --untracked-files=no >&2
  exit 4
fi

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
"${PYTHON_BIN}" -c 'import carla,sys; c=carla.Client("127.0.0.1",2000); c.set_timeout(10.0); m=c.get_world().get_map().name; print("CARLA map:",m); sys.exit(0 if m.endswith("Town05") else 4)'
"${PYTHON_BIN}" -c 'import tensorflow as tf,sys; g=tf.config.list_physical_devices("GPU"); print("TensorFlow GPUs:",g); sys.exit(0 if g else 3)'

"${PYTHON_BIN}" "${PROVENANCE_CAPTURE}" \
  --repo "${REPO_DIR}" --r1-contract "${R1_CONTRACT}" \
  --environment-output "${R3_RESULTS}/r3_environment.json" \
  --source-output "${R3_RESULTS}/r3_execution_source_manifest.json"

PREFLIGHT="${R3_RESULTS}/r3_deployment_preflight.json"
PREFLIGHT_CANDIDATE="${R3_RESULTS}/r3_deployment_preflight.candidate.tmp.json"
"${PYTHON_BIN}" "${MODELS_DIR}/verify_day9_deployment.py" \
  --day7-results "${DAY7_RESULTS}" --day8-results "${DAY8_RESULTS}" \
  --model "${B1_MODEL}" --calibration "${B1_CALIBRATION}" \
  --anchors "${ANCHORS}" --baseline-model "${B0_MODEL}" --output-json "${PREFLIGHT_CANDIDATE}"
"${PYTHON_BIN}" - "${PREFLIGHT_CANDIDATE}" "${PREFLIGHT}" <<'PY'
import json,os,sys
from pathlib import Path
candidate,output=map(Path,sys.argv[1:]); value=json.loads(candidate.read_text())
def semantic(v):
 return {"status":v.get("status"),"selected_variant":v.get("selected_variant"),"selected_seed":v.get("selected_seed"),"selection_freeze_sha256":v.get("selection_freeze_sha256"),"anchors":v.get("anchors"),"normalization":v.get("normalization"),"warmup_input":v.get("warmup_input"),"b1_deployment":(v.get("b1") or {}).get("deployment"),"b0_deployment":(v.get("b0") or {}).get("deployment")}
if value.get("status")!="pass": raise SystemExit("R3 deployment preflight failed")
if output.is_file():
 if semantic(json.loads(output.read_text()))!=semantic(value): raise SystemExit("Frozen R3 deployment preflight semantic drift")
 candidate.unlink()
else: os.replace(candidate,output)
PY

TUNING_CONFIG="${R3_RESULTS}/tuning_r3_frozen.json"
if [[ -f "${TUNING_CONFIG}" ]]; then
  cmp --silent "${TUNING_SOURCE}" "${TUNING_CONFIG}" || { echo "Frozen R3 tuning drift" >&2; exit 4; }
else
  cp "${TUNING_SOURCE}" "${TUNING_CONFIG}"
fi

REACTIVE_CONFIG_JSON="$("${PYTHON_BIN}" -c '
import json,sys
p=json.load(open(sys.argv[1]))["reactive_parameters"]
keys=("caution_speed_mps","minimum_speed_mps","activation_distance_m","release_clearance_m","arrival_time_gap_s","closest_approach_time_s","closest_approach_distance_m","release_hold_s")
print(json.dumps({k:p[k] for k in keys},separators=(",",":")))
' "${FROZEN_COLLECTION}")"

INIT_DIR="${R3_RESULTS}/_frozen_inits_101_105"
mkdir -p "${INIT_DIR}"
FROZEN_CONTRACT_DIR="${R3_RESULTS}/_frozen_contracts"
mkdir -p "${FROZEN_CONTRACT_DIR}"
"${PYTHON_BIN}" - "${R3_INIT_SOURCE}" "${INIT_DIR}" "${FROZEN_CONTRACT_DIR}" \
  "${R1_CONTRACT}" "${R2_RESULTS}/R2_COMPLETE.json" "${G2_DECISION}" "${M0_ORIGINAL}" \
  "${M0_CONTRACT}" "${M0_AMENDMENT}" "${M0_V2_MD}" "${R3_INIT_SOURCE}/R3_INIT_GENERATION_MANIFEST.json" "${FROZEN_COLLECTION}" \
  "${DAY7_RESULTS}/DAY7_COMPLETE.json" "${DAY8_RESULTS}/DAY8_COMPLETE.json" \
  "${DAY8_RESULTS}/final_test_v1/DAY8_MODEL_SELECTION_FROZEN.json" "${SCENARIO_SOURCE}" <<'PY'
import os,sys
from pathlib import Path
source,init_dir,frozen=map(Path,sys.argv[1:4])
copies=[]
for init_id in range(101,106): copies.append((source/f"ego_init_{init_id}.json",init_dir/f"ego_init_{init_id}.json"))
names=("R1_CORRECTED_CONTROL_CONTRACT.json","R2_COMPLETE.json","G2_ROUTE_DECISION.json",
 "M0_R3_ANALYSIS_CONTRACT.json","M0_R3_ANALYSIS_CONTRACT_v2.json","M0_AMENDMENT_COMPLETE.json","M0_R3_ANALYSIS_CONTRACT_v2.md","R3_INIT_GENERATION_MANIFEST.json",
 "day5_frozen_collection.json","DAY7_COMPLETE.json","DAY8_COMPLETE.json","DAY8_MODEL_SELECTION_FROZEN.json",
 "scenario_uk_give_way.json")
copies.extend((Path(src),frozen/name) for src,name in zip(sys.argv[4:],names))
for src,dst in copies:
 if not src.is_file(): raise SystemExit(f"Missing frozen source: {src}")
 data=src.read_bytes()
 if dst.is_symlink(): raise SystemExit(f"Frozen evidence may not be a symlink: {dst}")
 if dst.exists():
  if dst.read_bytes()!=data: raise SystemExit(f"Frozen evidence drift: {dst}")
  continue
 dst.parent.mkdir(parents=True,exist_ok=True)
 tmp=dst.with_suffix(dst.suffix+".tmp"); tmp.write_bytes(data); os.replace(tmp,dst)
import hashlib,json
v1=frozen/"M0_R3_ANALYSIS_CONTRACT.json"; v2=frozen/"M0_R3_ANALYSIS_CONTRACT_v2.json"
amends=json.loads(v2.read_text()).get("amends_without_overwriting") or {}
if amends.get("path")!=v1.name or amends.get("sha256")!=hashlib.sha256(v1.read_bytes()).hexdigest():
 raise SystemExit("Frozen M0 v2 does not bind the copied original M0 contract")
marker=json.loads((frozen/"M0_AMENDMENT_COMPLETE.json").read_text())
if ((marker.get("original_m0") or {}).get("sha256")!=hashlib.sha256(v1.read_bytes()).hexdigest()
 or (marker.get("amended_m0_v2") or {}).get("sha256")!=hashlib.sha256(v2.read_bytes()).hexdigest()):
 raise SystemExit("M0 amendment marker hash binding failed")
human=frozen/"M0_R3_ANALYSIS_CONTRACT_v2.md"
if (marker.get("human_readable_amendment") or {}).get("sha256")!=hashlib.sha256(human.read_bytes()).hexdigest():
 raise SystemExit("M0 human-readable amendment hash binding failed")
PY

CONTRACT="${R3_RESULTS}/r3_run_contract.json"
"${PYTHON_BIN}" - "${PREFLIGHT}" "${CONTRACT}" "${TUNING_CONFIG}" "${REACTIVE_CONFIG_JSON}" \
  "${INIT_DIR}" "${REPO_DIR}" "${R1_CONTRACT}" "${R2_RESULTS}/R2_COMPLETE.json" \
  "${G2_DECISION}" "${M0_CONTRACT}" "${M0_ORIGINAL}" "${M0_AMENDMENT}" \
  "${R3_INIT_SOURCE}/R3_INIT_GENERATION_MANIFEST.json" \
  "${R3_RESULTS}/r3_environment.json" "${R3_RESULTS}/r3_execution_source_manifest.json" \
  "${SCENARIO_SOURCE}" <<'PY'
import hashlib,json,os,random,subprocess,sys
from pathlib import Path
preflight_path,output,tuning_path=map(Path,sys.argv[1:4]); reactive=json.loads(sys.argv[4])
init_dir,repo,r1,r2,g2,m0,m0_original,m0_amendment,init_manifest,environment,source_manifest,scenario_source=map(Path,sys.argv[5:17])
pre=json.loads(preflight_path.read_text())
if pre.get("status")!="pass": raise SystemExit("R3 deployment preflight failed")
def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def semantic(value):
 return {"status":value.get("status"),"selected_variant":value.get("selected_variant"),"selected_seed":value.get("selected_seed"),"selection_freeze_sha256":value.get("selection_freeze_sha256"),"anchors":value.get("anchors"),"normalization":value.get("normalization"),"warmup_input":value.get("warmup_input"),"b1_deployment":(value.get("b1") or {}).get("deployment"),"b0_deployment":(value.get("b0") or {}).get("deployment")}
def semantic_hash(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
cells=[]
for predictor in ("B1","B0"):
 for policy in ("fixed_aggressive","fixed_medium","fixed_conservative","adaptive"):
  for style in ("assertive","reactive"):
   cells.append({"cell_id":f"{predictor}_{policy}_{style}","predictor":predictor,"risk_policy":policy,"target_style":style})
rng=random.Random(20260808); order=[]
for init_id in (101,102,103,104,105):
 block=[dict(cell,ego_init_id=init_id) for cell in cells]; rng.shuffle(block); order.extend(block)
payload={
 "schema_version":"r3_corrected_formal_contract_v2","status":"frozen","stage":"R3","formal_evidence":True,
 "result_generation":"distinction_corrected_v1","implementation_version":"corrected_joint_modes_shared_amin_v1",
 "research_comparison":"B1_vs_B0_predictor_stack_x_fixed_frontier_vs_adaptive_x_target_style",
 "ego_init_ids":[101,102,103,104,105],"expected_rollouts":80,"cells":cells,
 "execution_order_seed":20260808,"execution_order_method":"complete treatment block shuffled independently within each init","execution_order":order,
 "target_offset_m":0.0,"target_speed_mps":9.0,"authority_regime":"A3_risk_owned_yield","shared_A_MIN_mps2":-3.0,"n_modes":3,
 "scenario_contract":{"source":"core/scripts/carla/scenarios/scenario_uk_give_way.json","sha256":h(scenario_source),"map":"Town05","fps":20,"max_iters":600,"duration_limit_s":30.0},
 "scenario_source_sha256":h(scenario_source),
 "geometry_replay_contract":{"primary_footprint_margin_m_per_actor":0.25,"sensitivity_footprint_margins_m":[0.0,0.25,0.35,0.50],"fixed_conflict_radius_m":4.0,"clearance_tolerance_s":0.2,"actual_carla_bbox_and_local_pose_required":True},
 "risk_policies":["fixed_aggressive","fixed_medium","fixed_conservative","adaptive"],
 "adaptive_parameters":{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78},
 "reactive_parameters":reactive,"runtime_gate":{"max_p95_solve_time_s":0.5,"max_scenario_iters":600},
 "transient_retry_policy":{"max_attempts":int(os.environ.get("R3_MAX_ATTEMPTS","10")),"backoff_seconds":"5 * failed_attempt_index","attempts_isolated":True,"allowed_automatic_retry_classes":["spawn_collision","scenario_setup","carla_connection","carla_timeout","process_resource","external_signal","world_hygiene","external_interruption"],"unknown_failures_block_automatic_retry":True,"completed_rollouts_never_repeated":True,"scientific_outcomes_never_retried_or_excluded":True},
 "predictors":{"B1":{"seed":37,"model_sha256_tree":pre["b1"]["deployment"]["model_artifact"]["sha256_tree"],"calibration_sha256":pre["b1"]["deployment"]["calibration_artifact"]["sha256"],"calibration_parameters":pre["b1"]["deployment"]["calibration_parameters"]},"B0":{"model_sha256_tree":pre["b0"]["deployment"]["model_artifact"]["sha256_tree"],"calibration":"identity_no_calibration_artifact"}},
 "anchors_sha256":pre["anchors"]["sha256"],"init_sha256":{str(i):h(init_dir/f"ego_init_{i}.json") for i in range(101,106)},
 "init_generation_manifest_sha256":h(init_manifest),"tuning_sha256":h(tuning_path),"preflight_semantic_sha256":semantic_hash(semantic(pre)),
 "r1_contract_sha256":h(r1),"r2_complete_sha256":h(r2),"g2_decision_sha256":h(g2),"m0_analysis_contract_sha256":h(m0),"m0_original_contract_sha256":h(m0_original),"m0_amendment_complete_sha256":h(m0_amendment),
 "environment_sha256":h(environment),"execution_source_manifest_sha256":h(source_manifest),
 "frozen_source_files":{"tuning":{"scope":"results","path":"tuning_r3_frozen.json","sha256":h(tuning_path)},"scenario":{"scope":"results","path":"_frozen_contracts/scenario_uk_give_way.json","sha256":h(scenario_source)},"environment":{"scope":"results","path":"r3_environment.json","sha256":h(environment)},"execution_sources":{"scope":"results","path":"r3_execution_source_manifest.json","sha256":h(source_manifest)}},
 "deployment_preflight_filename":"r3_deployment_preflight.json",
 "prediction_protocol_id":"r3_corrected_formal_v3","git_commit":subprocess.check_output(["git","-C",str(repo),"rev-parse","HEAD"],text=True).strip(),
 "dedicated_carla_instance":{"host":"127.0.0.1","port":2000,"concurrent_jobs_prohibited":True,"pre_attempt_stale_actor_types":["vehicle.*","sensor.*"]},
 "analysis_unit":"ego_init_cluster","fixed_geometry_metric_required":True,"pilot_rollouts_excluded":True,"legacy_corrected_pooling_prohibited":True,"no_post_result_tuning":True,
}
rendered=json.dumps(payload,indent=2,sort_keys=True)+"\n"
if output.exists() and output.read_text()!=rendered: raise SystemExit(f"Frozen R3 contract drift: {output}")
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(rendered); os.replace(tmp,output)
PY

(
  cd "${REPO_DIR}"
  "${PYTHON_BIN}" -m unittest -v \
    core.scripts.models.tests.test_distinction_regression_gates \
    core.scripts.models.tests.test_r3_corrected_gates \
    core.scripts.models.tests.test_r3_runner_hardening \
    core.scripts.models.tests.test_r3_formal_analysis
)

PREFLIGHT_MARKER="${R3_RESULTS}/R3_PREFLIGHT_COMPLETE.json"
"${PYTHON_BIN}" - "${CONTRACT}" "${PREFLIGHT}" \
  "${R3_RESULTS}/r3_execution_source_manifest.json" "${R3_RESULTS}/r3_environment.json" \
  "${PREFLIGHT_MARKER}" "${R3_RESULTS}" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
contract,preflight,source,environment,output,root=map(Path,sys.argv[1:])
receipts=list(root.glob("*/R3_ROLLOUT_*_COMPLETE.json"))
def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
p={"schema_version":"r3_preflight_complete_v2","status":"pass","git_commit":json.loads(contract.read_text())["git_commit"],
 "contract_sha256":h(contract),"deployment_preflight_sha256":h(preflight),
 "execution_source_manifest_sha256":h(source),"environment_sha256":h(environment),
 "scientific_rollouts_launched":0,"dedicated_carla_instance_required":True}
rendered=json.dumps(p,indent=2,sort_keys=True)+"\n"
if output.is_file():
 if output.read_text()!=rendered: raise SystemExit("R3 preflight completion marker drift")
else:
 if receipts: raise SystemExit("Cannot create prospective preflight marker after rollout receipts exist")
 tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(rendered); os.replace(tmp,output)
PY

if ((R3_PREFLIGHT_ONLY)); then
  echo "[$(date --iso-8601=seconds)] R3 v3 preflight PASS; no scientific rollout was launched"
  "${PYTHON_BIN}" "${PROGRESS_SUMMARIZER}" --results-dir "${R3_RESULTS}" --contract-json "${CONTRACT}"
  exit 0
fi

run_rollout() {
  local predictor="$1" policy="$2" style="$3" init_id="$4"
  # Keep dependent assignments separate: with `set -u`, Bash expands every RHS
  # in a single `local` command before the earlier name is bound.
  local cell_id="${predictor}_${policy}_${style}"
  local cell_dir="${R3_RESULTS}/${cell_id}"
  local model policy_name risk_profile target_style attempt_dir attempt_log prepare_json prepare_status
  local finalize_json finalize_status scenario_status=1 attempt=0 retry_allowed=0
  local calibration_arg=() adaptive_arg=()
  mkdir -p "${cell_dir}"
  if [[ "${predictor}" == "B1" ]]; then model="${B1_MODEL}"; calibration_arg=(--prediction_model_calibration "${B1_CALIBRATION}"); else model="${B0_MODEL}"; fi
  case "${policy}" in
    fixed_aggressive) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_aggressive ;;
    fixed_medium) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_medium ;;
    fixed_conservative) policy_name=smpc_fixed_risk; risk_profile=fixed_frontier_conservative ;;
    adaptive) policy_name=smpc_var_risk; risk_profile=adaptive_interaction_severity; adaptive_arg=(--adaptive_risk_config_json '{"variant_name":"floor_weak","approach_preclearance_floor":1.66,"critical_preclearance_floor":1.72,"near_preclearance_floor":1.78}') ;;
    *) echo "Unknown risk policy: ${policy}" >&2; exit 5 ;;
  esac
  if [[ "${style}" == "reactive" ]]; then target_style=defensive_reactive; else target_style=assertive_constant_speed; fi
  while true; do
    prepare_status=0
    prepare_json="$("${PYTHON_BIN}" "${ATTEMPT_MANAGER}" prepare \
      --cell-dir "${cell_dir}" --cell-id "${cell_id}" --init-id "${init_id}" \
      --max-attempts "${R3_MAX_ATTEMPTS}")" || prepare_status=$?
    echo "${prepare_json}"
    if [[ "${prepare_json}" == *'"status": "complete"'* ]]; then
      echo "[$(date --iso-8601=seconds)] R3 skip verified accepted ${cell_id}/init${init_id}"
      return 0
    fi
    if ((prepare_status != 0)); then
      echo "R3 cannot start another attempt for ${cell_id}/init${init_id}: ${prepare_json}" >&2
      return "${prepare_status}"
    fi
    read -r attempt attempt_dir attempt_log < <("${PYTHON_BIN}" -c \
      'import json,sys; p=json.loads(sys.stdin.read()); print(p["attempt"],p["attempt_dir"],p["attempt_log"])' \
      <<<"${prepare_json}")
    echo "[$(date --iso-8601=seconds)] R3 ${cell_id}/init${init_id} attempt=${attempt}/${R3_MAX_ATTEMPTS}"
    if (
      set -Eeuo pipefail
      "${PYTHON_BIN}" "${ATTEMPT_MANAGER}" hygiene --attempt-dir "${attempt_dir}" \
        --host 127.0.0.1 --port 2000 --timeout 10
      "${PYTHON_BIN}" "${SCRIPT_DIR}/run_all_scenarios.py" \
        --scenario_glob scenario_uk_give_way.json --init_glob "${INIT_DIR}/ego_init_${init_id}.json" \
        --results_dir "${attempt_dir}" --policies "${policy_name}" --risk_profile "${risk_profile}" \
        --tuning_config "${TUNING_CONFIG}" --prediction_model_weights "${model}" --prediction_model_anchors "${ANCHORS}" \
        "${calibration_arg[@]}" --target_style "${target_style}" --reactive_config_json "${REACTIVE_CONFIG_JSON}" \
        --enable_prediction_logging --prediction_logging_stride 1 --prediction_logging_horizon 10 \
        --prediction_protocol_id r3_corrected_formal_v3 --prediction_cell_id "${cell_id}" \
        --prediction_ego_policy_label "${policy}" --prediction_git_commit "$(git -C "${REPO_DIR}" rev-parse HEAD)" \
        --disable_camera_viz --postprocess_no_plots "${adaptive_arg[@]}"
    ) 2>&1 | tee "${attempt_log}"; then
      scenario_status=0
    else
      scenario_status=$?
    fi
    finalize_status=0
    finalize_json="$("${PYTHON_BIN}" "${ATTEMPT_MANAGER}" finalize \
      --cell-dir "${cell_dir}" --cell-id "${cell_id}" --init-id "${init_id}" \
      --max-attempts "${R3_MAX_ATTEMPTS}" --attempt-dir "${attempt_dir}" \
      --exit-code "${scenario_status}")" || finalize_status=$?
    echo "${finalize_json}"
    if [[ "${finalize_json}" == *'"status": "accepted"'* ]]; then return 0; fi
    retry_allowed="$("${PYTHON_BIN}" -c 'import json,sys; print(1 if json.loads(sys.stdin.read()).get("retry_allowed") else 0)' <<<"${finalize_json}")"
    if ((finalize_status != 0 || retry_allowed != 1)); then
      echo "R3 non-retryable attempt failure: ${cell_id}/init${init_id}; inspect ${attempt_log}" >&2
      if ((finalize_status != 0)); then return "${finalize_status}"; else return 5; fi
    fi
    if ((attempt >= R3_MAX_ATTEMPTS)); then
      echo "R3 infrastructure failure exhausted ${R3_MAX_ATTEMPTS} attempts: ${cell_id}/init${init_id}" >&2
      return 4
    fi
    echo "[$(date --iso-8601=seconds)] predefined infrastructure failure; retry after $((5 * attempt))s"
    sleep $((5 * attempt))
  done
}

while IFS=$'\t' read -r predictor policy style init_id; do
  run_rollout "${predictor}" "${policy}" "${style}" "${init_id}"
done < <("${PYTHON_BIN}" - "${CONTRACT}" <<'PY'
import json,sys
for item in json.load(open(sys.argv[1]))["execution_order"]: print(item["predictor"],item["risk_policy"],item["target_style"],item["ego_init_id"],sep="\t")
PY
)

for predictor in B1 B0; do
  for policy in fixed_aggressive fixed_medium fixed_conservative adaptive; do
    for style in assertive reactive; do
      cell_dir="${R3_RESULTS}/${predictor}_${policy}_${style}"
      if [[ "${policy}" == adaptive ]]; then required_policy=smpc_var_risk; else required_policy=smpc_fixed_risk; fi
      gate_status=0
      "${PYTHON_BIN}" "${CORE_DIR}/scripts/postcarla_trajectory_gate.py" "${cell_dir}" \
        --required-policies "${required_policy}" --require-fixed-geometry-yield \
        --footprint-margin-m 0.25 --footprint-margins-m 0.0,0.25,0.35,0.50 \
        --conflict-radius-m 4.0 --clearance-tolerance-s 0.2 || gate_status=$?
      echo "[$(date --iso-8601=seconds)] R3 scientific outcome gate status=${gate_status} cell=$(basename "${cell_dir}")"
      "${PYTHON_BIN}" "${CORE_DIR}/scripts/compute_scenario_results.py" --results_dir "${cell_dir}" --compute_metrics
      "${PYTHON_BIN}" "${CORE_DIR}/scripts/risk_by_conflict_distance.py" "${cell_dir}"
      for init_id in 101 102 103 104 105; do
        "${PYTHON_BIN}" "${ATTEMPT_MANAGER}" verify --cell-dir "${cell_dir}" \
          --cell-id "$(basename "${cell_dir}")" --init-id "${init_id}" --max-attempts "${R3_MAX_ATTEMPTS}"
      done
    done
  done
done

AUDIT="${R3_RESULTS}/r3_corrected_matrix_audit.json"
"${PYTHON_BIN}" "${MODELS_DIR}/audit_r3_corrected_matrix.py" \
  --results-dir "${R3_RESULTS}" --contract-json "${CONTRACT}" --output-json "${AUDIT}"
"${PYTHON_BIN}" "${R3_ANALYZER}" --results-dir "${R3_RESULTS}" \
  --contract-json "${CONTRACT}" --analysis-contract "${M0_CONTRACT}" \
  --output-dir "${R3_RESULTS}/analysis"

DATA_COMPLETE="${R3_RESULTS}/R3_DATA_COMPLETE.json"
"${PYTHON_BIN}" - "${AUDIT}" "${PREFLIGHT}" "${CONTRACT}" \
  "${R3_RESULTS}/analysis/R3_ANALYSIS_COMPLETE.json" \
  "${R3_RESULTS}/analysis/R3_STUDY_STOP_GATE.json" \
  "${R3_RESULTS}/r3_execution_source_manifest.json" "${DATA_COMPLETE}" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
audit_path,preflight_path,contract_path,analysis_path,stop_path,source_path,output=map(Path,sys.argv[1:])
audit,pre,contract,analysis,stop=(json.loads(path.read_text()) for path in (audit_path,preflight_path,contract_path,analysis_path,stop_path))
if audit.get("status")!="pass" or audit.get("observed_rollouts")!=80 or audit.get("passing_integrity_rollouts")!=80: raise SystemExit("R3 integrity completion gate failed")
if pre.get("status")!="pass" or analysis.get("status")!="pass": raise SystemExit("R3 preflight/analysis completion gate failed")
if stop.get("status")!="pass" or stop.get("additional_large_scale_carla_required") is not False: raise SystemExit("R3 study-stop gate is absent or does not close large-scale CARLA")
def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
p={"schema_version":"r3_data_complete_v2","status":"pass","stage":"R3","formal_evidence":True,
 "result_generation":"distinction_corrected_v1","implementation_version":"corrected_joint_modes_shared_amin_v1",
 "prediction_protocol_id":"r3_corrected_formal_v3","observed_rollouts":80,"unique_treatment_keys":80,
 "scientific_outcome_taxonomy":audit["scientific_outcome_taxonomy"],"scientific_direction_never_blocks_completion":True,
 "additional_large_scale_carla_required":False,"deployment_preflight_sha256":h(preflight_path),
 "contract_sha256":h(contract_path),"matrix_audit_sha256":h(audit_path),"analysis_complete_sha256":h(analysis_path),
 "study_stop_gate_sha256":h(stop_path),"execution_source_manifest_sha256":h(source_path)}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY

"${PYTHON_BIN}" - "${R3_RESULTS}/r3_runner.log" "${R3_RESULTS}/r3_runner_frozen.log" <<'PY'
import os,sys
from pathlib import Path
source,output=map(Path,sys.argv[1:]); data=source.read_bytes(); tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_bytes(data); os.replace(tmp,output)
PY
"${PYTHON_BIN}" "${SNAPSHOT_PACKAGER}" --results-dir "${R3_RESULTS}" \
  --contract r3_run_contract.json --audit r3_corrected_matrix_audit.json --complete R3_DATA_COMPLETE.json \
  --profile r3-final --output "${SNAPSHOT}"
"${PYTHON_BIN}" "${SNAPSHOT_PACKAGER}" --verify-only --output "${SNAPSHOT}"

"${PYTHON_BIN}" - "${DATA_COMPLETE}" "${R3_RESULTS}/analysis/R3_STUDY_STOP_GATE.json" \
  "${SNAPSHOT}.json" "${SNAPSHOT}.files.json" "${R3_RESULTS}/R3_COMPLETE.json" <<'PY'
import hashlib,json,os,sys
from pathlib import Path
data,stop,snapshot,files_manifest,output=map(Path,sys.argv[1:])
d,g,s=(json.loads(path.read_text()) for path in (data,stop,snapshot))
if d.get("status")!="pass" or g.get("additional_large_scale_carla_required") is not False or s.get("status")!="pass": raise SystemExit("R3 final evidence is incomplete")
def h(path): return hashlib.sha256(path.read_bytes()).hexdigest()
p={"schema_version":"r3_complete_v2","status":"pass","stage":"R3","formal_evidence":True,
 "observed_rollouts":80,"prediction_protocol_id":"r3_corrected_formal_v3",
 "additional_large_scale_carla_required":False,"carla_experiment_program_closed":True,
 "scientific_direction_never_blocks_completion":True,"data_complete_sha256":h(data),
 "study_stop_gate_sha256":h(stop),"archive_sha256":s["archive_sha256"],
 "archive_sidecar_sha256":h(snapshot),"archive_files_manifest_sha256":h(files_manifest)}
tmp=output.with_suffix(output.suffix+".tmp"); tmp.write_text(json.dumps(p,indent=2,sort_keys=True)+"\n"); os.replace(tmp,output)
PY
echo "[$(date --iso-8601=seconds)] R3 complete"
cat "${R3_RESULTS}/R3_COMPLETE.json"
