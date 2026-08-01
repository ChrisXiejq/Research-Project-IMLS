#!/usr/bin/env bash
set -Eeuo pipefail

# Finalize an already completed Day 9 rollout matrix without starting CARLA
# scenarios again. This is intentionally separate from the frozen run contract:
# it may only regenerate the audit, completion marker, and compact snapshot.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_DIR="$(cd "${CORE_DIR}/.." && pwd)"
MODELS_DIR="${CORE_DIR}/scripts/models"
PYTHON_BIN="${PYTHON_BIN:-/root/miniconda3/envs/carla_modern/bin/python}"
DAY9_RESULTS="${DAY9_RESULTS:-/root/autodl-tmp/results/give_way_transformer/day9/day9_smoke_v1}"

CONTRACT="${DAY9_RESULTS}/day9_run_contract.json"
PREFLIGHT="${DAY9_RESULTS}/day9_deployment_preflight.json"
AUDIT="${DAY9_RESULTS}/day9_smoke_audit.json"
PROVENANCE="${DAY9_RESULTS}/day9_finalization_provenance.json"
COMPLETE="${DAY9_RESULTS}/DAY9_COMPLETE.json"
ARCHIVE="${DAY9_RESULTS}/day9_smoke_snapshot.tar.gz"

for required in "${CONTRACT}" "${PREFLIGHT}"; do
  test -f "${required}" || { echo "Missing Day 9 artifact: ${required}" >&2; exit 2; }
done

"${PYTHON_BIN}" "${MODELS_DIR}/audit_day9_smoke.py" \
  --results-dir "${DAY9_RESULTS}" \
  --contract-json "${CONTRACT}" \
  --output-json "${AUDIT}"

"${PYTHON_BIN}" - \
  "${CONTRACT}" "${PREFLIGHT}" "${AUDIT}" "${PROVENANCE}" "${COMPLETE}" \
  "${MODELS_DIR}/audit_day9_smoke.py" "${REPO_DIR}" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

(
    contract_path,
    preflight_path,
    audit_path,
    provenance_path,
    complete_path,
    audit_script,
    repo_dir,
) = map(Path, sys.argv[1:])


def read(path):
    return json.loads(path.read_text())


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path, payload):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


contract = read(contract_path)
preflight = read(preflight_path)
audit = read(audit_path)
if contract.get("status") != "frozen":
    raise SystemExit("Day 9 contract is not frozen")
if preflight.get("status") != "pass" or audit.get("status") != "pass":
    raise SystemExit("Day 9 finalization gate failed")
if audit.get("observed_arms") != 8 or audit.get("expected_arms") != 8:
    raise SystemExit("Day 9 finalization requires exactly 8 audited arms")

provenance = {
    "schema_version": "day9_finalization_provenance_v1",
    "status": "pass",
    "finalization_only": True,
    "raw_rollouts_reused": True,
    "original_contract_git_commit": contract.get("git_commit"),
    "finalizer_git_commit": subprocess.check_output(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"], text=True
    ).strip(),
    "compatibility_reason": (
        "Legacy Day 9 manifests serialized boolean warmup_passed=True as integer 1; "
        "the corrected audit accepts only canonical true or exact integer 1."
    ),
    "contract_sha256": sha256(contract_path),
    "preflight_sha256": sha256(preflight_path),
    "audit_sha256": sha256(audit_path),
    "audit_script_sha256": sha256(audit_script),
}
atomic_json(provenance_path, provenance)

complete = {
    "schema_version": "day9_complete_v1",
    "status": "pass",
    "smoke_only_not_formal_evidence": True,
    "selected_variant": "B1",
    "selected_seed": 37,
    "observed_arms": audit["observed_arms"],
    "deployment_preflight_sha256": sha256(preflight_path),
    "smoke_audit_sha256": sha256(audit_path),
    "finalization_provenance_sha256": sha256(provenance_path),
}
atomic_json(complete_path, complete)
PY

"${PYTHON_BIN}" "${MODELS_DIR}/package_day9_smoke_snapshot.py" \
  --results-dir "${DAY9_RESULTS}" \
  --output "${ARCHIVE}"

echo "[$(date --iso-8601=seconds)] Day 9 finalization complete"
cat "${COMPLETE}"
