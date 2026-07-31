#!/usr/bin/env python3
"""Write an atomic, compact Day 6 progress snapshot inside the result root."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


CELLS = ("S0_FIXED", "S0_ADAPTIVE", "S1_FIXED", "S1_ADAPTIVE")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def atomic_write(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--exit-code", type=int)
    args = parser.parse_args()

    root = Path(args.results_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    cell_summary = {}
    total_bytes = 0
    total_files = 0
    for path in root.rglob("*"):
        if path.is_file():
            total_files += 1
            total_bytes += path.stat().st_size

    for cell in CELLS:
        cell_dir = root / cell
        rollout_dirs = sorted(
            path for path in cell_dir.glob("scenario_*") if path.is_dir()
        ) if cell_dir.exists() else []
        status = Counter()
        init_ids = []
        for rollout in rollout_dirs:
            summary_path = rollout / "scenario_run_summary.json"
            manifest_path = (
                rollout / "prediction_dataset" / "prediction_dataset_manifest.json"
            )
            summary = read_json(summary_path) if summary_path.exists() else None
            manifest = read_json(manifest_path) if manifest_path.exists() else None
            if summary and summary.get("ran_successfully") is True:
                status["successful"] += 1
            elif summary:
                status["failed"] += 1
            else:
                status["incomplete"] += 1
            if manifest:
                status["manifests"] += 1
                init_id = manifest.get("dataset_metadata", {}).get("ego_init_id")
                if init_id is not None:
                    init_ids.append(int(init_id))
        cell_summary[cell] = {
            "rollout_directories": len(rollout_dirs),
            "successful": status["successful"],
            "failed": status["failed"],
            "incomplete": status["incomplete"],
            "prediction_manifests": status["manifests"],
            "observed_init_ids": sorted(set(init_ids)),
        }

    successful = sum(value["successful"] for value in cell_summary.values())
    manifests = sum(value["prediction_manifests"] for value in cell_summary.values())
    snapshot = {
        "schema_version": "day6_progress_v1",
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": args.phase,
        "exit_code": args.exit_code,
        "results_dir": str(root),
        "expected_rollouts": 200,
        "successful_rollouts": successful,
        "prediction_manifests": manifests,
        "completion_fraction": successful / 200.0,
        "cells": cell_summary,
        "inventory": {"file_count": total_files, "total_bytes": total_bytes},
        "complete_by_counts": successful == 200 and manifests == 200,
    }
    atomic_write(root / "day6_progress.json", snapshot)
    with (root / "day6_attempts.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "timestamp_utc": snapshot["updated_at_utc"],
                    "phase": args.phase,
                    "exit_code": args.exit_code,
                    "successful_rollouts": successful,
                    "prediction_manifests": manifests,
                }
            )
            + "\n"
        )
    print(json.dumps(snapshot, indent=2))


if __name__ == "__main__":
    main()
