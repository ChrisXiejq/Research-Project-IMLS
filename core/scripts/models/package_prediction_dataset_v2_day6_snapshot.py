#!/usr/bin/env python3
"""Package the compact, auditable part of a completed Day 6 collection."""

from __future__ import annotations

import argparse
import tarfile
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(args.results_dir).resolve()
    output = Path(args.output).resolve()
    if not (root / "DAY6_COMPLETE.json").is_file():
        raise SystemExit("DAY6_COMPLETE.json is missing; refusing to package incomplete data")

    patterns = (
        "DAY6_COMPLETE.json",
        "day6_collection_audit.json",
        "day6_analysis_manifest.json",
        "day6_run_contract.json",
        "day6_preflight_latest.json",
        "day6_progress.json",
        "day6_attempts.jsonl",
        "prediction_dataset_manifests.txt",
        "protocol_snapshot/*",
        "*/batch_summary.txt",
        "*/batch_subruns.json",
        "*/batch_events.jsonl",
        "*/environment.json",
        "*/scenario_*/scenario_run_summary.json",
        "*/scenario_*/prediction_dataset/prediction_dataset_manifest.json",
    )
    selected = sorted(
        {path for pattern in patterns for path in root.glob(pattern) if path.is_file()}
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz") as archive:
        for path in selected:
            archive.add(path, arcname=str(path.relative_to(root)))
    print(f"packed_files={len(selected)} output={output} bytes={output.stat().st_size}")


if __name__ == "__main__":
    main()
