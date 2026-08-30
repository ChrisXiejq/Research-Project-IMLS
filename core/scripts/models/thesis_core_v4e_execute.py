#!/usr/bin/env python3
"""Execute and validate the uniformly extended 27-run masked matrix."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Mapping

from capacity_study_v3_protocol import atomic_json, sha256_payload
from thesis_core_v3_execute import completion_valid as base_completion_valid
from thesis_core_v3_runs import shard_runs, thesis_core_runs, validate_thesis_core_manifest
from training_epoch_integrity_v4 import inspect_epoch_artifacts


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def hash_valid(payload: Mapping[str, Any], field: str) -> bool:
    value = dict(payload)
    recorded = value.pop(field, None)
    return recorded == sha256_payload(value)


def completion_valid(path: Path, spec: Mapping[str, Any]) -> bool:
    if not base_completion_valid(path, spec):
        return False
    try:
        completion = load(path)
        directory = path.parent
        config = load(directory / "run_config.json")
        health = load(directory / "training_health.json")
        seed = load(directory / "EXTENSION_SEED_RECEIPT.json")
        epoch_integrity = inspect_epoch_artifacts(
            directory / "history.csv",
            directory / "epoch_checkpoints",
            backup_dir=directory / "resume_backup",
            validate_hdf5=False,
        )
        return bool(
            int(config.get("epochs", -1)) == 120
            and int(health.get("epochs_allowed", -1)) == 120
            and int(health.get("epochs_completed", -1)) <= 120
            and epoch_integrity.get("status") == "pass"
            and int(epoch_integrity.get("history_rows", -1))
            == int(health.get("epochs_completed", -2))
            and "train_thesis_core_cached_v4e_120.py" in config.get(
                "source_sha256", {}
            )
            and hash_valid(seed, "receipt_sha256")
            and seed.get("run_id") == spec["run_id"]
            and seed.get("heldout_accessed") is False
            and seed.get("source_completion_sha256")
            != completion.get("completion_sha256")
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return False


def plan(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load(args.run_manifest)
    validate_thesis_core_manifest(manifest)
    assigned_ids = {
        row.run_id
        for row in shard_runs(
            thesis_core_runs(), args.shard_index, args.shard_count
        )
    }
    jobs = []
    for spec in manifest["runs"]:
        if spec["run_id"] not in assigned_ids:
            continue
        output = args.output_root / spec["run_id"]
        command = [
            args.python_bin,
            str(Path(__file__).with_name("train_thesis_core_cached_v4e_120.py")),
            "--run-manifest", str(args.run_manifest),
            "--run-id", spec["run_id"],
            "--dataset-dir", str(args.dataset_dir),
            "--cache-dir", str(args.cache_dir),
            "--base-model", str(args.base_model),
            "--anchors", str(args.anchors),
            "--output-dir", str(output),
            "--batch-size", str(args.batch_size),
        ]
        jobs.append({
            "run_id": spec["run_id"],
            "status": (
                "complete"
                if completion_valid(output / "TRAINING_COMPLETE.json", spec)
                else "pending"
            ),
            "command_argv": command,
        })
    return {
        "schema_version": "capacity_history_thesis_core_v4e_shard_plan",
        "status": "pass",
        "uniform_budget_epochs": 120,
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
    parser.add_argument("--shard-count", type=int, default=1)
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
