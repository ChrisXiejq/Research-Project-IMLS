#!/usr/bin/env python3
"""Calibration orchestration and fresh-test/deployment freeze for V3."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

from capacity_model_config_v3 import capacity_manifest
from capacity_study_v3_protocol import (
    PROTOCOL_PATH,
    load_protocol,
    sha256_file,
    sha256_payload,
    validate_capacity_count,
    validate_protocol,
    write_immutable_manifest,
)
from capacity_study_v3_runs import select_p_star


def _validate_checksum(payload: Mapping[str, Any], field: str) -> None:
    value = dict(payload)
    recorded = value.pop(field, None)
    value.pop("payload_sha256", None)
    if recorded != sha256_payload(value):
        raise ValueError(f"Hash mismatch for {field}")


def artifact_identity(payload: Mapping[str, Any]) -> str:
    for key in ("sha256", "sha256_tree", "tree_sha256"):
        value = payload.get(key)
        if value:
            return str(value)
    raise ValueError("Artifact record lacks a SHA-256 identity")


def calibration_jobs(
    selection: Mapping[str, Any],
    *,
    training_root: str | Path,
    output_root: str | Path,
    merged_dir: str | Path,
    anchors: str | Path,
) -> list[dict[str, Any]]:
    jobs = []
    for cell in selection["selected_cells"]:
        for run_id in cell["retained_run_ids"]:
            run_dir = Path(training_root) / run_id
            output_dir = Path(output_root) / run_id
            jobs.append(
                {
                    "job_id": f"calibrate__{run_id}",
                    "run_id": run_id,
                    "model_cell_id": cell["model_cell_id"],
                    "split": "val",
                    "model": str(run_dir / "best_model"),
                    "training_completion": str(run_dir / "TRAINING_COMPLETE.json"),
                    "merged_dir": str(Path(merged_dir)),
                    "anchors": str(Path(anchors)),
                    "calibration_output": str(output_dir / "calibration.json"),
                    "evaluation_output": str(output_dir / "validation_metrics.json"),
                    "require_complete_interaction_history": True,
                    "fit_calibration": True,
                }
            )
    if len(jobs) != 63 or len({row["run_id"] for row in jobs}) != 63:
        raise ValueError("Calibration plan must contain all 21 cells x 3 seeds")
    return jobs


def validate_calibration_record(
    record: Mapping[str, Any],
    *,
    expected_model_identity: str,
) -> None:
    if record.get("fit_split") not in {"val", "validation"}:
        raise ValueError("Calibration must be fitted on validation only")
    if record.get("calibration_fit_uses_test") is True:
        raise ValueError("Calibration record reports fresh-test access")
    parameters = record.get("parameters") or {}
    for name in ("temperature", "covariance_scale"):
        value = float(parameters[name])
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"Calibration parameter must be positive: {name}")
    if artifact_identity(record["model_artifact"]) != expected_model_identity:
        raise ValueError("Calibration/model hash binding mismatch")


def _representative_run(cell_selection: Mapping[str, Any]) -> str:
    scores = {int(seed): float(value) for seed, value in cell_selection["seed_scores"].items()}
    target = median(scores.values())
    chosen_seed = min(scores, key=lambda seed: (abs(scores[seed] - target), seed))
    suffix = f"__s{chosen_seed}__"
    matches = [run_id for run_id in cell_selection["retained_run_ids"] if suffix in run_id]
    if len(matches) != 1:
        raise ValueError("Could not identify representative validation-median seed")
    return matches[0]


def build_selection_freeze(
    *,
    selection: Mapping[str, Any],
    convergence: Mapping[str, Any],
    training_completions: Mapping[str, Mapping[str, Any]],
    calibration_records: Mapping[str, Mapping[str, Any]],
    latency_records: Mapping[str, Mapping[str, Any]],
    data_provenance: Mapping[str, Any],
    source_revision: str,
    data_efficiency_selection: Mapping[str, Any] | None = None,
    data_efficiency_convergence: Mapping[str, Any] | None = None,
    data_efficiency_training_completions: Mapping[str, Mapping[str, Any]] | None = None,
    data_efficiency_calibration_records: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    _validate_checksum(selection, "selection_sha256")
    if convergence.get("status") != "pass" or not convergence.get(
        "fresh_test_access_allowed"
    ):
        raise ValueError("Selection cannot freeze before convergence passes")
    protocol = load_protocol()
    validate_protocol(protocol)
    maximum_latency = float(
        protocol["deployment_selection"]["maximum_warmed_batch_one_latency_ms"]
    )
    frozen_capacity = capacity_manifest()
    expected_counts = {
        row["capacity_tier"]: row["trainable_parameters"]
        for row in frozen_capacity["head_configs"]
    }
    expected_counts.update(
        {
            (row["family"], row["history_horizon_s"], row["capacity_tier"]): row[
                "trainable_parameters"
            ]
            for row in frozen_capacity["encoder_configs"]
        }
    )

    cell_records = []
    eligibility = {}
    selected_by_cell = {row["model_cell_id"]: row for row in selection["selected_cells"]}
    required_run_ids = {
        run_id
        for row in selection["selected_cells"]
        for run_id in row["retained_run_ids"]
    }
    if set(training_completions) != required_run_ids:
        raise ValueError("Training completions must match all and only 63 retained runs")
    if set(calibration_records) != required_run_ids or set(latency_records) != required_run_ids:
        raise ValueError("Calibration and latency records must match all 63 retained runs")

    for cell_id, cell_selection in sorted(selected_by_cell.items()):
        per_seed = []
        for run_id in cell_selection["retained_run_ids"]:
            completion = training_completions[run_id]
            if completion.get("status") != "pass" or completion.get("run_id") != run_id:
                raise ValueError(f"Invalid training completion: {run_id}")
            model_identity = artifact_identity(completion["best_model"])
            validate_calibration_record(
                calibration_records[run_id], expected_model_identity=model_identity
            )
            latency = float(latency_records[run_id]["mean_ms"])
            if not math.isfinite(latency) or latency <= 0.0:
                raise ValueError(f"Invalid warmed latency: {run_id}")
            actual_parameters = int(completion["parameters"]["trainable_parameters"])
            family = str(completion["family"])
            tier = str(completion["capacity_tier"])
            horizon = completion.get("history_horizon_s")
            expected = (
                expected_counts[tier]
                if family == "head"
                else expected_counts[(family, float(horizon), tier)]
            )
            if actual_parameters != expected:
                raise ValueError(f"Frozen capacity mismatch for {run_id}")
            validate_capacity_count(actual_parameters, int(completion["capacity_config"]["trainable_parameters"]))
            per_seed.append(
                {
                    "run_id": run_id,
                    "seed": int(completion["seed"]),
                    "model_identity": model_identity,
                    "calibration_sha256": sha256_payload(calibration_records[run_id]),
                    "latency_ms": latency,
                    "trainable_parameters": actual_parameters,
                    "total_parameters": int(
                        completion["parameters"]["total_parameters"]
                    ),
                    "training_wall_time_s": float(
                        completion["training_wall_time_s"]
                    ),
                    "tensorflow_version": completion.get("tensorflow_version"),
                    "visible_devices": completion.get("visible_devices"),
                }
            )
        parameter_counts = {row["trainable_parameters"] for row in per_seed}
        if len(parameter_counts) != 1:
            raise ValueError(f"Capacity changes across seeds: {cell_id}")
        median_latency = median(row["latency_ms"] for row in per_seed)
        representative = _representative_run(cell_selection)
        cell_record = {
            "model_cell_id": cell_id,
            "selected_learning_rate": cell_selection["selected_learning_rate"],
            "median_validation_rollout_macro_nll": cell_selection[
                "median_validation_rollout_macro_nll"
            ],
            "representative_run_id": representative,
            "median_warmed_batch_one_latency_ms": median_latency,
            "retained_seeds": per_seed,
        }
        cell_records.append(cell_record)
        eligibility[cell_id] = {
            "converged": True,
            "capacity_audit_pass": True,
            "calibration_complete": True,
            "latency_gate_pass": median_latency <= maximum_latency,
            "trainable_parameters": next(iter(parameter_counts)),
            "warmed_batch_one_latency": median_latency,
        }

    p_star = select_p_star(selection, eligibility)
    p_star["representative_run_id"] = _representative_run(
        selected_by_cell[p_star["model_cell_id"]]
    )
    b1 = selected_by_cell["head-large"]
    data_efficiency = None
    if data_efficiency_selection is not None:
        if (
            not data_efficiency_convergence
            or data_efficiency_convergence.get("status") != "pass"
            or not data_efficiency_convergence.get("fresh_test_access_allowed")
        ):
            raise ValueError(
                "Data-efficiency selection cannot freeze before fraction convergence passes"
            )
        _validate_checksum(data_efficiency_selection, "selection_sha256")
        if data_efficiency_selection.get("selection_split") != "validation":
            raise ValueError("Data-efficiency selection must be validation-only")
        fraction_cells = data_efficiency_selection.get("selected_fraction_cells", [])
        if len(fraction_cells) != 12:
            raise ValueError("Data-efficiency freeze requires 3 families x 4 fractions")
        retained = {
            run_id for row in fraction_cells for run_id in row["retained_run_ids"]
        }
        core_retained = required_run_ids
        additional = retained - core_retained
        if len(retained) != 36 or len(additional) != 27:
            raise ValueError("Data-efficiency freeze must retain 36 entries/27 additional runs")
        fraction_training = data_efficiency_training_completions or {}
        fraction_calibration = data_efficiency_calibration_records or {}
        if set(fraction_training) != additional or set(fraction_calibration) != additional:
            raise ValueError("Missing additional data-efficiency training/calibration records")
        additional_records = []
        for run_id in sorted(additional):
            completion = fraction_training[run_id]
            if completion.get("status") != "pass" or completion.get("run_id") != run_id:
                raise ValueError(f"Invalid data-efficiency completion: {run_id}")
            model_identity = artifact_identity(completion["best_model"])
            validate_calibration_record(
                fraction_calibration[run_id], expected_model_identity=model_identity
            )
            additional_records.append(
                {
                    "run_id": run_id,
                    "model_identity": model_identity,
                    "calibration_sha256": sha256_payload(fraction_calibration[run_id]),
                }
            )
        data_efficiency = {
            "selection_sha256": data_efficiency_selection["selection_sha256"],
            "selected_fraction_cells": fraction_cells,
            "additional_retained_records": additional_records,
        }

    payload = {
        "schema_version": "capacity_history_selection_freeze_v3",
        "status": "pass",
        "fresh_test_access_allowed": True,
        "selection_uses_fresh_test": False,
        "source_revision": source_revision,
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "selection_sha256": selection["selection_sha256"],
        "convergence_sha256": sha256_payload(convergence),
        "capacity_manifest_sha256": sha256_payload(frozen_capacity),
        "data_provenance": dict(data_provenance),
        "maximum_warmed_batch_one_latency_ms": maximum_latency,
        "cells": cell_records,
        "B1": {
            "model_cell_id": "head-large",
            "representative_run_id": _representative_run(b1),
            "retained_run_ids": b1["retained_run_ids"],
        },
        "P_star": p_star,
        "data_efficiency": data_efficiency,
        "data_efficiency_convergence_sha256": (
            sha256_payload(data_efficiency_convergence)
            if data_efficiency_convergence is not None
            else None
        ),
    }
    payload["freeze_sha256"] = sha256_payload(payload)
    return payload


def validate_selection_freeze(payload: Mapping[str, Any]) -> None:
    _validate_checksum(payload, "freeze_sha256")
    if payload.get("status") != "pass" or not payload.get("fresh_test_access_allowed"):
        raise ValueError("Selection freeze does not unlock fresh evaluation")
    if payload.get("selection_uses_fresh_test") is not False:
        raise ValueError("Selection freeze is contaminated by fresh-test evidence")
    if payload.get("P_star", {}).get("family") not in {"mlp", "transformer"}:
        raise ValueError("P_star must be a validation-selected sequence model")


def fresh_evaluation_jobs(
    freeze: Mapping[str, Any],
    *,
    training_root: str | Path,
    calibration_root: str | Path,
    dataset_roots: Mapping[str, str | Path],
    output_root: str | Path,
    anchors: str | Path,
) -> list[dict[str, Any]]:
    validate_selection_freeze(freeze)
    if set(dataset_roots) != {"general_test", "interaction_challenge"}:
        raise ValueError("Both fresh dataset roots are required")
    jobs = []
    for cell in freeze["cells"]:
        for retained in cell["retained_seeds"]:
            run_id = retained["run_id"]
            for dataset, merged_dir in sorted(dataset_roots.items()):
                jobs.append(
                    {
                        "job_id": f"evaluate__{dataset}__{run_id}",
                        "dataset": dataset,
                        "run_id": run_id,
                        "model_cell_id": cell["model_cell_id"],
                        "model": str(Path(training_root) / run_id / "best_model"),
                        "calibration": str(Path(calibration_root) / run_id / "calibration.json"),
                        "merged_dir": str(Path(merged_dir)),
                        "anchors": str(Path(anchors)),
                        "output": str(Path(output_root) / dataset / f"{run_id}.json"),
                        "require_complete_interaction_history": True,
                        "interaction_ablation": "none",
                    }
                )
    if len(jobs) != 126 or len({row["job_id"] for row in jobs}) != 126:
        raise ValueError("Fresh evaluation requires 21 cells x 3 seeds x 2 datasets")
    return jobs


def freeze_to_path(path: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    validate_selection_freeze(payload)
    return write_immutable_manifest(path, payload)
