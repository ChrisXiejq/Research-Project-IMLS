#!/usr/bin/env python3
"""Server-ready, resumable execution plan and completion audit for V3."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path
from typing import Any, Iterable, Mapping

from capacity_study_v3_protocol import (
    EARLY_STOPPING_PATIENCE,
    ENCODER_DROPOUT,
    GRADIENT_CLIP_NORM,
    PROTOCOL_PATH,
    WEIGHT_DECAY,
    atomic_json,
    sha256_file,
    sha256_payload,
)
from capacity_study_v3_runs import run_manifest, validate_run_manifest


def unique_training_specs(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    validate_run_manifest(manifest)
    specs = list(manifest["core_runs"])
    specs.extend(
        row for row in manifest["fraction_runs"] if row["is_additional_fraction_run"]
    )
    if len(specs) != 270 or len({row["run_id"] for row in specs}) != 270:
        raise ValueError("Training execution grid must be 189 core + 81 additional runs")
    return specs


def completion_is_valid(path: Path, spec: Mapping[str, Any]) -> bool:
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if payload.get("status") != "pass" or payload.get("run_id") != spec["run_id"]:
        return False
    required = (
        "best_model",
        "best_weights",
        "history_csv",
        "run_config",
        "training_start",
        "training_data_integrity",
        "training_health",
        "parameters",
        "dataset_artifact_sha256",
    )
    if any(key not in payload for key in required):
        return False
    model = payload["best_model"]
    history = payload["history_csv"]
    if not (model.get("sha256_tree") or model.get("sha256")) or not history.get("sha256"):
        return False
    from train_prediction_model_v3 import artifact_hash, source_hashes

    for record in (
        model,
        payload["best_weights"],
        history,
        payload["run_config"],
        payload["training_start"],
        payload["training_data_integrity"],
        payload["training_health"],
    ):
        artifact_path = Path(str(record.get("path", "")))
        if not artifact_path.exists():
            return False
        actual = artifact_hash(artifact_path)
        identity = actual.get("sha256_tree") or actual.get("sha256")
        recorded_identity = record.get("sha256_tree") or record.get("sha256")
        if identity != recorded_identity:
            return False
    try:
        config = json.loads(Path(payload["run_config"]["path"]).read_text(encoding="utf-8"))
        if payload.get("formal_run") is not True:
            return False
        if config.get("max_train_samples") is not None or config.get("max_val_samples") is not None:
            return False
        if config.get("optimization") != {
            "optimizer": "adamw",
            "weight_decay": WEIGHT_DECAY,
            "gradient_clip_norm": GRADIENT_CLIP_NORM,
            "encoder_dropout": ENCODER_DROPOUT,
            "early_stopping_patience": EARLY_STOPPING_PATIENCE,
            "checkpoint_metric": "validation_rollout_macro_trajectory_mixture_NLL_per_step",
        }:
            return False
        data_integrity = json.loads(
            Path(payload["training_data_integrity"]["path"]).read_text(encoding="utf-8")
        )
        integrity_copy = dict(data_integrity)
        integrity_hash = integrity_copy.pop("audit_sha256", None)
        if (
            integrity_hash != sha256_payload(integrity_copy)
            or data_integrity.get("status") != "pass"
            or data_integrity.get("formal_mode") is not True
            or data_integrity.get("hard_failures")
            or data_integrity.get("train_validation_group_overlap")
            or data_integrity.get("train_validation_sample_overlap_count") != 0
        ):
            return False
        training_health = json.loads(
            Path(payload["training_health"]["path"]).read_text(encoding="utf-8")
        )
        health_copy = dict(training_health)
        health_hash = health_copy.pop("health_sha256", None)
        if (
            health_hash != sha256_payload(health_copy)
            or training_health.get("status") != "pass"
            or training_health.get("hard_checks_pass") is not True
            or training_health.get("formal_run") is not True
        ):
            return False
        optimizer = training_health.get("optimizer") or {}
        if (
            optimizer.get("name") != "adamw"
            or float(optimizer.get("weight_decay", -1.0)) != WEIGHT_DECAY
            or float(optimizer.get("gradient_clip_norm", -1.0)) != GRADIENT_CLIP_NORM
        ):
            return False
        start = json.loads(
            Path(payload["training_start"]["path"]).read_text(encoding="utf-8")
        )
        start_copy = dict(start)
        start_hash = start_copy.pop("record_sha256", None)
        if start_hash != sha256_payload(start_copy):
            return False
        if config.get("source_sha256") != source_hashes():
            return False
        if config.get("protocol_sha256") != sha256_file(PROTOCOL_PATH):
            return False
        if config.get("run_manifest_sha256") != sha256_file(config["run_manifest"]):
            return False
        if config.get("anchors_sha256") != sha256_file(config["anchors"]):
            return False
        if config.get("base_model_artifact") != artifact_hash(Path(config["base_model"])):
            return False
        if config.get("dataset_artifact_sha256") != payload["dataset_artifact_sha256"]:
            return False
        merged = Path(config["merged_dir"])
        live = {
            "train_jsonl": sha256_file(merged / "train.jsonl"),
            "val_jsonl": sha256_file(merged / "val.jsonl"),
            "day7_complete": sha256_file(merged / "DAY7_COMPLETE.json"),
            "model_implementation_complete": sha256_file(
                merged / "DAY7_MODEL_IMPLEMENTATION_COMPLETE.json"
            ),
            "interaction_normalization_train": (
                sha256_file(merged / "interaction_normalization_train.json")
                if (merged / "interaction_normalization_train.json").is_file()
                else None
            ),
        }
        if live != payload["dataset_artifact_sha256"]:
            return False
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        return False
    if payload.get("checkpoint_selection_metric") != (
        "validation_rollout_macro_trajectory_mixture_NLL_per_step"
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
            "data_fraction",
            "train_groups",
        )
    )


def training_plan(
    manifest: Mapping[str, Any],
    *,
    manifest_path: str | Path,
    merged_dir: str | Path,
    base_model: str | Path,
    anchors: str | Path,
    output_root: str | Path,
    python_bin: str,
    trainer: str | Path,
) -> dict[str, Any]:
    specs = unique_training_specs(manifest)
    output_root = Path(output_root)
    jobs = []
    for spec in specs:
        completion = output_root / spec["run_id"] / "TRAINING_COMPLETE.json"
        complete = completion_is_valid(completion, spec)
        argv = [
            python_bin,
            str(trainer),
            "--run-manifest",
            str(manifest_path),
            "--run-id",
            spec["run_id"],
            "--merged-dir",
            str(merged_dir),
            "--base-model",
            str(base_model),
            "--anchors",
            str(anchors),
            "--output-dir",
            str(output_root / spec["run_id"]),
        ]
        jobs.append(
            {
                "run_id": spec["run_id"],
                "kind": "core" if not spec["is_additional_fraction_run"] else "fraction",
                "status": "complete" if complete else "pending",
                "command_argv": argv,
                "command": shlex.join(argv),
                "completion": str(completion),
            }
        )
    return {
        "schema_version": "capacity_history_execution_plan_v3",
        "status": "pass",
        "planned_unique_runs": len(jobs),
        "core_runs": sum(row["kind"] == "core" for row in jobs),
        "additional_fraction_runs": sum(row["kind"] == "fraction" for row in jobs),
        "complete_runs": sum(row["status"] == "complete" for row in jobs),
        "pending_runs": sum(row["status"] == "pending" for row in jobs),
        "jobs": jobs,
    }


def audit_training(
    manifest: Mapping[str, Any], output_root: str | Path
) -> dict[str, Any]:
    root = Path(output_root)
    invalid = []
    complete = []
    for spec in unique_training_specs(manifest):
        path = root / spec["run_id"] / "TRAINING_COMPLETE.json"
        if completion_is_valid(path, spec):
            complete.append(spec["run_id"])
        else:
            invalid.append(spec["run_id"])
    return {
        "schema_version": "capacity_history_training_audit_v3",
        "status": "pass" if not invalid else "incomplete",
        "planned_unique_runs": 270,
        "complete_runs": len(complete),
        "invalid_or_missing_runs": invalid,
        "training_root": str(root.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--merged-dir", required=True, type=Path)
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--anchors", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--python-bin", default="python")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan-output", type=Path)
    parser.add_argument("--audit-output", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    plan = training_plan(
        manifest,
        manifest_path=args.manifest,
        merged_dir=args.merged_dir,
        base_model=args.base_model,
        anchors=args.anchors,
        output_root=args.output_root,
        python_bin=args.python_bin,
        trainer=Path(__file__).with_name("train_prediction_model_v3.py"),
    )
    if args.plan_output:
        atomic_json(args.plan_output, plan)
    if args.execute:
        import subprocess

        for job in plan["jobs"]:
            if job["status"] == "pending":
                subprocess.run(job["command_argv"], check=True)
    audit = audit_training(manifest, args.output_root)
    if args.audit_output:
        atomic_json(args.audit_output, audit)
    print(json.dumps({**audit, "manifest_sha256": sha256_file(args.manifest)}, indent=2))


if __name__ == "__main__":
    main()
