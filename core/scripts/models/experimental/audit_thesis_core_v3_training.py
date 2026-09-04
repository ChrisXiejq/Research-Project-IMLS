#!/usr/bin/env python3
"""Deep integrity, convergence, and capacity audit for the 27 thesis-core runs."""

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
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from capacity_model_config_v3 import capacity_manifest
from capacity_study_v3_protocol import (
    BOUNDARY_WINDOW_EPOCHS,
    CORE_EPOCHS,
    THESIS_CORE_RUN_COUNT,
    atomic_json,
    sha256_file,
    sha256_payload,
)
from thesis_core_v3_execute import completion_valid
from thesis_core_v3_runs import validate_thesis_core_manifest
from training_epoch_integrity_v4 import inspect_epoch_artifacts


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def audit(manifest_path: Path, training_root: Path) -> dict[str, Any]:
    manifest = _load(manifest_path)
    validate_thesis_core_manifest(manifest)
    invalid: list[str] = []
    rows: list[dict[str, Any]] = []
    source_identities: Counter[str] = Counter()
    cache_identities: Counter[str] = Counter()
    dataset_identities: Counter[str] = Counter()
    by_cell: dict[str, list[dict[str, Any]]] = defaultdict(list)
    capacity = capacity_manifest()
    expected_parameters = {
        f"head-{row['capacity_tier']}": int(row["trainable_parameters"])
        for row in capacity["head_configs"]
    }
    expected_parameters.update(
        {
            (
                f"{row['family']}-h{float(row['history_horizon_s']):.1f}"
                f"-{row['capacity_tier']}"
            ).replace(".", "p"): int(row["trainable_parameters"])
            for row in capacity["encoder_configs"]
        }
    )

    for spec in manifest["runs"]:
        run_id = str(spec["run_id"])
        directory = training_root / run_id
        completion_path = directory / "TRAINING_COMPLETE.json"
        if not completion_valid(completion_path, spec):
            invalid.append(run_id)
            continue
        completion = _load(completion_path)
        health = _load(directory / "training_health.json")
        parity = _load(directory / "cached_full_parity.json")
        parameters = _load(directory / "parameters.json")
        config = _load(directory / "run_config.json")
        history_path = directory / "history.csv"
        epoch_integrity = inspect_epoch_artifacts(
            history_path,
            directory / "epoch_checkpoints",
            backup_dir=directory / "resume_backup",
            validate_hdf5=True,
        )
        if epoch_integrity.get("status") != "pass":
            invalid.append(f"{run_id}:epoch_artifact_integrity")
            continue
        history = np.genfromtxt(history_path, delimiter=",", names=True)
        scores = np.atleast_1d(history["val_rollout_macro_nll"]).astype(float)
        epoch_indices = np.atleast_1d(history["epoch"]).astype(int)
        best_score = float(np.min(scores))
        best_epoch = int(epoch_indices[int(np.argmin(scores))]) + 1
        if best_epoch != int(completion["best_epoch"]):
            invalid.append(f"{run_id}:best_epoch_drift")
            continue
        if (
            int(health.get("epochs_completed", -1)) != len(scores)
            or int(health.get("per_epoch_checkpoints", -1)) != len(scores)
        ):
            invalid.append(f"{run_id}:epoch_count_drift")
            continue
        source_identity = sha256_payload(config["source_sha256"])
        source_identities[source_identity] += 1
        cache_identities[str(completion["cache_complete_sha256"])] += 1
        dataset_identities[str(completion["dataset_complete_sha256"])] += 1
        cached_parameters = parameters["cached_trainable"]
        row = {
            "run_id": run_id,
            "model_cell_id": spec["model_cell_id"],
            "family": spec["family"],
            "capacity_tier": spec["capacity_tier"],
            "history_horizon_s": spec["history_horizon_s"],
            "seed": int(spec["seed"]),
            "learning_rate": float(spec["learning_rate"]),
            "best_epoch": best_epoch,
            "epochs_completed": int(health["epochs_completed"]),
            "epochs_allowed": CORE_EPOCHS,
            "boundary_limited": best_epoch > CORE_EPOCHS - BOUNDARY_WINDOW_EPOCHS,
            "validation_rollout_macro_nll": best_score,
            "gradient_global_norm": float(
                health["gradient_audit"]["gradient_global_norm"]
            ),
            "maximum_trainable_weight_change": float(
                health["maximum_trainable_weight_change"]
            ),
            "cached_full_maximum_absolute_error": float(
                parity["maximum_absolute_error"]
            ),
            "trainable_parameters": int(cached_parameters["trainable_parameters"]),
            "total_cached_parameters": int(cached_parameters["total_parameters"]),
            "training_wall_time_s": float(health["training_wall_time_s"]),
            "completion_sha256": str(completion["completion_sha256"]),
            "source_identity": source_identity,
            "epoch_artifact_integrity": "pass",
        }
        if (
            not np.isfinite(row["validation_rollout_macro_nll"])
            or row["gradient_global_norm"] <= 0.0
            or row["maximum_trainable_weight_change"] <= 0.0
            or parity.get("status") != "pass"
            or health.get("hard_checks_pass") is not True
            or row["trainable_parameters"] != expected_parameters[row["model_cell_id"]]
        ):
            invalid.append(f"{run_id}:health_gate")
            continue
        rows.append(row)
        by_cell[row["model_cell_id"]].append(row)

    cell_summaries = []
    for cell_id, members in sorted(by_cell.items()):
        seeds = {row["seed"] for row in members}
        parameter_counts = {row["trainable_parameters"] for row in members}
        if seeds != {11, 23, 37} or len(parameter_counts) != 1:
            invalid.append(f"{cell_id}:seed_or_capacity_support")
            continue
        values = [row["validation_rollout_macro_nll"] for row in members]
        cell_summaries.append(
            {
                "model_cell_id": cell_id,
                "median_validation_rollout_macro_nll": float(np.median(values)),
                "mean_validation_rollout_macro_nll": float(np.mean(values)),
                "seed_sd_validation_rollout_macro_nll": float(np.std(values, ddof=1)),
                "trainable_parameters": next(iter(parameter_counts)),
                "boundary_runs": sum(row["boundary_limited"] for row in members),
                "retained_run_ids": sorted(row["run_id"] for row in members),
                "seed_scores": {
                    str(row["seed"]): row["validation_rollout_macro_nll"]
                    for row in sorted(members, key=lambda value: value["seed"])
                },
            }
        )

    if len(rows) != THESIS_CORE_RUN_COUNT:
        invalid.append(f"valid_run_count:{len(rows)}")
    if len(cell_summaries) != 9:
        invalid.append(f"valid_cell_count:{len(cell_summaries)}")
    if len(source_identities) != 1:
        invalid.append("source_identity_not_uniform")
    if len(cache_identities) != 1:
        invalid.append("cache_identity_not_uniform")
    if len(dataset_identities) != 1:
        invalid.append("dataset_identity_not_uniform")

    payload = {
        "schema_version": "capacity_history_thesis_core_training_audit_v4_masked",
        "status": "pass" if not invalid else "fail",
        "evidence_status": "retrospective_held_out",
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "training_root": str(training_root.resolve()),
        "planned_runs": THESIS_CORE_RUN_COUNT,
        "valid_runs": len(rows),
        "invalid_runs_or_gates": invalid,
        "source_identity_counts": dict(source_identities),
        "cache_identity_counts": dict(cache_identities),
        "dataset_identity_counts": dict(dataset_identities),
        "maximum_cached_full_absolute_error": max(
            (row["cached_full_maximum_absolute_error"] for row in rows), default=None
        ),
        "boundary_limited_runs": sum(row["boundary_limited"] for row in rows),
        "convergence_interpretation": {
            "protocol_budget_epochs": CORE_EPOCHS,
            "boundary_window_epochs": BOUNDARY_WINDOW_EPOCHS,
            "post_outcome_budget_extension_allowed": False,
            "boundary_limitation_requires_pre_freeze_tail_materiality_audit": True,
        },
        "future_validity_contract": "future_valid_mask_fail_closed_v4",
        "cells": cell_summaries,
        "runs": rows,
    }
    payload["audit_sha256"] = sha256_payload(payload)
    if invalid:
        raise ValueError(f"Thesis-core training audit failed: {invalid}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--training-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.manifest, args.training_root)
    atomic_json(args.output, report)
    print(json.dumps({
        "status": report["status"],
        "valid_runs": report["valid_runs"],
        "boundary_limited_runs": report["boundary_limited_runs"],
        "maximum_cached_full_absolute_error": report["maximum_cached_full_absolute_error"],
        "audit_sha256": report["audit_sha256"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
