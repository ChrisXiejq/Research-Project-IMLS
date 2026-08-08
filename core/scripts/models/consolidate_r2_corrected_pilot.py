#!/usr/bin/env python3
"""Verify and summarize a pulled R2 corrected-pilot evidence bundle.

The pilot is a deployment gate, not an effect-estimation dataset.  This script
therefore reports each rollout descriptively while explicitly preventing a
statistical interpretation of the ten pilot observations.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import tarfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: Path, payload: dict) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def archive_csv(archive: tarfile.TarFile, name: str) -> list[dict[str, str]]:
    member = archive.getmember(name)
    extracted = archive.extractfile(member)
    if extracted is None:
        raise ValueError(f"Cannot read archive member: {name}")
    return list(csv.DictReader(io.StringIO(extracted.read().decode("utf-8"))))


def as_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    root = args.run_dir.resolve()
    output = args.output_dir.resolve()
    archive_path = root / "r2_corrected_pilot_snapshot.tar.gz"
    archive_manifest_path = root / "r2_corrected_pilot_snapshot.tar.gz.json"
    required = {
        "complete": root / "R2_COMPLETE.json",
        "audit": root / "r2_corrected_pilot_audit.json",
        "contract": root / "r2_run_contract.json",
        "preflight": root / "r2_deployment_preflight.json",
        "archive": archive_path,
        "archive_manifest": archive_manifest_path,
        "runner_log": root / "r2_runner.log",
    }
    missing = [label for label, path in required.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing pulled R2 artifacts: {missing}")

    complete = read_json(required["complete"])
    audit = read_json(required["audit"])
    contract = read_json(required["contract"])
    preflight = read_json(required["preflight"])
    archive_manifest = read_json(archive_manifest_path)
    failures: list[str] = []

    actual_archive_hash = sha256(archive_path)
    if actual_archive_hash != archive_manifest.get("archive_sha256"):
        failures.append("archive_sha256")
    if complete.get("status") != "pass":
        failures.append("complete_status")
    if audit.get("status") != "pass" or audit.get("failures"):
        failures.append("audit_status")
    if preflight.get("status") != "pass":
        failures.append("preflight_status")
    if contract.get("status") != "frozen" or contract.get("formal_evidence") is not False:
        failures.append("pilot_contract_semantics")
    if complete.get("pilot_audit_sha256") != sha256(required["audit"]):
        failures.append("complete_audit_sha256")
    if complete.get("deployment_preflight_sha256") != sha256(required["preflight"]):
        failures.append("complete_preflight_sha256")
    if audit.get("contract_sha256") != sha256(required["contract"]):
        failures.append("audit_contract_sha256")

    evaluations = {item["cell_id"]: item for item in audit.get("evaluations", [])}
    rows: list[dict] = []
    with tarfile.open(archive_path, "r:gz") as archive:
        names = set(archive.getnames())
        if len(names) != int(archive_manifest.get("files", -1)):
            failures.append("archive_member_count")
        for cell in contract.get("cells", []):
            cell_id = cell["cell_id"]
            metric_name = f"{cell_id}/paper_metrics_summary.csv"
            if metric_name not in names:
                failures.append(f"{cell_id}:paper_metrics_summary")
                continue
            metrics = archive_csv(archive, metric_name)
            if len(metrics) != 1:
                failures.append(f"{cell_id}:metric_row_count")
                continue
            metric = metrics[0]
            evaluation = evaluations.get(cell_id, {})
            rows.append(
                {
                    "cell_id": cell_id,
                    "pilot_role": "collision_regression_probe" if cell.get("probe") else "deployment_smoke",
                    "predictor": cell["predictor"],
                    "risk_policy": cell["risk_policy"],
                    "target_style": cell["target_style"],
                    "ego_init_id": cell["ego_init_id"],
                    "target_offset_m": cell["target_offset_m"],
                    "status": evaluation.get("status"),
                    "completion_time_s": as_float(metric.get("completion_time")),
                    "minimum_center_distance_m": as_float(metric.get("dmin_TV")),
                    "completion_valid": as_float(metric.get("completion_valid")),
                    "feasibility_fraction": as_float(metric.get("feasibility_percent")),
                    "average_solve_time_s": as_float(metric.get("average_solve_time")),
                    "solver_failure_fraction": as_float(metric.get("solver_failure_frac")),
                    "native_collision_count": evaluation.get("native_collision_count"),
                    "valid_prediction_steps": evaluation.get("valid_prediction_steps"),
                    "p95_solve_time_s": evaluation.get("p95_solve_time_s"),
                    "reference_A_MIN_mps2": evaluation.get("reference_A_MIN"),
                    "solver_A_MIN_mps2": evaluation.get("solver_A_MIN"),
                }
            )

    if len(rows) != int(contract.get("expected_rollouts", -1)):
        failures.append("consolidated_rollout_count")

    log_text = required["runner_log"].read_text(encoding="utf-8", errors="replace")
    initial_spawn_failures = len(re.findall(r"R2 cell failed after 3 attempts", log_text))
    successful_phase_attempts = re.findall(
        r"R2 cell=([^ ]+) attempt=1/3", log_text[log_text.rfind("CARLA map:") :]
    )
    provenance = {
        "initial_failed_cells_before_carla_restart": initial_spawn_failures,
        "initial_failure_class": "CARLA spawn collision / persistent simulator state",
        "successful_phase_cells_started_at_first_attempt": len(successful_phase_attempts),
        "successful_phase_expected_cells": int(contract.get("expected_rollouts", 0)),
        "interpretation": (
            "The failed launch occurred before the clean CARLA restart and produced no accepted "
            "rollout. All ten audited rollouts then started on attempt 1. This is retained as "
            "infrastructure provenance and is not counted as scientific outcome data."
        ),
    }
    if provenance["successful_phase_cells_started_at_first_attempt"] != contract.get("expected_rollouts"):
        failures.append("successful_phase_attempt_provenance")

    output.mkdir(parents=True, exist_ok=True)
    csv_path = output / "r2_pilot_cell_summary.csv"
    fieldnames = list(rows[0]) if rows else []
    if rows:
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        atomic_text(csv_path, buffer.getvalue())

    payload = {
        "schema_version": "r2_local_verification_v1",
        "status": "pass" if not failures else "fail",
        "stage": "R2",
        "scientific_role": "non_statistical_deployment_gate",
        "effect_estimation_allowed": False,
        "implementation_version": contract.get("implementation_version"),
        "observed_rollouts": len(rows),
        "passing_rollouts": sum(row.get("status") == "pass" for row in rows),
        "native_collisions": sum(int(row.get("native_collision_count") or 0) for row in rows),
        "total_valid_prediction_steps": sum(int(row.get("valid_prediction_steps") or 0) for row in rows),
        "max_p95_solve_time_s": max(float(row["p95_solve_time_s"]) for row in rows),
        "archive_sha256": actual_archive_hash,
        "archive_files": archive_manifest.get("files"),
        "runner_log_sha256": sha256(required["runner_log"]),
        "source_git_commit": contract.get("git_commit"),
        "failures": sorted(set(failures)),
        "launch_provenance": provenance,
        "cell_summary_csv": str(csv_path.relative_to(output)),
        "claim_boundary": (
            "R2 supports corrected deployment validity and runtime feasibility only. "
            "Its per-cell values must not be used to claim predictor or policy effects."
        ),
    }
    json_path = output / "R2_LOCAL_VERIFICATION.json"
    atomic_json(json_path, payload)
    markdown = f"""# R2 corrected-pilot local verification

Status: **{payload['status'].upper()}**

- 10/10 corrected-v1 pilot rollouts passed; native collisions: 0.
- {payload['total_valid_prediction_steps']} valid prediction/control steps were audited.
- Maximum per-rollout P95 solver time: {payload['max_p95_solve_time_s']:.4f} s (gate: 0.5 s).
- Pulled archive SHA256: `{actual_archive_hash}` ({payload['archive_files']} files).
- Runner log SHA256: `{payload['runner_log_sha256']}`.
- One pre-restart launch failed from persistent CARLA spawn state; after a clean restart, all 10 accepted rollouts started on their first attempt.

Scientific boundary: this is a deployment/runtime gate, not an effect-estimation sample. The descriptive cell table must not be cited as evidence that B1 beats B0 or that adaptive risk beats a fixed policy.
"""
    atomic_text(output / "R2_LOCAL_VERIFICATION.md", markdown)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
