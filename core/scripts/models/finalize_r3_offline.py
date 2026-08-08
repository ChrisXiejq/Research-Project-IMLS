#!/usr/bin/env python3
"""Finalize a complete R3 raw collection without launching CARLA.

This repair path exists for the post-collection schema-compatibility failure
where ``actor_geometry`` was added to immutable trajectory dictionaries but the
legacy metric loader forwarded every dictionary field to its dataclass.  It
preserves the original rollout commit/source manifest, verifies all 80 raw
receipts, permits only the declared loader drift, and rebuilds derived gates,
analysis and the final evidence archive entirely offline.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MODELS_DIR = Path(__file__).resolve().parent
REPO_DIR = Path(__file__).resolve().parents[3]
CORE_DIR = REPO_DIR / "core"
sys.path.insert(0, str(MODELS_DIR))

from r3_attempt_manager import valid_receipt  # noqa: E402
from summarize_r3_progress import build_summary  # noqa: E402


EXPECTED_PROTOCOL = "r3_corrected_formal_v3"
EXPECTED_ROLLOUTS = 80
ALLOWED_CRITICAL_SOURCE_DRIFT = {
    "core/scripts/evaluation/closed_loop_metrics.py": (
        "Forward-compatible deserialization only: ignore non-dataclass telemetry "
        "keys while leaving immutable pickle bytes and metric inputs unchanged."
    ),
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def atomic_copy(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    shutil.copyfile(source, temporary)
    os.replace(temporary, output)


def freeze_json(path: Path, payload: dict[str, Any], volatile: Iterable[str] = ()) -> None:
    if path.is_file():
        previous = read_json(path)
        omitted = set(volatile)
        comparable = lambda value: {key: item for key, item in value.items() if key not in omitted}
        if comparable(previous) != comparable(payload):
            raise RuntimeError(f"Frozen offline-finalization provenance drift: {path}")
        return
    atomic_json(path, payload)


def git_text(repo: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *arguments], text=True).strip()


def validate_progress(payload: dict[str, Any]) -> None:
    failures = []
    if int(payload.get("expected_rollouts", -1)) != EXPECTED_ROLLOUTS:
        failures.append("expected_rollouts")
    if int(payload.get("accepted_rollouts", -1)) != EXPECTED_ROLLOUTS:
        failures.append("accepted_rollouts")
    if int(payload.get("pending_rollouts", -1)) != 0:
        failures.append("pending_rollouts")
    if payload.get("current_or_interrupted_attempts"):
        failures.append("current_or_interrupted_attempts")
    if failures:
        raise RuntimeError(f"R3 raw collection is not offline-finalizable: {failures}")


def verify_original_source_manifest(
    repo: Path, contract: dict[str, Any], source_manifest: dict[str, Any]
) -> tuple[str, list[dict[str, Any]]]:
    collection_commit = str(contract.get("git_commit") or "")
    if not collection_commit or source_manifest.get("git_commit") != collection_commit:
        raise RuntimeError("Collection contract/source-manifest Git commit mismatch")
    if source_manifest.get("status") != "pass" or source_manifest.get("tracked_worktree_clean") is not True:
        raise RuntimeError("Original execution source manifest is not a clean passing freeze")
    git_text(repo, "cat-file", "-e", f"{collection_commit}^{{commit}}")
    current_commit = git_text(repo, "rev-parse", "HEAD")
    if git_text(repo, "status", "--porcelain", "--untracked-files=no"):
        raise RuntimeError("Offline finalization requires a clean tracked worktree")
    if subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", collection_commit, current_commit],
        check=False,
    ).returncode != 0:
        raise RuntimeError("Finalizer commit is not a descendant of the frozen collection commit")

    drift: list[dict[str, Any]] = []
    for relative, frozen in sorted((source_manifest.get("critical_sources") or {}).items()):
        expected = str((frozen or {}).get("sha256") or "")
        original = subprocess.check_output(
            ["git", "-C", str(repo), "show", f"{collection_commit}:{relative}"]
        )
        if bytes_sha256(original) != expected:
            raise RuntimeError(f"Frozen source manifest does not match original Git object: {relative}")
        current_path = repo / relative
        if not current_path.is_file():
            raise RuntimeError(f"Current finalizer checkout is missing critical source: {relative}")
        current_hash = sha256(current_path)
        if current_hash != expected:
            if relative not in ALLOWED_CRITICAL_SOURCE_DRIFT:
                raise RuntimeError(f"Unapproved critical source drift during offline finalization: {relative}")
            drift.append(
                {
                    "path": relative,
                    "collection_sha256": expected,
                    "finalizer_sha256": current_hash,
                    "classification": "derived_only_schema_compatibility",
                    "justification": ALLOWED_CRITICAL_SOURCE_DRIFT[relative],
                }
            )
    if {item["path"] for item in drift} != set(ALLOWED_CRITICAL_SOURCE_DRIFT):
        raise RuntimeError("Declared compatibility repair is absent or has unexpected scope")
    return current_commit, drift


def raw_collection_marker(
    root: Path, contract: dict[str, Any], progress: dict[str, Any]
) -> dict[str, Any]:
    entries = []
    for item in contract.get("execution_order") or []:
        cell_id = str(item["cell_id"])
        init_id = int(item["ego_init_id"])
        cell_dir = root / cell_id
        receipt_path = cell_dir / f"R3_ROLLOUT_{init_id}_COMPLETE.json"
        if not valid_receipt(cell_dir, cell_id, init_id):
            raise RuntimeError(f"Immutable raw receipt failed verification: {cell_id}/init{init_id}")
        receipt = read_json(receipt_path)
        entries.append(
            {
                "cell_id": cell_id,
                "ego_init_id": init_id,
                "receipt": receipt_path.relative_to(root).as_posix(),
                "receipt_sha256": sha256(receipt_path),
                "raw_evidence_sha256": receipt["raw_evidence_sha256"],
                "accepted_attempt": int(receipt["accepted_attempt"]),
            }
        )
    if len(entries) != EXPECTED_ROLLOUTS or len(
        {(item["cell_id"], item["ego_init_id"]) for item in entries}
    ) != EXPECTED_ROLLOUTS:
        raise RuntimeError("Raw collection treatment-key coverage is not exactly 80/80")
    aggregate = bytes_sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return {
        "schema_version": "r3_raw_collection_complete_v1",
        "status": "pass",
        "stage": "R3_raw_collection",
        "prediction_protocol_id": EXPECTED_PROTOCOL,
        "collection_git_commit": contract["git_commit"],
        "expected_rollouts": EXPECTED_ROLLOUTS,
        "accepted_rollouts": len(entries),
        "pending_rollouts": 0,
        "failed_infrastructure_attempts_retained": int(progress.get("failed_attempts", 0)),
        "unique_treatment_keys": len(entries),
        "receipt_manifest_sha256": aggregate,
        "scientific_rollouts_launched_by_offline_finalizer": 0,
        "entries": entries,
        "created_at_utc": now_utc(),
    }


class Tee:
    def __init__(self, *streams: Any) -> None:
        self.streams = streams

    def write(self, value: str) -> int:
        for stream in self.streams:
            stream.write(value)
            stream.flush()
        return len(value)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def run_command(arguments: list[str], *, allowed: set[int] = {0}) -> int:
    print("+", " ".join(arguments), flush=True)
    process = subprocess.Popen(
        arguments,
        cwd=REPO_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
    returncode = process.wait()
    if returncode not in allowed:
        raise RuntimeError(f"Command failed with exit {returncode}: {' '.join(arguments)}")
    return returncode


def check_existing_complete(root: Path, python_bin: str) -> bool:
    complete_path = root / "R3_COMPLETE.json"
    snapshot = root / "r3_corrected_formal_snapshot.tar.gz"
    if not complete_path.is_file():
        return False
    try:
        complete = read_json(complete_path)
        data = root / "R3_DATA_COMPLETE.json"
        stop = root / "analysis/R3_STUDY_STOP_GATE.json"
        sidecar = Path(str(snapshot) + ".json")
        files = Path(str(snapshot) + ".files.json")
        valid = (
            complete.get("status") == "pass"
            and complete.get("additional_large_scale_carla_required") is False
            and complete.get("data_complete_sha256") == sha256(data)
            and complete.get("study_stop_gate_sha256") == sha256(stop)
            and complete.get("archive_sidecar_sha256") == sha256(sidecar)
            and complete.get("archive_files_manifest_sha256") == sha256(files)
            and read_json(sidecar).get("archive_sha256") == complete.get("archive_sha256")
        )
    except Exception:
        return False
    if not valid:
        return False
    run_command(
        [
            python_bin,
            str(MODELS_DIR / "package_closed_loop_snapshot.py"),
            "--verify-only",
            "--output",
            str(snapshot),
        ]
    )
    print(json.dumps(complete, indent=2, sort_keys=True))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--python-bin", default=sys.executable)
    args = parser.parse_args()
    root = args.results_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    live_log = root / "offline_finalizer_live.log"
    log_handle = live_log.open("a", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.__stdout__, log_handle)
    sys.stderr = Tee(sys.__stderr__, log_handle)

    lock_handle = (root / ".offline_finalizer.lock").open("a+")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise SystemExit("Another offline R3 finalizer is active") from error

    runner_pid = root / ".runner_lock/pid"
    if runner_pid.is_file():
        try:
            pid = int(runner_pid.read_text().strip())
            os.kill(pid, 0)
            command_line = (Path("/proc") / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ")
        except (OSError, ValueError):
            pass
        else:
            if b"run_r3_corrected_formal_matrix.sh" in command_line:
                raise RuntimeError("CARLA collection runner is still active; offline finalization refused")

    print(f"[{now_utc()}] R3 offline finalization started")
    if check_existing_complete(root, args.python_bin):
        print("R3 already complete; archive and final marker verified")
        return

    contract_path = root / "r3_run_contract.json"
    source_manifest_path = root / "r3_execution_source_manifest.json"
    preflight_path = root / "R3_PREFLIGHT_COMPLETE.json"
    for required in (contract_path, source_manifest_path, preflight_path):
        if not required.is_file():
            raise FileNotFoundError(required)
    contract = read_json(contract_path)
    source_manifest = read_json(source_manifest_path)
    preflight = read_json(preflight_path)
    if (
        contract.get("status") != "frozen"
        or contract.get("prediction_protocol_id") != EXPECTED_PROTOCOL
        or int(contract.get("expected_rollouts", -1)) != EXPECTED_ROLLOUTS
    ):
        raise RuntimeError("R3 v3 frozen contract is invalid")
    if preflight.get("status") != "pass" or int(preflight.get("scientific_rollouts_launched", -1)) != 0:
        raise RuntimeError("R3 preflight completion marker is invalid")

    progress = build_summary(root, contract_path)
    validate_progress(progress)
    current_commit, source_drift = verify_original_source_manifest(
        REPO_DIR, contract, source_manifest
    )

    raw_marker_path = root / "R3_RAW_COLLECTION_COMPLETE.json"
    raw_marker = raw_collection_marker(root, contract, progress)
    freeze_json(raw_marker_path, raw_marker, volatile={"created_at_utc"})

    frozen_finalizer_source = root / "r3_offline_finalizer_source.py"
    frozen_loader_source = root / "r3_closed_loop_metrics_compat_source.py"
    atomic_copy(Path(__file__).resolve(), frozen_finalizer_source)
    atomic_copy(
        REPO_DIR / "core/scripts/evaluation/closed_loop_metrics.py",
        frozen_loader_source,
    )
    provenance_path = root / "r3_offline_finalization_provenance.json"
    provenance = {
        "schema_version": "r3_offline_finalization_provenance_v1",
        "status": "pass",
        "classification": "authorized_derived_only_repair",
        "repair_reason": "legacy_metric_loader_rejected_appended_actor_geometry_metadata",
        "raw_collection_mutation_permitted": False,
        "carla_or_scientific_rollouts_permitted": False,
        "collection_git_commit": contract["git_commit"],
        "finalizer_git_commit": current_commit,
        "collection_source_manifest": source_manifest_path.name,
        "collection_source_manifest_sha256": sha256(source_manifest_path),
        "raw_collection_marker": raw_marker_path.name,
        "raw_collection_marker_sha256": sha256(raw_marker_path),
        "critical_source_drift": source_drift,
        "frozen_repair_sources": {
            frozen_finalizer_source.name: sha256(frozen_finalizer_source),
            frozen_loader_source.name: sha256(frozen_loader_source),
        },
        "created_at_utc": now_utc(),
    }
    freeze_json(provenance_path, provenance, volatile={"created_at_utc"})

    outcomes = []
    for cell in contract["cells"]:
        cell_id = str(cell["cell_id"])
        cell_dir = root / cell_id
        required_policy = (
            "smpc_var_risk" if cell["risk_policy"] == "adaptive" else "smpc_fixed_risk"
        )
        gate_code = run_command(
            [
                args.python_bin,
                str(CORE_DIR / "scripts/postcarla_trajectory_gate.py"),
                str(cell_dir),
                "--required-policies",
                required_policy,
                "--require-fixed-geometry-yield",
                "--footprint-margin-m",
                "0.25",
                "--footprint-margins-m",
                "0.0,0.25,0.35,0.50",
                "--conflict-radius-m",
                "4.0",
                "--clearance-tolerance-s",
                "0.2",
            ],
            allowed={0, 1},
        )
        run_command(
            [
                args.python_bin,
                str(CORE_DIR / "scripts/compute_scenario_results.py"),
                "--results_dir",
                str(cell_dir),
                "--compute_metrics",
            ]
        )
        run_command(
            [
                args.python_bin,
                str(CORE_DIR / "scripts/risk_by_conflict_distance.py"),
                str(cell_dir),
            ]
        )
        gate_path = cell_dir / "postcarla_trajectory_gate.json"
        metrics_path = cell_dir / "df_full.csv"
        risk_path = cell_dir / "risk_by_conflict_distance_summary.json"
        for required in (gate_path, metrics_path, risk_path):
            if not required.is_file():
                raise RuntimeError(f"Missing derived cell evidence: {required}")
        outcomes.append(
            {
                "cell_id": cell_id,
                "postcarla_exit_code": gate_code,
                "postcarla_sha256": sha256(gate_path),
                "metrics_sha256": sha256(metrics_path),
                "risk_summary_sha256": sha256(risk_path),
            }
        )

    # Recheck all immutable receipts after every derived file has been written.
    postprocess_progress = build_summary(root, contract_path)
    validate_progress(postprocess_progress)
    raw_after = raw_collection_marker(root, contract, postprocess_progress)
    if raw_after["receipt_manifest_sha256"] != read_json(raw_marker_path)["receipt_manifest_sha256"]:
        raise RuntimeError("Immutable raw receipt manifest changed during offline post-processing")

    audit_path = root / "r3_corrected_matrix_audit.json"
    run_command(
        [
            args.python_bin,
            str(MODELS_DIR / "audit_r3_corrected_matrix.py"),
            "--results-dir",
            str(root),
            "--contract-json",
            str(contract_path),
            "--output-json",
            str(audit_path),
        ]
    )
    analysis_dir = root / "analysis"
    analysis_contract = root / "_frozen_contracts/M0_R3_ANALYSIS_CONTRACT_v2.json"
    run_command(
        [
            args.python_bin,
            str(MODELS_DIR / "analyze_r3_corrected_formal.py"),
            "--results-dir",
            str(root),
            "--contract-json",
            str(contract_path),
            "--analysis-contract",
            str(analysis_contract),
            "--output-dir",
            str(analysis_dir),
        ]
    )

    audit = read_json(audit_path)
    analysis_complete_path = analysis_dir / "R3_ANALYSIS_COMPLETE.json"
    stop_path = analysis_dir / "R3_STUDY_STOP_GATE.json"
    analysis_complete = read_json(analysis_complete_path)
    stop = read_json(stop_path)
    if (
        audit.get("status") != "pass"
        or int(audit.get("observed_rollouts", -1)) != EXPECTED_ROLLOUTS
        or int(audit.get("passing_integrity_rollouts", -1)) != EXPECTED_ROLLOUTS
        or analysis_complete.get("status") != "pass"
        or stop.get("status") != "pass"
        or stop.get("additional_large_scale_carla_required") is not False
    ):
        raise RuntimeError("R3 audit, analysis, or study-stop gate did not pass")

    sys.stdout.flush()
    sys.stderr.flush()
    runner_log = root / "r3_runner.log"
    if not runner_log.is_file():
        raise FileNotFoundError(runner_log)
    atomic_copy(runner_log, root / "r3_runner_frozen.log")
    atomic_copy(live_log, root / "r3_offline_finalizer_frozen.log")

    report_path = root / "r3_offline_finalization_report.json"
    report = {
        "schema_version": "r3_offline_finalization_report_v1",
        "status": "pass",
        "cells_postprocessed": len(outcomes),
        "scientific_rollouts_launched": 0,
        "raw_receipt_manifest_unchanged": True,
        "postcarla_nonzero_is_scientific_not_integrity": True,
        "cell_outputs": outcomes,
        "matrix_audit_sha256": sha256(audit_path),
        "analysis_complete_sha256": sha256(analysis_complete_path),
        "study_stop_gate_sha256": sha256(stop_path),
        "runner_log_sha256": sha256(root / "r3_runner_frozen.log"),
        "offline_finalizer_log_sha256": sha256(root / "r3_offline_finalizer_frozen.log"),
        "completed_at_utc": now_utc(),
    }
    atomic_json(report_path, report)

    data_complete_path = root / "R3_DATA_COMPLETE.json"
    data_complete = {
        "schema_version": "r3_data_complete_v3",
        "status": "pass",
        "stage": "R3",
        "formal_evidence": True,
        "result_generation": "distinction_corrected_v1",
        "implementation_version": "corrected_joint_modes_shared_amin_v1",
        "prediction_protocol_id": EXPECTED_PROTOCOL,
        "collection_git_commit": contract["git_commit"],
        "offline_finalizer_git_commit": current_commit,
        "observed_rollouts": EXPECTED_ROLLOUTS,
        "unique_treatment_keys": EXPECTED_ROLLOUTS,
        "scientific_outcome_taxonomy": audit["scientific_outcome_taxonomy"],
        "scientific_direction_never_blocks_completion": True,
        "additional_large_scale_carla_required": False,
        "raw_collection_complete_sha256": sha256(raw_marker_path),
        "offline_finalization_provenance_sha256": sha256(provenance_path),
        "offline_finalization_report_sha256": sha256(report_path),
        "deployment_preflight_sha256": sha256(root / "r3_deployment_preflight.json"),
        "contract_sha256": sha256(contract_path),
        "matrix_audit_sha256": sha256(audit_path),
        "analysis_complete_sha256": sha256(analysis_complete_path),
        "study_stop_gate_sha256": sha256(stop_path),
        "execution_source_manifest_sha256": sha256(source_manifest_path),
    }
    atomic_json(data_complete_path, data_complete)

    snapshot = root / "r3_corrected_formal_snapshot.tar.gz"
    evidence = [
        raw_marker_path,
        provenance_path,
        report_path,
        frozen_finalizer_source,
        frozen_loader_source,
        root / "r3_offline_finalizer_frozen.log",
    ]
    package_command = [
        args.python_bin,
        str(MODELS_DIR / "package_closed_loop_snapshot.py"),
        "--results-dir",
        str(root),
        "--contract",
        contract_path.name,
        "--audit",
        audit_path.name,
        "--complete",
        data_complete_path.name,
        "--profile",
        "r3-final",
        "--output",
        str(snapshot),
    ]
    for path in evidence:
        package_command.extend(["--evidence", path.relative_to(root).as_posix()])
    run_command(package_command)
    run_command(
        [
            args.python_bin,
            str(MODELS_DIR / "package_closed_loop_snapshot.py"),
            "--verify-only",
            "--output",
            str(snapshot),
        ]
    )

    snapshot_sidecar = Path(str(snapshot) + ".json")
    files_manifest = Path(str(snapshot) + ".files.json")
    snapshot_payload = read_json(snapshot_sidecar)
    complete = {
        "schema_version": "r3_complete_v3",
        "status": "pass",
        "stage": "R3",
        "formal_evidence": True,
        "observed_rollouts": EXPECTED_ROLLOUTS,
        "prediction_protocol_id": EXPECTED_PROTOCOL,
        "collection_git_commit": contract["git_commit"],
        "offline_finalizer_git_commit": current_commit,
        "additional_large_scale_carla_required": False,
        "carla_experiment_program_closed": True,
        "scientific_direction_never_blocks_completion": True,
        "raw_collection_complete_sha256": sha256(raw_marker_path),
        "offline_finalization_provenance_sha256": sha256(provenance_path),
        "offline_finalization_report_sha256": sha256(report_path),
        "data_complete_sha256": sha256(data_complete_path),
        "study_stop_gate_sha256": sha256(stop_path),
        "archive_sha256": snapshot_payload["archive_sha256"],
        "archive_sidecar_sha256": sha256(snapshot_sidecar),
        "archive_files_manifest_sha256": sha256(files_manifest),
    }
    atomic_json(root / "R3_COMPLETE.json", complete)
    print(f"[{now_utc()}] R3 offline finalization complete")
    print(json.dumps(complete, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
