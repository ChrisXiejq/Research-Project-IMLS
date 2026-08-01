#!/usr/bin/env python3
"""Package the Day 10 formal closed-loop evidence without model weights or rasters."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
from pathlib import Path


INCLUDE_NAMES = {
    "day10_run_contract.json",
    "day10_deployment_preflight.json",
    "day10_closed_loop_audit.json",
    "DAY10_COMPLETE.json",
    "tuning_day10_frozen.json",
    "scenario_run_summary.json",
    "scenario_rollout_config.json",
    "prediction_deployment_manifest.json",
    "smpc_debug_setup.json",
    "smpc_debug_steps.jsonl",
    "prediction_dataset_config.json",
    "prediction_dataset_manifest.json",
    "prediction_dataset_raw.jsonl",
    "prediction_dataset_labeled.jsonl",
    "postcarla_trajectory_gate.json",
    "risk_by_conflict_distance_summary.json",
    "risk_by_conflict_distance_summary.csv",
    "risk_by_conflict_distance_comparison.csv",
    "paper_metrics_summary.csv",
    "comparison_manifest.jsonl",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.results_dir).resolve()
    output = Path(args.output).resolve()
    for required in ("DAY10_COMPLETE.json", "day10_closed_loop_audit.json", "day10_run_contract.json"):
        if not (root / required).is_file():
            raise FileNotFoundError(root / required)
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name in INCLUDE_NAMES and path.resolve() != output
    )
    temporary = output.with_suffix(output.suffix + ".tmp")
    with tarfile.open(temporary, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=str(path.relative_to(root)))
    os.replace(temporary, output)
    manifest = {
        "status": "pass",
        "archive": str(output),
        "archive_sha256": sha256(output),
        "files": len(files),
        "excludes_model_weights": True,
        "excludes_rasters_and_video": True,
    }
    output.with_suffix(output.suffix + ".json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
