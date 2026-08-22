#!/usr/bin/env python3
"""Build the complete provenance-indexed offline V3 synthesis from sealed outputs."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Mapping, Sequence

import numpy as np

from capacity_study_v3_analysis import (
    effect_summary,
    pareto_membership,
    synthesize_three_axes,
)
from capacity_study_v3_freeze import validate_selection_freeze
from capacity_study_v3_protocol import atomic_json, sha256_file


def _load(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _seed_from_run_id(run_id: str) -> int:
    match = re.search(r"__s(\d+)__", run_id)
    if not match:
        raise ValueError(f"Cannot infer seed from run id: {run_id}")
    return int(match.group(1))


def evaluation_rows(
    freeze: Mapping[str, Any], jobs: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    validate_selection_freeze(freeze)
    core_run_to_cell = {
        seed["run_id"]: cell["model_cell_id"]
        for cell in freeze["cells"]
        for seed in cell["retained_seeds"]
    }
    offline_rows = []
    mechanism_rows = []
    for job in jobs:
        path = Path(job["output"])
        if not path.is_file():
            raise ValueError(f"Missing fresh evaluation output: {job['job_id']}")
        report = _load(path)
        if report.get("status") != "pass":
            raise ValueError(f"Failed fresh evaluation: {job['job_id']}")
        run_id = str(job["run_id"])
        cell_id = str(job.get("model_cell_id") or core_run_to_cell[run_id])
        seed = _seed_from_run_id(run_id)
        calibrated = report.get("calibrated")
        if calibrated is None:
            raise ValueError(f"Fresh evaluation lacks calibration: {job['job_id']}")
        for group_key, metrics in calibrated["init_group_aggregation"]["per_init_group"].items():
            init_id = int(group_key.rsplit("_", 1)[-1])
            offline_rows.append(
                {
                    "dataset": job["dataset"],
                    "model_cell_id": cell_id,
                    "run_id": run_id,
                    "seed": seed,
                    "ego_init_id": init_id,
                    "rollout_id": group_key,
                    "rollout_macro_nll": metrics[
                        "trajectory_mixture_NLL_per_step_mean"
                    ],
                    "top1_ADE": metrics["top1_ADE_mean"],
                    "top1_FDE": metrics["top1_FDE_mean"],
                    "data_fraction": job.get("data_fraction", 1.0),
                    "source_artifact": str(path),
                    "source_sha256": sha256_file(path),
                }
            )
        for stratum, metrics in calibrated.get("response_strata_v3", {}).items():
            mechanism_rows.append(
                {
                    "dataset": job["dataset"],
                    "model_cell_id": cell_id,
                    "run_id": run_id,
                    "seed": seed,
                    "response_stratum": stratum,
                    "windows": metrics["windows"],
                    "independent_rollouts": metrics["independent_rollouts"],
                    "independent_init_groups": metrics["independent_init_groups"],
                    **metrics["rollout_macro"],
                    "source_artifact": str(path),
                }
            )
    return offline_rows, mechanism_rows


def _curve(rows: Sequence[Mapping[str, Any]], dataset: str) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for row in rows:
        if row["dataset"] == dataset and float(row.get("data_fraction", 1.0)) == 1.0:
            grouped[row["model_cell_id"]].append(float(row["rollout_macro_nll"]))
    return [
        {
            "model_cell_id": cell,
            "rollout_macro_nll_mean": float(np.mean(values)),
            "rollout_macro_nll_seed_group_sd": float(np.std(values, ddof=1)),
            "observations": len(values),
        }
        for cell, values in sorted(grouped.items())
    ]


def _matched_architecture(rows: Sequence[Mapping[str, Any]], dataset: str) -> list[dict[str, Any]]:
    results = []
    for horizon in ("h0p0", "h0p4", "h1p0"):
        for capacity in ("small", "medium", "large"):
            result = effect_summary(
                [row for row in rows if row["dataset"] == dataset],
                contrast_id=f"mlp_minus_transformer__{horizon}__{capacity}",
                terms=(
                    (f"mlp-{horizon}-{capacity}", 1.0),
                    (f"transformer-{horizon}-{capacity}", -1.0),
                ),
            )
            results.append(result)
    return results


def _data_efficiency(rows: Sequence[Mapping[str, Any]], dataset: str) -> list[dict[str, Any]]:
    grouped = defaultdict(list)
    for row in rows:
        if row["dataset"] == dataset and row["model_cell_id"] in {
            "head-large",
            "mlp-h1p0-large",
            "transformer-h1p0-large",
        }:
            grouped[(row["model_cell_id"], float(row["data_fraction"]))].append(
                float(row["rollout_macro_nll"])
            )
    return [
        {
            "model_cell_id": key[0],
            "data_fraction": key[1],
            "rollout_macro_nll_mean": float(np.mean(values)),
            "observations": len(values),
        }
        for key, values in sorted(grouped.items())
    ]


def build_offline_synthesis(
    freeze: Mapping[str, Any], jobs: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    rows, mechanisms = evaluation_rows(freeze, jobs)
    primary_rows = [row for row in rows if float(row.get("data_fraction", 1.0)) == 1.0]
    datasets = ("general_test", "interaction_challenge")
    three_axes = {
        dataset: synthesize_three_axes(primary_rows, dataset=dataset)
        for dataset in datasets
    }
    curves = {dataset: _curve(rows, dataset) for dataset in datasets}
    architecture = {
        dataset: _matched_architecture(primary_rows, dataset) for dataset in datasets
    }
    efficiency = {dataset: _data_efficiency(rows, dataset) for dataset in datasets}
    latency_rows = [
        {
            "id": cell["model_cell_id"],
            "rollout_macro_nll": cell["median_validation_rollout_macro_nll"],
            "mean_ms": cell["median_warmed_batch_one_latency_ms"],
        }
        for cell in freeze["cells"]
    ]
    compute_rows = [
        {
            "model_cell_id": cell["model_cell_id"],
            "run_id": seed["run_id"],
            "training_wall_time_s": seed["training_wall_time_s"],
            "trainable_parameters": seed["trainable_parameters"],
            "total_parameters": seed["total_parameters"],
            "tensorflow_version": seed.get("tensorflow_version"),
            "visible_devices": seed.get("visible_devices"),
        }
        for cell in freeze["cells"]
        for seed in cell["retained_seeds"]
    ]
    return {
        "schema_version": "capacity_history_offline_synthesis_v3",
        "status": "pass",
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "evaluated_rows": len(rows),
        "mechanism_summary_rows": len(mechanisms),
        "three_axes": three_axes,
        "capacity_and_horizon_curves": curves,
        "matched_architecture": architecture,
        "data_efficiency": efficiency,
        "mechanism_by_response_stratum": mechanisms,
        "validation_latency_pareto": pareto_membership(latency_rows),
        "training_compute": {
            "retained_seed_runs": compute_rows,
            "total_wall_time_s": float(
                sum(row["training_wall_time_s"] for row in compute_rows)
            ),
        },
        "B1_allocation": {
            dataset: [
                row for row in curves[dataset] if row["model_cell_id"].startswith("head-")
            ]
            for dataset in datasets
        },
        "P_star": freeze["P_star"],
        "claim_boundary": (
            "Effects are bounded to the frozen Town05 give-way distributions; null, "
            "mixed, and adverse results remain reportable and no safety, equivalence, "
            "foundation-mismatch, or universal-superiority claim follows automatically."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", required=True, type=Path)
    parser.add_argument("--evaluation-plan", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    freeze = _load(args.freeze)
    plan = _load(args.evaluation_plan)
    report = build_offline_synthesis(freeze, plan["jobs"])
    atomic_json(args.output, report)
    print(json.dumps({"status": "pass", "evaluated_rows": report["evaluated_rows"]}))


if __name__ == "__main__":
    main()
