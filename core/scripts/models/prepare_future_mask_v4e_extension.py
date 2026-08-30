#!/usr/bin/env python3
"""Seed a uniform 120-epoch continuation without altering the 80-epoch evidence.

The amendment is allowed only after the pre-freeze convergence gate fails and
before any corrected held-out artifact exists.  All 27 runs are seeded from
their last optimizer state, existing selection history and per-epoch recovery
checkpoints.  Existing checkpoints are hard-linked, never rewritten.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Mapping

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload
from thesis_core_v3_runs import validate_thesis_core_manifest


COMPLETE_SCHEMA = "capacity_history_thesis_core_training_complete_v4_masked"
CONTRACT = "future_valid_mask_fail_closed_v4"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return value


def hash_valid(payload: Mapping[str, Any], field: str) -> bool:
    value = dict(payload)
    recorded = value.pop(field, None)
    return recorded == sha256_payload(value)


def tree_hash(path: Path) -> dict[str, Any]:
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    size = 0
    for item in files:
        digest.update(str(item.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(sha256_file(item).encode("ascii"))
        size += item.stat().st_size
    return {
        "path": str(path),
        "files": len(files),
        "bytes": size,
        "sha256_tree": digest.hexdigest(),
    }


def artifact_matches(record: Mapping[str, Any]) -> bool:
    path = Path(str(record["path"]))
    if path.is_file():
        return (
            int(record.get("bytes", -1)) == path.stat().st_size
            and record.get("sha256") == sha256_file(path)
        )
    if path.is_dir():
        return tree_hash(path) == dict(record)
    return False


def hardlink_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in sorted(source.iterdir()):
        if not item.is_file():
            raise ValueError(f"Unexpected nested checkpoint item: {item}")
        target = destination / item.name
        if target.exists():
            if sha256_file(target) != sha256_file(item):
                raise ValueError(f"Existing checkpoint differs: {target}")
            continue
        os.link(item, target)


def history_epochs(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def seed_run(
    *,
    run_id: str,
    source_root: Path,
    destination_root: Path,
    spill_root: Path,
) -> dict[str, Any]:
    source = source_root / run_id
    destination = destination_root / run_id
    completion = load(source / "TRAINING_COMPLETE.json")
    if (
        not hash_valid(completion, "completion_sha256")
        or completion.get("schema_version") != COMPLETE_SCHEMA
        or completion.get("status") != "pass"
        or completion.get("future_validity_contract") != CONTRACT
        or completion.get("run_id") != run_id
    ):
        raise ValueError(f"Invalid source completion: {run_id}")
    for key in (
        "cached_weights",
        "history_csv",
        "resume_backup",
        "epoch_checkpoints",
    ):
        if not artifact_matches(completion[key]):
            raise ValueError(f"Source artifact drift for {run_id}:{key}")

    receipt_path = destination / "EXTENSION_SEED_RECEIPT.json"
    if receipt_path.is_file():
        receipt = load(receipt_path)
        if hash_valid(receipt, "receipt_sha256"):
            return receipt
        raise ValueError(f"Invalid existing extension seed receipt: {run_id}")
    if (destination / "TRAINING_COMPLETE.json").exists():
        raise ValueError(f"Unreceipted destination completion exists: {run_id}")
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "history.csv", destination / "history.csv")
    shutil.copy2(source / "cached_best.weights.h5", destination / "cached_best.weights.h5")
    shutil.copytree(source / "resume_backup", destination / "resume_backup")

    source_epochs = (source / "epoch_checkpoints").resolve()
    local_device = destination.stat().st_dev
    source_device = source_epochs.stat().st_dev
    if source_device == local_device:
        destination_epochs = destination / "epoch_checkpoints"
        storage = "autodl_tmp_hardlinks"
    else:
        destination_epochs = spill_root / run_id
        destination_epochs.mkdir(parents=True, exist_ok=True)
        link = destination / "epoch_checkpoints"
        if not link.exists() and not link.is_symlink():
            link.symlink_to(destination_epochs)
        if link.resolve() != destination_epochs.resolve():
            raise ValueError(f"Extension spill link drift: {run_id}")
        storage = "memory_spill_hardlinks"
    hardlink_tree(source_epochs, destination_epochs)
    epochs = history_epochs(destination / "history.csv")
    if len(list(destination_epochs.glob("epoch_*.weights.h5"))) != epochs:
        raise ValueError(f"Seeded checkpoint/history mismatch: {run_id}")

    receipt = {
        "schema_version": "capacity_history_future_mask_v4e_run_seed_receipt",
        "status": "pass",
        "run_id": run_id,
        "source_completion_sha256": completion["completion_sha256"],
        "source_best_epoch": int(completion["best_epoch"]),
        "source_epochs_completed": epochs,
        "destination_maximum_epochs": 120,
        "continuation_uses_optimizer_backup": True,
        "continuation_uses_existing_selection_history": True,
        "heldout_accessed": False,
        "checkpoint_storage": storage,
        "history_sha256": sha256_file(destination / "history.csv"),
        "cached_best_weights_sha256": sha256_file(
            destination / "cached_best.weights.h5"
        ),
        "resume_backup": tree_hash(destination / "resume_backup"),
        "epoch_checkpoints": tree_hash(destination / "epoch_checkpoints"),
    }
    receipt["receipt_sha256"] = sha256_payload(receipt)
    atomic_json(receipt_path, receipt)
    return receipt


def prepare(args: argparse.Namespace) -> dict[str, Any]:
    manifest = load(args.manifest)
    validate_thesis_core_manifest(manifest)
    trigger = load(args.trigger_audit)
    if (
        not hash_valid(trigger, "audit_sha256")
        or trigger.get("status") != "fail"
        or not trigger.get("unresolved_boundary_underfit_runs")
        or int(trigger.get("runs", -1)) != 27
    ):
        raise ValueError("Uniform extension requires a failed 27-run pre-freeze audit")
    if args.corrected_heldout_root.exists() and any(args.corrected_heldout_root.rglob("*.json")):
        raise ValueError("Extension blocked because corrected held-out has been accessed")
    args.destination_root.mkdir(parents=True, exist_ok=True)
    args.spill_root.mkdir(parents=True, exist_ok=True)
    receipts = [
        seed_run(
            run_id=str(spec["run_id"]),
            source_root=args.source_training_root,
            destination_root=args.destination_root,
            spill_root=args.spill_root,
        )
        for spec in manifest["runs"]
    ]
    if len(receipts) != 27 or {row["run_id"] for row in receipts} != {
        str(spec["run_id"]) for spec in manifest["runs"]
    }:
        raise ValueError("Uniform extension seed matrix is incomplete")
    payload = {
        "schema_version": "capacity_history_future_mask_v4e_extension_protocol",
        "status": "pass",
        "scientific_role": "uniform_pre_freeze_training_budget_amendment",
        "source_budget_epochs": 80,
        "destination_budget_epochs": 120,
        "all_27_runs_extended_uniformly": True,
        "single_run_or_cell_selective_extension": False,
        "heldout_accessed_before_amendment": False,
        "trigger_audit_sha256": trigger["audit_sha256"],
        "triggered_runs": sorted(trigger["unresolved_boundary_underfit_runs"]),
        "manifest_sha256": sha256_file(args.manifest),
        "source_training_root": str(args.source_training_root.resolve()),
        "destination_training_root": str(args.destination_root.resolve()),
        "run_seed_receipts": {
            row["run_id"]: row["receipt_sha256"] for row in receipts
        },
    }
    payload["protocol_sha256"] = sha256_payload(payload)
    atomic_json(args.output, payload)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-training-root", required=True, type=Path)
    parser.add_argument("--trigger-audit", required=True, type=Path)
    parser.add_argument("--corrected-heldout-root", required=True, type=Path)
    parser.add_argument("--destination-root", required=True, type=Path)
    parser.add_argument("--spill-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = prepare(args)
    print(json.dumps({
        "status": payload["status"],
        "runs": len(payload["run_seed_receipts"]),
        "protocol_sha256": payload["protocol_sha256"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
