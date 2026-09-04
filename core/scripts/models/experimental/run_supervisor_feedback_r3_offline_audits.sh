#!/usr/bin/env bash
set -euo pipefail

# Run the two supervisor-feedback audits that require the archived R3 raw logs.
# This script never starts CARLA and never changes the frozen R3 archive.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

R3_RESULTS_ROOT="${R3_RESULTS_ROOT:-${EXPERIMENT_RESULTS_ROOT:-/path/to/results}/give_way_transformer/distinction_v1/r3_corrected_formal_v3}"
R3_ARCHIVE="${R3_ARCHIVE:-${R3_RESULTS_ROOT}/r3_corrected_formal_snapshot.tar.gz}"
SF_RESULTS_ROOT="${SF_RESULTS_ROOT:-${R3_RESULTS_ROOT}/supervisor_feedback_v1/r3_offline}"
SF_WORKSPACE_ROOT="${SF_WORKSPACE_ROOT:-${R3_RESULTS_ROOT}/.supervisor_feedback_workspace}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

CANONICAL_R3_DIR="${REPO_ROOT}/docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3"
MATRIX_AUDIT="${CANONICAL_R3_DIR}/r3_corrected_matrix_audit.json"
ROLLOUT_OUTCOMES="${CANONICAL_R3_DIR}/analysis/r3_rollout_outcomes.csv"
SNAPSHOT_RECEIPT="${CANONICAL_R3_DIR}/r3_corrected_formal_snapshot.tar.gz.json"
SNAPSHOT_FILES_MANIFEST="${CANONICAL_R3_DIR}/r3_corrected_formal_snapshot.tar.gz.files.json"

for required in \
  "${R3_ARCHIVE}" \
  "${MATRIX_AUDIT}" \
  "${ROLLOUT_OUTCOMES}" \
  "${SNAPSHOT_RECEIPT}" \
  "${SNAPSHOT_FILES_MANIFEST}"; do
  if [[ ! -f "${required}" ]]; then
    echo "Missing required evidence: ${required}" >&2
    exit 2
  fi
done

mkdir -p "${SF_RESULTS_ROOT}" "${SF_WORKSPACE_ROOT}"

EXPECTED_ARCHIVE_SHA="$(${PYTHON_BIN} - "${SNAPSHOT_RECEIPT}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(payload["archive_sha256"])
PY
)"

OBSERVED_ARCHIVE_SHA="$(${PYTHON_BIN} - "${R3_ARCHIVE}" <<'PY'
import hashlib
import sys
from pathlib import Path

digest = hashlib.sha256()
with Path(sys.argv[1]).open("rb") as handle:
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
)"

if [[ "${OBSERVED_ARCHIVE_SHA}" != "${EXPECTED_ARCHIVE_SHA}" ]]; then
  echo "R3 archive SHA-256 mismatch" >&2
  echo "expected=${EXPECTED_ARCHIVE_SHA}" >&2
  echo "observed=${OBSERVED_ARCHIVE_SHA}" >&2
  exit 3
fi

EXTRACT_ROOT="${SF_WORKSPACE_ROOT}/snapshot_${OBSERVED_ARCHIVE_SHA:0:12}"
EXTRACT_MARKER="${EXTRACT_ROOT}/.SUPERVISOR_FEEDBACK_EXTRACT_COMPLETE.json"
mkdir -p "${EXTRACT_ROOT}"

if [[ ! -f "${EXTRACT_MARKER}" ]]; then
  # tarfile data filtering is unavailable in the server's Python 3.8, so
  # validate every member explicitly before extraction. Interrupted extraction
  # is safe to rerun because the source archive is immutable and hash-bound.
  "${PYTHON_BIN}" - "${R3_ARCHIVE}" "${EXTRACT_ROOT}" "${OBSERVED_ARCHIVE_SHA}" <<'PY'
import json
import os
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

