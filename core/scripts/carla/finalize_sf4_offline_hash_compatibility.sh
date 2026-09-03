#!/usr/bin/env bash
set -Eeuo pipefail

# Offline-only SF4 finalization.  This script never connects to CARLA and never
# launches a rollout.  It preserves the frozen experiment sources and invokes
# the frozen analyser through an audited dual-hash compatibility proof.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-python}"
SF4_RESULTS="${SF4_RESULTS:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/distinction_v1/sf4_supervisor_behavioural_authority_v1}"
PREREG_JSON="${PREREG_JSON:-${REPO_DIR}/core/scripts/models/protocols/sf4_supervisor_behavioural_authority_prereg.json}"
CONTRACT="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_run_contract.json"
DEPLOYMENT_PREFLIGHT="${SF4_RESULTS}/sf4_b1_deployment_preflight.json"
SPAWN_PREFLIGHT="${SF4_RESULTS}/sf4_town05_spawn_preflight.json"
ANALYSIS_DIR="${SF4_RESULTS}/analysis"
COMPAT_ANALYZER="${MODELS_DIR}/finalize_sf4_offline_hash_compatibility.py"
FULL_PACKAGER="${MODELS_DIR}/package_sf4_full_raw_snapshot.py"
PACKAGER="${MODELS_DIR}/package_sf4_compact_evidence.py"
RECOVERY_PREPARE="${MODELS_DIR}/prepare_sf4_infrastructure_recovery.py"

for required in \
  "${CONTRACT}" "${DEPLOYMENT_PREFLIGHT}" "${SPAWN_PREFLIGHT}" \
  "${PREREG_JSON}" "${COMPAT_ANALYZER}" "${FULL_PACKAGER}" \
  "${PACKAGER}" "${RECOVERY_PREPARE}"; do
  test -e "${required}" || { echo "Missing SF4 offline-finalization asset: ${required}" >&2; exit 2; }
done
if [[ -n "$(git -C "${REPO_DIR}" status --porcelain --untracked-files=no)" ]]; then
  echo "SF4 offline finalization requires a clean tracked Git worktree" >&2
  exit 3
fi

mkdir -p "${SF4_RESULTS}"
exec > >(tee -a "${SF4_RESULTS}/sf4_offline_finalization.log") 2>&1
LOCK="${SF4_RESULTS}/.offline_finalization_lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  if [[ -f "${LOCK}/pid" ]] && kill -0 "$(cat "${LOCK}/pid")" 2>/dev/null; then
    echo "Another SF4 offline finalizer is active: PID $(cat "${LOCK}/pid")" >&2
    exit 4
  fi
  rm -f "${LOCK}/pid"
  rmdir "${LOCK}"
  mkdir "${LOCK}"
fi
echo "$$" > "${LOCK}/pid"
cleanup() { rm -f "${LOCK}/pid"; rmdir "${LOCK}" 2>/dev/null || true; }
trap cleanup EXIT

mapfile -t AMENDMENTS < <(find "${SF4_RESULTS}" -path '*/_attempts/init_*/SF4_INFRASTRUCTURE_RECOVERY_AMENDMENT.json' -type f | sort)
if ((${#AMENDMENTS[@]} != 1)); then
  echo "Expected exactly one frozen SF4 recovery amendment; found ${#AMENDMENTS[@]}" >&2
  exit 5
fi
AMENDMENT="${AMENDMENTS[0]}"

echo "[$(date --iso-8601=seconds)] SF4 offline compatibility analysis start"
"${PYTHON_BIN}" "${COMPAT_ANALYZER}" \
  --results-dir "${SF4_RESULTS}" --repo "${REPO_DIR}" \
  --contract "${CONTRACT}" --prereg "${PREREG_JSON}" \
  --deployment-preflight "${DEPLOYMENT_PREFLIGHT}" \
  --output-dir "${ANALYSIS_DIR}"

FULL_RAW_SNAPSHOT="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz"
"${PYTHON_BIN}" "${FULL_PACKAGER}" --results-dir "${SF4_RESULTS}" \
  --prereg "${PREREG_JSON}" --output "${FULL_RAW_SNAPSHOT}"
"${PYTHON_BIN}" "${FULL_PACKAGER}" --verify-only --output "${FULL_RAW_SNAPSHOT}"
FULL_RAW_MARKER="${SF4_RESULTS}/SF4_FULL_RAW_SNAPSHOT_COMPLETE.json"

"${PYTHON_BIN}" "${RECOVERY_PREPARE}" complete \
  --results-dir "${SF4_RESULTS}" --contract "${CONTRACT}" \
  --prereg "${PREREG_JSON}" --spawn "${SPAWN_PREFLIGHT}" \
  --deployment "${DEPLOYMENT_PREFLIGHT}" \
  --analysis "${ANALYSIS_DIR}/SF4_ANALYSIS_COMPLETE.json" \
  --archive "${FULL_RAW_SNAPSHOT}" --full-marker "${FULL_RAW_MARKER}" \
  --amendment "${AMENDMENT}"

COMPACT_PACKAGE="${SF4_RESULTS}/sf4_supervisor_behavioural_authority_compact_evidence.tar.gz"
"${PYTHON_BIN}" "${PACKAGER}" --results-dir "${SF4_RESULTS}" --output "${COMPACT_PACKAGE}"
"${PYTHON_BIN}" "${PACKAGER}" --verify-only --output "${COMPACT_PACKAGE}"
echo "[$(date --iso-8601=seconds)] SF4 offline finalization complete"
cat "${SF4_RESULTS}/SF4_COMPLETE.json"
