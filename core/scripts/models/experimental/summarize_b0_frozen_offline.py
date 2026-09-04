#!/usr/bin/env python3
"""Summarize a post-selection B0 offline bridge without changing Day 8 selection."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

from summarize_day8_frozen_test import metrics_for


SUBSETS = ("all", "assertive", "reactive", "pre_response", "response_active")
REQUIRED_SUBSETS = ("all", "assertive", "reactive")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finite(value: Any, label: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Non-finite {label}: {value}")
    return number


def metric_contrasts(b1: dict[str, Any], b0: dict[str, Any]) -> dict[str, float]:
    fields = (
        "top1_ADE_mean",
        "top1_FDE_mean",
        "uncalibrated_rollout_macro_NLL",
        "calibrated_rollout_macro_NLL",
        "uncalibrated_coverage_MAE",
        "calibrated_coverage_MAE",
        "mean_prediction_ms_per_sample",
    )
    return {
        f"B1_minus_B0_{field}": finite(b1[field], f"B1 {field}")
        - finite(b0[field], f"B0 {field}")
        for field in fields
    }


def summarize(
    results_dir: Path,
    day8_summary_path: Path,
    day10_contract_path: Path,
) -> dict[str, Any]:
    day8 = json.loads(day8_summary_path.read_text())
    contract = json.loads(day10_contract_path.read_text())
    if day8.get("status") != "pass" or day8.get("test_used_for_selection") is not False:
        raise ValueError("Day 8 frozen test summary is invalid")
    if day8.get("closed_loop_selected_variant") != "B1":
        raise ValueError("B1 was not the validation-frozen selected variant")
    if contract.get("status") != "frozen" or not contract.get("no_post_result_tuning"):
        raise ValueError("Day 10 contract is not frozen")
    expected_b0_hash = contract["predictors"]["B0"]["model_sha256_tree"]
    b1_run = next(run for run in day8["runs"] if run["variant"] == "B1")

    calibration_path = results_dir / "b0_validation_calibration.json"
    validation_path = results_dir / "b0_validation_evaluation.json"
    calibration = json.loads(calibration_path.read_text())
    validation = json.loads(validation_path.read_text())
    if calibration.get("fit_split") != "val":
        raise ValueError("B0 calibration was not fitted on validation")
    if calibration.get("model_artifact", {}).get("sha256_tree") != expected_b0_hash:
        raise ValueError("B0 validation calibration model hash mismatch")
    if validation.get("split") != "val" or validation.get("subset") != "all":
        raise ValueError("B0 validation evaluation split/subset mismatch")
    if validation.get("model_artifact", {}).get("sha256_tree") != expected_b0_hash:
        raise ValueError("B0 validation evaluation model hash mismatch")

    subsets: dict[str, Any] = {}
    artifacts = {
        "b0_validation_calibration": sha256(calibration_path),
        "b0_validation_evaluation": sha256(validation_path),
    }
    for subset in SUBSETS:
        path = results_dir / f"b0_test_{subset}.json"
        payload = json.loads(path.read_text())
        artifacts[f"b0_test_{subset}"] = sha256(path)
        if payload.get("evaluation_schema_version") != "multipath_accuracy_calibration_v2":
            raise ValueError(f"B0 evaluation schema mismatch: {path}")
        if payload.get("split") != "test" or payload.get("subset") != subset:
            raise ValueError(f"B0 test split/subset mismatch: {path}")
        if payload.get("model_artifact", {}).get("sha256_tree") != expected_b0_hash:
            raise ValueError(f"B0 frozen model hash mismatch: {path}")
        if payload.get("calibration_fit_uses_test") is not False:
            raise ValueError(f"B0 test leakage flag failed: {path}")
        if (payload.get("calibration") or {}).get("parameters") != calibration.get("parameters"):
            raise ValueError(f"B0 validation calibration drift: {path}")

        if payload.get("status") == "not_applicable" and subset not in REQUIRED_SUBSETS:
            if int(payload.get("samples", -1)) != 0:
                raise ValueError(f"Empty subset has nonzero samples: {path}")
            subsets[subset] = {
                "status": "not_applicable",
                "samples": 0,
                "reason": payload.get("reason"),
            }
            continue
        if payload.get("status") != "pass":
            raise ValueError(f"Required B0 evaluation did not pass: {path}")
        b0_metrics = metrics_for(payload)
        b1_metrics = b1_run["subsets"][subset]
        if b1_metrics.get("status") != "pass":
            raise ValueError(f"B1 reference subset is unavailable: {subset}")
        if (
            b0_metrics["samples"],
            b0_metrics["independent_rollouts"],
            b0_metrics["independent_init_groups"],
        ) != (
            b1_metrics["samples"],
            b1_metrics["independent_rollouts"],
            b1_metrics["independent_init_groups"],
        ):
            raise ValueError(f"B0/B1 test population mismatch: {subset}")
        subsets[subset] = {
            "status": "pass",
            "B0": b0_metrics,
            "B1": b1_metrics,
            "contrasts": metric_contrasts(b1_metrics, b0_metrics),
        }

    for subset, expected in {"all": (20, 5), "assertive": (10, 5), "reactive": (10, 5)}.items():
        observed = subsets[subset]["B0"]
        if (observed["independent_rollouts"], observed["independent_init_groups"]) != expected:
            raise ValueError(f"B0 grouping mismatch for {subset}: {observed}")

    return {
        "schema_version": "b0_frozen_offline_bridge_v1",
        "status": "pass",
        "role": "post-selection gap completion; reporting only",
        "test_used_for_selection": False,
        "retraining_or_retuning_after_test_permitted": False,
        "closed_loop_selection_unchanged": {"variant": "B1", "seed": int(b1_run["seed"])},
        "comparison_scope": {
            "uncalibrated": "model adaptation contrast under the shared identity GMM decoder",
            "calibrated": "deployment-package contrast using separately validation-fitted calibration",
            "closed_loop_B0_calibration": "identity; calibrated B0 is not retroactively substituted into Day 10",
        },
        "B0_model_sha256_tree": expected_b0_hash,
        "B0_validation_calibration_parameters": calibration["parameters"],
        "subsets": subsets,
        "source_sha256": {
            "day8_frozen_test_summary": sha256(day8_summary_path),
            "day10_run_contract": sha256(day10_contract_path),
            **artifacts,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--day8-test-summary", required=True, type=Path)
    parser.add_argument("--day10-contract", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    args = parser.parse_args()
    payload = summarize(
        args.results_dir.resolve(),
        args.day8_test_summary.resolve(),
        args.day10_contract.resolve(),
    )
    output = args.output_json.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps({"status": "pass", "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
