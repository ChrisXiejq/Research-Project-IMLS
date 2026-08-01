#!/usr/bin/env python3
"""Audit and rank Day 8 models using validation artifacts only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from statistics import median


VARIANTS = ("B1", "B2-M", "B2-D", "T1", "T2")
SEEDS = (11, 23, 37)
SUBSETS = ("all", "assertive", "reactive", "pre_response", "response_active")
REQUIRED_SUBSETS = ("all", "assertive", "reactive")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output-json", required=True)
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite validation metric: {label}={value}")
    return number


def metrics_for(payload: dict) -> dict:
    uncalibrated = payload["uncalibrated"]
    calibrated = payload.get("calibrated")
    if calibrated is None:
        raise ValueError("Validation evaluation is missing calibrated metrics")
    invalid = calibrated["probabilistic"]["covariance_audit"]["invalid_matrices"]
    if invalid:
        raise ValueError(f"Validation evaluation contains {invalid} invalid covariances")
    uncalibrated_macro = uncalibrated["rollout_aggregation"]["macro_mean"]
    calibrated_macro = calibrated["rollout_aggregation"]["macro_mean"]
    return {
        "status": "pass",
        "samples": int(payload["samples"]),
        "independent_rollouts": int(payload["independent_rollouts"]),
        "independent_init_groups": int(payload["independent_init_groups"]),
        "top1_ADE_mean": finite(uncalibrated["top1_ADE_mean"], "top1_ADE_mean"),
        "top1_FDE_mean": finite(uncalibrated["top1_FDE_mean"], "top1_FDE_mean"),
        "uncalibrated_trajectory_NLL_per_step_mean": finite(
            uncalibrated["trajectory_mixture_NLL_per_step_mean"], "uncalibrated_NLL"
        ),
        "calibrated_trajectory_NLL_per_step_mean": finite(
            calibrated["trajectory_mixture_NLL_per_step_mean"], "trajectory_NLL"
        ),
        "uncalibrated_rollout_macro_trajectory_NLL_per_step": finite(
            uncalibrated_macro["trajectory_mixture_NLL_per_step_mean"],
            "uncalibrated_macro_NLL",
        ),
        "calibrated_rollout_macro_trajectory_NLL_per_step": finite(
            calibrated_macro["trajectory_mixture_NLL_per_step_mean"], "calibrated_macro_NLL"
        ),
        "uncalibrated_coverage_mean_absolute_error": finite(
            uncalibrated["probabilistic"]["coverage_mean_absolute_error"],
            "uncalibrated_coverage_MAE",
        ),
        "calibrated_coverage_mean_absolute_error": finite(
            calibrated["probabilistic"]["coverage_mean_absolute_error"], "coverage_MAE"
        ),
        "mean_prediction_ms_per_sample": finite(
            payload["latency"]["mean_prediction_ms_per_sample"], "latency"
        ),
        "invalid_covariances": int(invalid),
    }


def main() -> None:
    args = parse_args()
    root = Path(args.results_dir).resolve()
    runs = []
    for variant in VARIANTS:
        for seed in SEEDS:
            run_dir = root / "runs" / variant / f"seed_{seed}"
            completion_path = run_dir / "TRAINING_COMPLETE.json"
            completion = json.loads(completion_path.read_text())
            if completion.get("status") != "pass":
                raise ValueError(f"Training gate failed: {completion_path}")
            subsets = {}
            for subset in SUBSETS:
                evaluation_path = run_dir / f"validation_{subset}.json"
                evaluation = json.loads(evaluation_path.read_text())
                status = evaluation.get("status")
                if (
                    evaluation.get("evaluation_schema_version")
                    != "multipath_accuracy_calibration_v2"
                ):
                    raise ValueError(f"Stale evaluation schema: {evaluation_path}")
                if evaluation.get("split") != "val":
                    raise ValueError(f"Invalid validation artifact: {evaluation_path}")
                if evaluation.get("subset") != subset:
                    raise ValueError(f"Subset mismatch: {evaluation_path}")
                if status == "not_applicable":
                    if subset in REQUIRED_SUBSETS:
                        raise ValueError(
                            f"Required validation subset is empty: {evaluation_path}"
                        )
                    if int(evaluation.get("samples", -1)) != 0:
                        raise ValueError(
                            f"not_applicable subset must have zero samples: {evaluation_path}"
                        )
                    subsets[subset] = {
                        "status": "not_applicable",
                        "samples": 0,
                        "independent_rollouts": 0,
                        "independent_init_groups": 0,
                        "reason": evaluation.get("reason"),
                    }
                elif status == "pass":
                    subsets[subset] = metrics_for(evaluation)
                else:
                    raise ValueError(f"Invalid validation artifact: {evaluation_path}")
            expected_groups = {
                "all": (20, 5),
                "assertive": (10, 5),
                "reactive": (10, 5),
            }
            for subset, (expected_rollouts, expected_inits) in expected_groups.items():
                observed = subsets[subset]
                if (
                    observed["independent_rollouts"] != expected_rollouts
                    or observed["independent_init_groups"] != expected_inits
                ):
                    raise ValueError(
                        f"{subset} grouping mismatch for {variant}/seed_{seed}: "
                        f"rollouts={observed['independent_rollouts']} inits={observed['independent_init_groups']}"
                    )
            runs.append(
                {
                    "variant": variant,
                    "seed": seed,
                    "training": {
                        "best_epoch": completion["best_epoch"],
                        "best_val_masked_nll": completion["best_val_masked_nll"],
                        "epochs_completed": completion["epochs_completed"],
                        "parameters": completion["parameters"],
                        "model_artifact": completion["best_model"],
                    },
                    "calibration": json.loads((run_dir / "calibration.json").read_text())["parameters"],
                    "subsets": subsets,
                    "artifact_sha256": {
                        "training_completion": sha256_file(completion_path),
                        **{
                            f"validation_{subset}": sha256_file(
                                run_dir / f"validation_{subset}.json"
                            )
                            for subset in SUBSETS
                        },
                    },
                }
            )

    subset_availability = {
        subset: {
            "pass_runs": sum(run["subsets"][subset]["status"] == "pass" for run in runs),
            "not_applicable_runs": sum(
                run["subsets"][subset]["status"] == "not_applicable" for run in runs
            ),
        }
        for subset in SUBSETS
    }
    pre_response_available = subset_availability["pre_response"]["pass_runs"] == len(runs)
    variants = []
    for variant in VARIANTS:
        group = [run for run in runs if run["variant"] == variant]
        primary = [
            run["subsets"]["all"]["uncalibrated_rollout_macro_trajectory_NLL_per_step"]
            for run in group
        ]
        reactive_ade = [run["subsets"]["reactive"]["top1_ADE_mean"] for run in group]
        pre_response_ade = (
            [run["subsets"]["pre_response"]["top1_ADE_mean"] for run in group]
            if pre_response_available
            else []
        )
        target = median(primary)
        representative = min(
            group,
            key=lambda run: (
                abs(
                    run["subsets"]["all"][
                        "uncalibrated_rollout_macro_trajectory_NLL_per_step"
                    ]
                    - target
                ),
                run["seed"],
            ),
        )
        variants.append(
            {
                "variant": variant,
                "seeds": [run["seed"] for run in group],
                "median_validation_rollout_macro_NLL": median(primary),
                "median_reactive_top1_ADE": median(reactive_ade),
                "median_pre_response_top1_ADE": (
                    median(pre_response_ade) if pre_response_ade else None
                ),
                "median_latency_ms_per_sample": median(
                    run["subsets"]["all"]["mean_prediction_ms_per_sample"] for run in group
                ),
                "representative_seed": representative["seed"],
                "representative_rule": "seed closest to the architecture median primary score; lower seed breaks exact ties",
            }
        )
    variants.sort(
        key=lambda item: (
            item["median_validation_rollout_macro_NLL"],
            item["median_reactive_top1_ADE"],
            (
                item["median_pre_response_top1_ADE"]
                if item["median_pre_response_top1_ADE"] is not None
                else float("inf")
            ),
        )
    )
    payload = {
        "schema_version": "day8_validation_summary_v2",
        "status": "pass",
        "selection_scope": "validation_only_test_untouched",
        "expected_runs": 15,
        "observed_runs": len(runs),
        "primary_ranking_metric": "median across seeds of validation rollout-macro uncalibrated trajectory mixture NLL per step",
        "calibration_role": "fitted on validation for deployment, reported for every run, but not used to rank architectures",
        "secondary_ranking_metrics": ["median reactive top1 ADE"]
        + (["median pre-response top1 ADE"] if pre_response_available else []),
        "subset_availability": subset_availability,
        "empty_optional_subset_policy": (
            "record not_applicable with zero samples; do not redefine the subset or use it for ranking"
        ),
        "provisional_selected_variant": variants[0]["variant"],
        "provisional_representative_seed": variants[0]["representative_seed"],
        "test_accessed": False,
        "variant_ranking": variants,
        "runs": runs,
    }
    output = Path(args.output_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(json.dumps({key: payload[key] for key in ("status", "observed_runs", "provisional_selected_variant", "provisional_representative_seed", "test_accessed")}, indent=2))


if __name__ == "__main__":
    main()
