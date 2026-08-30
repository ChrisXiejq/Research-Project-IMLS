#!/usr/bin/env python3
"""Seal the live uniform-extension pipeline and its immutable amendment."""

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
    parser.add_argument("--extension-protocol", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    proc = Path("/proc") / str(args.pid)
    if not proc.is_dir():
        raise ValueError(f"Pipeline PID is not running: {args.pid}")
    command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode().strip()
    cwd = Path(os.readlink(proc / "cwd")).resolve()
    script_dir = (args.worktree / "core/scripts/models").resolve()
    required = (
        str(script_dir / "run_future_mask_v4e_pipeline.sh"),
        str(args.output_root.resolve()),
        str(args.extension_protocol.resolve()),
    )
    if cwd != script_dir or any(token not in command for token in required):
        raise ValueError("Live process is not the frozen V4e pipeline")
    extension = json.loads(args.extension_protocol.read_text(encoding="utf-8"))
    extension_value = dict(extension)
    recorded_extension_hash = extension_value.pop("protocol_sha256", None)
    if (
        recorded_extension_hash != sha256_payload(extension_value)
        or extension.get("status") != "pass"
        or extension.get("all_27_runs_extended_uniformly") is not True
        or extension.get("heldout_accessed_before_amendment") is not False
    ):
        raise ValueError("Uniform extension protocol is invalid")
    sources = (
        "run_future_mask_v4e_pipeline.sh",
        "thesis_core_v4e_execute.py",
        "train_thesis_core_cached_v4e_120.py",
        "train_thesis_core_cached_v3.py",
        "train_prediction_model_v3.py",
        "evaluate_multipath_model_on_dataset.py",
        "build_thesis_core_feature_cache_v3.py",
        "evaluate_thesis_core_cached_v3.py",
        "thesis_core_v3_execute.py",
        "thesis_core_v3_postprocess.py",
        "capacity_study_v3_analysis.py",
        "audit_thesis_core_v4e_training.py",
        "audit_thesis_core_v3_training.py",
        "training_epoch_integrity_v4.py",
        "write_pre_freeze_training_curve_audit_v4.py",
        "write_future_mask_v4e_pipeline_receipt.py",
        "audit_future_mask_v4_offline.py",
        "measure_thesis_core_latency_v3.py",
        "thesis_core_v3_runs.py",
        "capacity_study_v3_protocol.py",
    )
    stat = (proc / "stat").read_text(encoding="utf-8").split()
    start_ticks = int(stat[21])
    clock_ticks = int(os.sysconf(os.sysconf_names["SC_CLK_TCK"]))
    boot_time = next(
        int(line.split()[1])
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines()
        if line.startswith("btime ")
    )
    payload = {
        # Keep the V4 schema because the downstream receipt verifier validates
        # structure and source identities; the amendment is an additional gate.
        "schema_version": "capacity_history_future_mask_v4_running_pipeline_receipt",
        "status": "pass",
        "protocol_variant": "uniform_v4e_120_epoch_amendment",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "process_started_at_utc": datetime.fromtimestamp(
            boot_time + start_ticks / clock_ticks, tz=timezone.utc
        ).isoformat(),
        "pid": args.pid,
        "process_command": command,
        "process_cwd": str(cwd),
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
        "extension_protocol": {
            "path": str(args.extension_protocol.resolve()),
            "sha256": sha256_file(args.extension_protocol),
            "protocol_sha256": extension["protocol_sha256"],
        },
        "claim_boundary": (
            "The 120-epoch maximum was applied uniformly to all 27 runs after a "
            "pre-freeze convergence gate failed and before corrected held-out access."
        ),
    }
    payload["receipt_sha256"] = sha256_payload(payload)
    atomic_json(args.output, payload)
    print(json.dumps({
        "status": "pass",
        "receipt_sha256": payload["receipt_sha256"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
