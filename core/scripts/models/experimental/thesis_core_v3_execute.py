#!/usr/bin/env python3
"""Plan, execute, and audit one disjoint thesis-core GPU shard."""

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
import subprocess
from pathlib import Path
from typing import Any, Mapping

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload
from thesis_core_v3_runs import (
    shard_runs,
    thesis_core_runs,
    validate_thesis_core_manifest,
)
from train_prediction_model_v3 import artifact_hash


CORRECTED_COMPLETION_SCHEMA = "capacity_history_thesis_core_training_complete_v4_masked"
CORRECTED_HEALTH_SCHEMA = "capacity_history_thesis_core_training_health_v4_masked"
FUTURE_VALIDITY_CONTRACT = "future_valid_mask_fail_closed_v4"


def completion_valid(path: Path, spec: Mapping[str, Any]) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = dict(payload)
        recorded = value.pop("completion_sha256", None)
        if recorded != sha256_payload(value):
            return False
        if (
            payload.get("schema_version") != CORRECTED_COMPLETION_SCHEMA
            or payload.get("status") != "pass"
            or payload.get("formal_run") is not True
            or payload.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
            or payload.get("checkpoint_selection_metric")
            != "validation_rollout_macro_masked_trajectory_mixture_NLL_per_valid_step"
        ):
            return False
        if payload.get("run_id") != spec["run_id"]:
            return False
        for key in (
            "best_model",
            "best_weights",
            "cached_weights",
            "history_csv",
            "run_config",
            "training_health",
            "parameters",
            "parity",
            "epoch_checkpoints",
            "resume_backup",
        ):
            record = payload[key]
            if artifact_hash(Path(record["path"])) != record:
                return False
        parity = json.loads(Path(payload["parity"]["path"]).read_text(encoding="utf-8"))
        health = json.loads(Path(payload["training_health"]["path"]).read_text(encoding="utf-8"))
        if (
            parity.get("status") != "pass"
            or health.get("schema_version") != CORRECTED_HEALTH_SCHEMA
            or health.get("hard_checks_pass") is not True
            or health.get("future_validity_contract") != FUTURE_VALIDITY_CONTRACT
            or health.get("epoch_recovery_preserved") is not True
            or int(health.get("per_epoch_checkpoints", -1))
            != int(health.get("epochs_completed", -2))
        ):
            return False
        return all(
            payload.get(key) == spec.get(key)
            for key in (
                "model_cell_id",
                "family",
                "capacity_tier",
                "history_horizon_s",
                "learning_rate",
                "seed",
            )
        )
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return False


def plan(args: argparse.Namespace) -> dict[str, Any]:
    manifest = json.loads(args.run_manifest.read_text(encoding="utf-8"))
    validate_thesis_core_manifest(manifest)
    specs = [row for row in manifest["runs"]]
    assigned_ids = {row.run_id for row in shard_runs(thesis_core_runs(), args.shard_index, args.shard_count)}
    jobs = []
    for spec in specs:
        if spec["run_id"] not in assigned_ids:
            continue
        completion = args.output_root / spec["run_id"] / "TRAINING_COMPLETE.json"
        command = [
            args.python_bin,
            str(Path(__file__).with_name("train_thesis_core_cached_v3.py")),
            "--run-manifest",
            str(args.run_manifest),
            "--run-id",
            spec["run_id"],
            "--dataset-dir",
            str(args.dataset_dir),
            "--cache-dir",
            str(args.cache_dir),
            "--base-model",
            str(args.base_model),
            "--anchors",
            str(args.anchors),
            "--output-dir",
            str(args.output_root / spec["run_id"]),
            "--batch-size",
            str(args.batch_size),
        ]
        jobs.append(
            {
                "run_id": spec["run_id"],
                "status": "complete" if completion_valid(completion, spec) else "pending",
                "command_argv": command,
            }
        )
    return {
        "schema_version": "capacity_history_thesis_core_shard_plan_v3",
        "status": "pass",
        "shard_index": args.shard_index,
        "shard_count": args.shard_count,
        "assigned_runs": len(jobs),
        "complete_runs": sum(row["status"] == "complete" for row in jobs),
        "pending_runs": sum(row["status"] == "pending" for row in jobs),
        "jobs": jobs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-manifest", required=True, type=Path)
    parser.add_argument("--dataset-dir", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--python-bin", default="python")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--shard-index", required=True, type=int)
    parser.add_argument("--shard-count", type=int, default=6)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan-output", type=Path)
    args = parser.parse_args()
    current = plan(args)
    if args.plan_output:
        atomic_json(args.plan_output, current)
    if args.execute:
        for job in current["jobs"]:
            if job["status"] == "pending":
                subprocess.run(job["command_argv"], check=True)
        current = plan(args)
    print(json.dumps(current, indent=2, sort_keys=True))
    if args.execute and current["pending_runs"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