archive = Path(sys.argv[1]).resolve()
destination = Path(sys.argv[2]).resolve()
archive_sha = sys.argv[3]
with tarfile.open(archive, "r:gz") as bundle:
    members = bundle.getmembers()
    for member in members:
        pure = PurePosixPath(member.name)
        if pure.is_absolute() or ".." in pure.parts:
            raise SystemExit(f"Unsafe archive member: {member.name!r}")
        if member.issym() or member.islnk() or member.isdev():
            raise SystemExit(f"Unsupported archive member type: {member.name!r}")
        resolved = (destination / member.name).resolve()
        if os.path.commonpath([str(destination), str(resolved)]) != str(destination):
            raise SystemExit(f"Archive member escapes destination: {member.name!r}")
    bundle.extractall(destination, members=members)

marker = {
    "schema_version": "supervisor_feedback_extract_v1",
    "status": "pass",
    "archive": str(archive),
    "archive_sha256": archive_sha,
    "members": len(members),
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
}
temporary = destination / ".SUPERVISOR_FEEDBACK_EXTRACT_COMPLETE.json.tmp"
final = destination / ".SUPERVISOR_FEEDBACK_EXTRACT_COMPLETE.json"
temporary.write_text(json.dumps(marker, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, final)
PY
else
  MARKER_SHA="$(${PYTHON_BIN} - "${EXTRACT_MARKER}" <<'PY'
import json
import sys
from pathlib import Path
print(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["archive_sha256"])
PY
)"
  if [[ "${MARKER_SHA}" != "${OBSERVED_ARCHIVE_SHA}" ]]; then
    echo "Extraction marker does not match the immutable archive" >&2
    exit 4
  fi
fi

BEHAVIOUR_OUTPUT="${SF_RESULTS_ROOT}/01_behaviour"
COST_OUTPUT="${SF_RESULTS_ROOT}/02_cost_feasibility"
mkdir -p "${BEHAVIOUR_OUTPUT}" "${COST_OUTPUT}"

"${PYTHON_BIN}" "${SCRIPT_DIR}/analysis/analyze_supervisor_feedback_behaviour.py" \
  --results-root "${EXTRACT_ROOT}" \
  --matrix-audit "${MATRIX_AUDIT}" \
  --output-dir "${BEHAVIOUR_OUTPUT}" \
  --fps 20 \
  --stop-speed-mps 0.15 \
  --resume-speed-mps 0.8 \
  --consecutive-steps 3 \
  --expected-rollouts 80

"${PYTHON_BIN}" "${SCRIPT_DIR}/analysis/analyze_supervisor_feedback_cost_feasibility.py" \
  --matrix-audit "${MATRIX_AUDIT}" \
  --rollout-outcomes "${ROLLOUT_OUTCOMES}" \
  --output-dir "${COST_OUTPUT}" \
  --raw-root "${EXTRACT_ROOT}" \
  --snapshot-files-manifest "${SNAPSHOT_FILES_MANIFEST}"

"${PYTHON_BIN}" - \
  "${SF_RESULTS_ROOT}" \
  "${OBSERVED_ARCHIVE_SHA}" \
  "${BEHAVIOUR_OUTPUT}/SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json" \
  "${COST_OUTPUT}/SUPERVISOR_FEEDBACK_02_COMPLETE.json" \
  "$(git -C "${REPO_ROOT}" rev-parse HEAD)" \
  "${SCRIPT_DIR}/analysis/analyze_supervisor_feedback_behaviour.py" \
  "${SCRIPT_DIR}/analysis/analyze_supervisor_feedback_cost_feasibility.py" \
  "${BASH_SOURCE[0]}" \
  "${MATRIX_AUDIT}" <<'PY'
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

