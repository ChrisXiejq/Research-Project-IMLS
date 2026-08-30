#!/usr/bin/env python3
"""Seal the command and immutable inputs of an already-running V4 pipeline."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--dataset-complete", required=True, type=Path)
    parser.add_argument("--cache-complete", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    proc = Path("/proc") / str(args.pid)
    if not proc.is_dir():
        raise ValueError(f"Pipeline PID is not running: {args.pid}")
    command = (proc / "cmdline").read_bytes().replace(b"\x00", b" ").decode().strip()
    cwd = os.readlink(proc / "cwd")
    script_dir = args.worktree / "core/scripts/models"
    if Path(cwd).resolve() != script_dir.resolve():
        raise ValueError(f"Pipeline cwd is not the frozen script directory: {cwd}")
    required_command_tokens = (
        "bash -lc set -euo pipefail",
        str(script_dir.resolve()),
        f"MASK_ROOT={args.output_root.resolve()}",
        "thesis_core_v3_execute.py",
        "thesis_core_v3_postprocess.py",
        "--stage calibrate",
        "--stage heldout",
        "synthesize",
        "OFFLINE_PIPELINE_COMPLETE",
    )
    missing_tokens = [token for token in required_command_tokens if token not in command]
    if missing_tokens:
        raise ValueError(f"Running command is not the expected V4 pipeline: {missing_tokens}")
    sources = (
        "thesis_core_v3_execute.py",
        "train_thesis_core_cached_v3.py",
        "train_prediction_model_v3.py",
        "evaluate_multipath_model_on_dataset.py",
        "build_thesis_core_feature_cache_v3.py",
        "evaluate_thesis_core_cached_v3.py",
        "thesis_core_v3_postprocess.py",
        "capacity_study_v3_analysis.py",
        "audit_thesis_core_v3_training.py",
        "measure_thesis_core_latency_v3.py",
        "thesis_core_v3_runs.py",
        "capacity_study_v3_protocol.py",
    )
    stat_fields = (proc / "stat").read_text(encoding="utf-8").split()
    start_ticks = int(stat_fields[21])
    clock_ticks = int(os.sysconf(os.sysconf_names["SC_CLK_TCK"]))
    boot_time = next(
        int(line.split()[1])
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines()
        if line.startswith("btime ")
    )
    process_started = datetime.fromtimestamp(
        boot_time + start_ticks / clock_ticks, tz=timezone.utc
    ).isoformat()
    payload = {
        "schema_version": "capacity_history_future_mask_v4_running_pipeline_receipt",
        "status": "pass",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "process_started_at_utc": process_started,
        "pid": args.pid,
        "process_command": command,
        "process_cwd": cwd,
        "worktree": str(args.worktree.resolve()),
        "output_root": str(args.output_root.resolve()),
        "training_source_sha256": {
            name: sha256_file(script_dir / name) for name in sources
        },
        "manifest": {
            "path": str(args.manifest.resolve()),
            "sha256": sha256_file(args.manifest),
        },
        "dataset_complete": {
            "path": str(args.dataset_complete.resolve()),
            "sha256": sha256_file(args.dataset_complete),
        },
        "cache_complete": {
            "path": str(args.cache_complete.resolve()),
            "sha256": sha256_file(args.cache_complete),
        },
        "claim_boundary": (
            "This receipt records the live externally launched process and immutable "
            "training inputs. Post-training scripts are separately source-hashed by "
            "the final evidence audits."
        ),
    }
    payload["receipt_sha256"] = sha256_payload(payload)
    atomic_json(args.output, payload)
    print(json.dumps({"status": "pass", "receipt_sha256": payload["receipt_sha256"]}))


if __name__ == "__main__":
    main()
