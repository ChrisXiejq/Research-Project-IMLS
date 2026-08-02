#!/usr/bin/env python3
"""Package a compact closed-loop evidence tree without weights, rasters, or video."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
from pathlib import Path


INCLUDE_NAMES = {
    "scenario_run_summary.json", "scenario_rollout_config.json", "prediction_deployment_manifest.json",
    "smpc_debug_setup.json", "smpc_debug_steps.jsonl", "prediction_dataset_config.json",
    "prediction_dataset_manifest.json", "prediction_dataset_raw.jsonl", "prediction_dataset_labeled.jsonl",
    "postcarla_trajectory_gate.json", "risk_by_conflict_distance_summary.json",
    "risk_by_conflict_distance_summary.csv", "risk_by_conflict_distance_comparison.csv",
    "df_full.csv", "paper_metrics_summary.csv", "comparison_manifest.jsonl",
    "day11_analysis_summary.json", "day11_rollout_metrics.csv", "day11_cell_summary.csv",
    "day11_paired_contrasts.csv",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--complete", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root=args.results_dir.resolve(); output=args.output.resolve()
    required={args.contract,args.audit,args.complete}
    missing=[name for name in required if not (root/name).is_file()]
    if missing: raise FileNotFoundError(f"Missing closed-loop evidence: {missing}")
    contract=json.loads((root/args.contract).read_text())
    explicit={root/name for name in required}
    preflight=contract.get("deployment_preflight_filename")
    if preflight: explicit.add(root/preflight)
    for entry in (contract.get("tuning_sha256_by_offset") or {}).values():
        explicit.add(root/entry["path"])
    missing_explicit=[str(path) for path in explicit if not path.is_file()]
    if missing_explicit: raise FileNotFoundError(f"Missing contract-bound evidence: {missing_explicit}")
    files=sorted({path for path in root.rglob("*") if path.is_file() and path.name in INCLUDE_NAMES and path.resolve()!=output}|explicit)
    temp=output.with_suffix(output.suffix+".tmp")
    with tarfile.open(temp,"w:gz") as archive:
        for path in files: archive.add(path,arcname=str(path.relative_to(root)))
    os.replace(temp,output)
    manifest={"schema_version":"closed_loop_snapshot_v1","status":"pass","archive":str(output),"archive_sha256":sha256(output),"files":len(files),"excludes_model_weights_rasters_and_video":True}
    output.with_suffix(output.suffix+".json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(json.dumps(manifest,indent=2,sort_keys=True))


if __name__ == "__main__": main()