root = Path(sys.argv[1]).resolve()
archive_sha = sys.argv[2]
behaviour = Path(sys.argv[3]).resolve()
cost = Path(sys.argv[4]).resolve()
source_commit = sys.argv[5]
behaviour_source = Path(sys.argv[6]).resolve()
cost_source = Path(sys.argv[7]).resolve()
runner_source = Path(sys.argv[8]).resolve()
matrix_audit = Path(sys.argv[9]).resolve()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

statuses = {}
for path in (behaviour, cost):
    value = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    status = value.get("status")
    if not isinstance(status, str) or not status.startswith("pass"):
        raise SystemExit(f"Audit receipt missing or non-passing: {path}")
    if path == cost and (
        value.get("raw_taxonomy_status") != "pass"
        or value.get("deadline_evaluation_status") != "evaluated"
        or value.get("observed_rollouts") != 80
    ):
        raise SystemExit(
            "Cost receipt passed only its aggregate layer; the required raw "
            f"taxonomy/deadline audit is incomplete: {path}"
        )
    statuses[str(path.relative_to(root))] = status

behaviour_payload = json.loads(behaviour.read_text(encoding="utf-8"))
expected_behaviour_sources = {
    "core/scripts/models/analysis/analyze_supervisor_feedback_behaviour.py": digest(behaviour_source),
    "core/scripts/models/experimental/run_supervisor_feedback_r3_offline_audits.sh": digest(runner_source),
    "matrix_audit": digest(matrix_audit),
}
if behaviour_payload.get("source_sha256") != expected_behaviour_sources:
    raise SystemExit("Behaviour receipt source hashes do not match the executing sources")

payload = {
    "schema_version": "supervisor_feedback_r3_offline_complete_v1",
    "status": (
        "pass" if all(value == "pass" for value in statuses.values())
        else "pass_with_missing_mechanism_events"
    ),
    "created_at_utc": datetime.now(timezone.utc).isoformat(),
    "source_git_commit": source_commit,
    "source_r3_archive_sha256": archive_sha,
    "receipts": {
        str(behaviour.relative_to(root)): digest(behaviour),
        str(cost.relative_to(root)): digest(cost),
    },
    "receipt_statuses": statuses,
    "source_sha256": {
        "core/scripts/models/analysis/analyze_supervisor_feedback_behaviour.py": digest(behaviour_source),
        "core/scripts/models/analysis/analyze_supervisor_feedback_cost_feasibility.py": digest(cost_source),
        "core/scripts/models/experimental/run_supervisor_feedback_r3_offline_audits.sh": digest(runner_source),
        "r3_corrected_matrix_audit.json": digest(matrix_audit),
    },
    "carla_started": False,
    "raw_r3_modified": False,
}
temporary = root / "SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json.tmp"
final = root / "SUPERVISOR_FEEDBACK_R3_OFFLINE_COMPLETE.json"
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, final)
PY

PACKAGE_PARENT="$(dirname "${SF_RESULTS_ROOT}")"
PACKAGE_PATH="${PACKAGE_PARENT}/supervisor_feedback_r3_offline_results.tar.gz"
tar -czf "${PACKAGE_PATH}.tmp" -C "${SF_RESULTS_ROOT}" .
mv "${PACKAGE_PATH}.tmp" "${PACKAGE_PATH}"
"${PYTHON_BIN}" - "${PACKAGE_PATH}" <<'PY'
import hashlib
import json
import os
import sys
from pathlib import Path

path = Path(sys.argv[1]).resolve()
digest = hashlib.sha256(path.read_bytes()).hexdigest()
payload = {"status": "pass", "archive": str(path), "bytes": path.stat().st_size, "sha256": digest}
temporary = path.with_suffix(path.suffix + ".json.tmp")
final = path.with_suffix(path.suffix + ".json")
temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
os.replace(temporary, final)
print(json.dumps(payload, indent=2, sort_keys=True))
PY

echo "Supervisor-feedback R3 offline audits complete."
echo "Results: ${SF_RESULTS_ROOT}"
echo "Package: ${PACKAGE_PATH}"
