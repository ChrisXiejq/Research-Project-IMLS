#!/usr/bin/env python3
"""Audit the single Day 8 test pass without changing validation selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path


VARIANTS = ("B1", "B2-M", "B2-D", "T1", "T2")
SUBSETS = ("all", "assertive", "reactive", "pre_response", "response_active")
REQUIRED_SUBSETS = ("all", "assertive", "reactive")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value: object, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite test metric: {label}={value}")
    return number


def metrics_for(payload: dict) -> dict:
    uncalibrated = payload["uncalibrated"]
    calibrated = payload.get("calibrated")
    if calibrated is None:
        raise ValueError("Test evaluation is missing validation-frozen calibration")
    invalid = int(calibrated["probabilistic"]["covariance_audit"]["invalid_matrices"])
    if invalid:
        raise ValueError(f"Test evaluation contains {invalid} invalid covariances")
    u_macro = uncalibrated["rollout_aggregation"]["macro_mean"]
    c_macro = calibrated["rollout_aggregation"]["macro_mean"]
    return {
        "status": "pass",
        "samples": int(payload["samples"]),
        "independent_rollouts": int(payload["independent_rollouts"]),
        "independent_init_groups": int(payload["independent_init_groups"]),
        "top1_ADE_mean": finite(uncalibrated["top1_ADE_mean"], "ADE"),
        "top1_FDE_mean": finite(uncalibrated["top1_FDE_mean"], "FDE"),
        "uncalibrated_rollout_macro_NLL": finite(
            u_macro["trajectory_mixture_NLL_per_step_mean"], "uncalibrated macro NLL"
        ),
        "calibrated_rollout_macro_NLL": finite(
            c_macro["trajectory_mixture_NLL_per_step_mean"], "calibrated macro NLL"
        ),
        "uncalibrated_coverage_MAE": finite(
            uncalibrated["probabilistic"]["coverage_mean_absolute_error"], "coverage MAE"
        ),
        "calibrated_coverage_MAE": finite(
            calibrated["probabilistic"]["coverage_mean_absolute_error"], "calibrated coverage MAE"
        ),
        "mean_prediction_ms_per_sample": finite(
            payload["latency"]["mean_prediction_ms_per_sample"], "latency"
        ),
        "invalid_covariances": invalid,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--test-dir", required=True)
    parser.add_argument("--selection-json", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    root = Path(args.results_dir).resolve()
    test_dir = Path(args.test_dir).resolve()
    selection_path = Path(args.selection_json).resolve()
    selection = json.loads(selection_path.read_text())
    if selection.get("status") != "pass" or not selection.get(
        "closed_loop_selection_locked_before_test"
    ):
        raise ValueError("Invalid pre-test selection freeze")

    representatives = selection["representatives_for_single_test_pass"]
    runs = []
    for variant in VARIANTS:
        frozen = representatives[variant]
        seed = int(frozen["seed"])
        expected_model_hash = frozen["model"]["sha256_tree"]
        expected_parameters = frozen["calibration_parameters"]
        subsets = {}
        artifact_hashes = {}
        for subset in SUBSETS:
            path = test_dir / variant / f"seed_{seed}" / f"test_{subset}.json"
            payload = json.loads(path.read_text())
            artifact_hashes[f"test_{subset}"] = sha256_file(path)
            if payload.get("evaluation_schema_version") != "multipath_accuracy_calibration_v2":
                raise ValueError(f"Stale test evaluation schema: {path}")
            if payload.get("split") != "test" or payload.get("subset") != subset:
                raise ValueError(f"Test split/subset mismatch: {path}")
            if payload.get("calibration_fit_uses_test") is not False:
                raise ValueError(f"Test leakage flag failed: {path}")
            if payload.get("model_artifact", {}).get("sha256_tree") != expected_model_hash:
                raise ValueError(f"Frozen model hash mismatch: {path}")
            calibration = payload.get("calibration") or {}
            if calibration.get("fit_split") != "val":
                raise ValueError(f"Calibration was not fitted on validation: {path}")
            if calibration.get("parameters") != expected_parameters:
                raise ValueError(f"Frozen calibration parameters mismatch: {path}")

            status = payload.get("status")
            if status == "pass":
                subsets[subset] = metrics_for(payload)
            elif status == "not_applicable" and subset not in REQUIRED_SUBSETS:
                if int(payload.get("samples", -1)) != 0:
                    raise ValueError(f"Empty subset has nonzero samples: {path}")
                subsets[subset] = {
                    "status": "not_applicable",
                    "samples": 0,
                    "independent_rollouts": 0,
                    "independent_init_groups": 0,
                    "reason": payload.get("reason"),
                }
            else:
                raise ValueError(f"Required test evaluation did not pass: {path}")

        for subset, expected in {
            "all": (20, 5),
            "assertive": (10, 5),
            "reactive": (10, 5),
        }.items():
            observed = subsets[subset]
            if (observed["independent_rollouts"], observed["independent_init_groups"]) != expected:
                raise ValueError(f"Test grouping mismatch for {variant}/{subset}: {observed}")
        if subsets["all"]["samples"] != (
            subsets["assertive"]["samples"] + subsets["reactive"]["samples"]
        ):
            raise ValueError(f"Test style partition is incomplete for {variant}")
        runs.append(
            {
                "variant": variant,
                "seed": seed,
                "validation_rank": int(frozen["validation_rank"]),
                "subsets": subsets,
                "artifact_sha256": artifact_hashes,
            }
        )

    test_ranking = sorted(
        (
            {
                "variant": run["variant"],
                "seed": run["seed"],
                "test_rollout_macro_NLL": run["subsets"]["all"][
                    "uncalibrated_rollout_macro_NLL"
                ],
                "test_reactive_top1_ADE": run["subsets"]["reactive"]["top1_ADE_mean"],
            }
            for run in runs
        ),
        key=lambda item: (item["test_rollout_macro_NLL"], item["test_reactive_top1_ADE"]),
    )
    payload = {
        "schema_version": "day8_frozen_test_summary_v1",
        "status": "pass",
        "test_accessed": True,
        "test_pass_policy": "one evaluation pass over all five validation-frozen representatives",
        "test_used_for_selection": False,
        "retraining_or_retuning_after_test_permitted": False,
        "selection_freeze": {
            "path": str(selection_path),
            "sha256": sha256_file(selection_path),
        },
        "closed_loop_selected_variant": selection["closed_loop_selected_variant"],
        "closed_loop_selected_seed": selection["closed_loop_selected_seed"],
        "test_ranking_for_reporting_only": test_ranking,
        "runs": runs,
    }
    output = Path(args.output_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps({
        "status": "pass",
        "closed_loop_selected_variant": payload["closed_loop_selected_variant"],
        "closed_loop_selected_seed": payload["closed_loop_selected_seed"],
        "test_used_for_selection": False,
    }, indent=2))


if __name__ == "__main__":
    main()
