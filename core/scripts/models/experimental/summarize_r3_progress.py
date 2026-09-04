#!/usr/bin/env python3
"""Read-only progress summary for the resumable R3 formal matrix."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return None


def build_summary(root: Path, contract_path: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    contract_path = contract_path.resolve() if contract_path else root / "r3_run_contract.json"
    contract = read_json(contract_path) or {}
    order = contract.get("execution_order") or []
    expected = int(contract.get("expected_rollouts", len(order) or 80))
    expected_keys = [
        {
            "cell_id": item["cell_id"],
            "ego_init_id": int(item["ego_init_id"]),
        }
        for item in order
    ]
    if not expected_keys:
        for predictor in ("B1", "B0"):
            for policy in ("fixed_aggressive", "fixed_medium", "fixed_conservative", "adaptive"):
                for style in ("assertive", "reactive"):
                    for init_id in (101, 102, 103, 104, 105):
                        expected_keys.append(
                            {"cell_id": f"{predictor}_{policy}_{style}", "ego_init_id": init_id}
                        )
    accepted = []
    pending = []
    for key in expected_keys:
        receipt = root / key["cell_id"] / f"R3_ROLLOUT_{key['ego_init_id']}_COMPLETE.json"
        value = read_json(receipt)
        if value and value.get("status") == "pass":
            accepted.append({**key, "receipt": str(receipt)})
        else:
            pending.append(key)

    attempt_records = sorted(root.glob("*/_attempts/init_*/attempt_*/attempt_record.json"))
    starts = sorted(root.glob("*/_attempts/init_*/attempt_*/attempt_started.json"))
    records_by_dir = {path.parent: read_json(path) or {} for path in attempt_records}
    current = []
    for start in starts:
        if start.parent not in records_by_dir:
            value = read_json(start) or {}
            current.append(
                {
                    "cell_id": value.get("cell_id"),
                    "ego_init_id": value.get("ego_init_id"),
                    "attempt": value.get("attempt"),
                    "started_at_utc": value.get("started_at_utc"),
                    "directory": str(start.parent),
                }
            )
    failed = [
        {
            "cell_id": value.get("cell_id"),
            "ego_init_id": value.get("ego_init_id"),
            "attempt": value.get("attempt"),
            "classification": value.get("classification"),
            "retry_allowed": value.get("retry_allowed"),
        }
        for value in records_by_dir.values()
        if value.get("accepted") is False
    ]

    available_outcomes = 0
    for gate_path in root.glob("*/postcarla_trajectory_gate.json"):
        gate = read_json(gate_path) or {}
        available_outcomes += len(gate.get("evaluations") or [])
    audit = read_json(root / "r3_corrected_matrix_audit.json")
    analysis = read_json(root / "analysis" / "R3_ANALYSIS_COMPLETE.json")
    stop_gate = read_json(root / "analysis" / "R3_STUDY_STOP_GATE.json")
    data_complete = read_json(root / "R3_DATA_COMPLETE.json")
    archive = root / "r3_corrected_formal_snapshot.tar.gz"
    archive_sidecar = read_json(Path(str(archive) + ".json"))
    complete = read_json(root / "R3_COMPLETE.json")
    payload = {
        "schema_version": "r3_progress_v2",
        "results_dir": str(root),
        "expected_rollouts": expected,
        "accepted_rollouts": len(accepted),
        "pending_rollouts": len(pending),
        "failed_attempts": len(failed),
        "retryable_failed_attempts": sum(item["retry_allowed"] is True for item in failed),
        "nonretryable_failed_attempts": sum(item["retry_allowed"] is not True for item in failed),
        "current_or_interrupted_attempts": current,
        "scientific_raw_outcomes_available": len(accepted),
        "scientific_outcomes_available": available_outcomes,
        "integrity_status": (audit or {}).get("status", "not_run"),
        "analysis_status": (analysis or {}).get("status", "not_run"),
        "study_stop_gate_status": (stop_gate or {}).get("status", "not_run"),
        "data_complete_status": (data_complete or {}).get("status", "not_run"),
        "archive_status": (archive_sidecar or {}).get("status", "not_built"),
        "archive_present": archive.is_file(),
        "complete_status": (complete or {}).get("status", "not_complete"),
        "accepted": accepted,
        "pending": pending,
        "failed": failed,
    }
    return payload


def print_human(payload: dict[str, Any]) -> None:
    print(
        "R3 progress: "
        f"accepted={payload['accepted_rollouts']}/{payload['expected_rollouts']} "
        f"pending={payload['pending_rollouts']} "
        f"failed_attempts={payload['failed_attempts']} "
        f"active_or_interrupted={len(payload['current_or_interrupted_attempts'])}"
    )
    print(
        "Stages: "
        f"raw_outcomes={payload['scientific_raw_outcomes_available']} "
        f"postprocessed_outcomes={payload['scientific_outcomes_available']} "
        f"integrity={payload['integrity_status']} "
        f"analysis={payload['analysis_status']} "
        f"stop_gate={payload['study_stop_gate_status']} "
        f"archive={payload['archive_status']} "
        f"complete={payload['complete_status']}"
    )
    if payload["current_or_interrupted_attempts"]:
        print("Current/interrupted attempts:")
        for item in payload["current_or_interrupted_attempts"]:
            print(
                f"  {item['cell_id']}/init{item['ego_init_id']} attempt={item['attempt']} "
                f"started={item['started_at_utc']}"
            )
    if payload["pending"]:
        print("Next pending rollouts:")
        for item in payload["pending"][:20]:
            print(f"  {item['cell_id']}/init{item['ego_init_id']}")
        if len(payload["pending"]) > 20:
            print(f"  ... {len(payload['pending']) - 20} more")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--contract-json", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = build_summary(args.results_dir, args.contract_json)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_human(payload)


if __name__ == "__main__":
    main()
