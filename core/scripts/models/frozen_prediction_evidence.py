#!/usr/bin/env python3
"""Shared readers for aggregation-safe frozen prediction evidence.

The summary JSONs intentionally retain historical window-micro ADE/FDE fields.
Paper-facing consumers must therefore obtain NLL, ADE and FDE from the explicit
``rollout_aggregation.macro_mean`` object in each frozen evaluation artifact.
This module centralises that contract and cross-checks the summaries only for
identity, selection, counts, latency and rollout-macro NLL.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping


TEST_VARIANT_SEEDS = {
    "B1": 37,
    "B2-M": 37,
    "B2-D": 11,
    "T1": 23,
    "T2": 23,
}
VALIDATION_VARIANTS = ("B1", "B2-M", "B2-D", "T1", "T2")
VALIDATION_SEEDS = (11, 23, 37)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return payload


def finite(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite value for {label}: {value!r}")
    return result


def close(left: Any, right: Any, label: str) -> None:
    if not math.isclose(
        finite(left, f"{label}:left"),
        finite(right, f"{label}:right"),
        rel_tol=1.0e-10,
        abs_tol=1.0e-12,
    ):
        raise ValueError(f"Frozen summary/evaluation mismatch for {label}: {left} != {right}")


def frozen_test_evaluation_paths(repo: Path) -> dict[str, Path]:
    root = repo / "docs/paper/generated"
    paths = {
        "B0": root / "day10/gaps/b0_offline/b0_test_all.json",
    }
    for variant, seed in TEST_VARIANT_SEEDS.items():
        paths[variant] = (
            root / f"day8/final_test/{variant}/seed_{seed}/test_all.json"
        )
    return paths


def frozen_validation_evaluation_paths(repo: Path) -> dict[tuple[str, int], Path]:
    root = repo / "docs/paper/generated/day8/final_validation/runs"
    return {
        (variant, seed): root / variant / f"seed_{seed}" / "validation_all.json"
        for variant in VALIDATION_VARIANTS
        for seed in VALIDATION_SEEDS
    }


def rollout_macro_record(
    path: Path,
    *,
    variant: str,
    seed: int | None,
    split: str,
    validation_rank: int | None,
) -> dict[str, Any]:
    payload = load_json(path)
    if payload.get("status") != "pass" or payload.get("split") != split:
        raise ValueError(f"Frozen evaluation gate failed for {variant}: {path}")
    uncalibrated = payload["uncalibrated"]["rollout_aggregation"]
    calibrated = payload["calibrated"]["rollout_aggregation"]
    uncalibrated_macro = uncalibrated["macro_mean"]
    calibrated_macro = calibrated["macro_mean"]
    rollouts = int(payload["independent_rollouts"])
    init_groups = int(payload["independent_init_groups"])
    samples = int(payload["samples"])
    if int(uncalibrated["independent_rollouts"]) != rollouts:
        raise ValueError(f"Rollout count mismatch for {variant}: {path}")
    if samples <= 0 or rollouts <= 0 or init_groups <= 0:
        raise ValueError(f"Non-positive frozen evaluation counts for {variant}: {path}")
    return {
        "variant": variant,
        "seed": seed,
        "validation_rank": validation_rank,
        "aggregation_level": "rollout_macro",
        "samples": samples,
        "independent_rollouts": rollouts,
        "independent_init_groups": init_groups,
        "uncalibrated_rollout_macro_NLL": finite(
            uncalibrated_macro["trajectory_mixture_NLL_per_step_mean"],
            f"{variant}:uncalibrated rollout-macro NLL",
        ),
        "rollout_macro_top1_ADE_m": finite(
            uncalibrated_macro["top1_ADE_mean"],
            f"{variant}:rollout-macro ADE",
        ),
        "rollout_macro_top1_FDE_m": finite(
            uncalibrated_macro["top1_FDE_mean"],
            f"{variant}:rollout-macro FDE",
        ),
        "calibrated_rollout_macro_NLL": finite(
            calibrated_macro["trajectory_mixture_NLL_per_step_mean"],
            f"{variant}:calibrated rollout-macro NLL",
        ),
        "mean_prediction_ms_per_sample": finite(
            payload["latency"]["mean_prediction_ms_per_sample"],
            f"{variant}:latency",
        ),
        "source_path": path,
    }


def _cross_check_summary(
    record: Mapping[str, Any], summary: Mapping[str, Any], label: str
) -> None:
    if summary.get("status") != "pass":
        raise ValueError(f"Summary row is not pass for {label}")
    for record_key, summary_key in (
        ("samples", "samples"),
        ("independent_rollouts", "independent_rollouts"),
        ("independent_init_groups", "independent_init_groups"),
    ):
        if int(record[record_key]) != int(summary[summary_key]):
            raise ValueError(f"Count mismatch for {label}:{record_key}")
    close(
        record["uncalibrated_rollout_macro_NLL"],
        summary.get(
            "uncalibrated_rollout_macro_NLL",
            summary.get("uncalibrated_rollout_macro_trajectory_NLL_per_step"),
        ),
        f"{label}:uncalibrated rollout-macro NLL",
    )
    close(
        record["calibrated_rollout_macro_NLL"],
        summary.get(
            "calibrated_rollout_macro_NLL",
            summary.get("calibrated_rollout_macro_trajectory_NLL_per_step"),
        ),
        f"{label}:calibrated rollout-macro NLL",
    )
    close(
        record["mean_prediction_ms_per_sample"],
        summary["mean_prediction_ms_per_sample"],
        f"{label}:latency",
    )


def frozen_test_rollout_records(
    repo: Path,
    test_summary: Mapping[str, Any],
    b0_summary: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if (
        test_summary.get("status") != "pass"
        or test_summary.get("test_used_for_selection") is not False
        or test_summary.get("retraining_or_retuning_after_test_permitted") is not False
    ):
        raise ValueError("Frozen test selection/separation gate failed")
    if (
        b0_summary.get("status") != "pass"
        or b0_summary.get("test_used_for_selection") is not False
        or b0_summary.get("retraining_or_retuning_after_test_permitted") is not False
    ):
        raise ValueError("B0 reporting bridge gate failed")

    summary_runs = {str(row["variant"]): row for row in test_summary["runs"]}
    if {name: int(row["seed"]) for name, row in summary_runs.items()} != TEST_VARIANT_SEEDS:
        raise ValueError("Frozen test representative variants/seeds changed")

    paths = frozen_test_evaluation_paths(repo)
    records: list[dict[str, Any]] = []
    b0 = rollout_macro_record(
        paths["B0"], variant="B0", seed=None, split="test", validation_rank=None
    )
    if sha256_file(paths["B0"]) != b0_summary["source_sha256"]["b0_test_all"]:
        raise ValueError("B0 frozen evaluation hash mismatch")
    _cross_check_summary(b0, b0_summary["subsets"]["all"]["B0"], "B0/test")
    records.append(b0)

    for variant, run in sorted(
        summary_runs.items(), key=lambda item: int(item[1]["validation_rank"])
    ):
        path = paths[variant]
        if sha256_file(path) != run["artifact_sha256"]["test_all"]:
            raise ValueError(f"Frozen test artifact hash mismatch: {variant}")
        record = rollout_macro_record(
            path,
            variant=variant,
            seed=int(run["seed"]),
            split="test",
            validation_rank=int(run["validation_rank"]),
        )
        _cross_check_summary(record, run["subsets"]["all"], f"{variant}/test")
        records.append(record)

    if any(
        (int(row["samples"]), int(row["independent_rollouts"]), int(row["independent_init_groups"]))
        != (315, 20, 5)
        for row in records
    ):
        raise ValueError("Frozen test population is not the registered 315/20/5 contract")
    return records


def frozen_validation_rollout_records(
    repo: Path, validation_summary: Mapping[str, Any]
) -> list[dict[str, Any]]:
    if (
        validation_summary.get("status") != "pass"
        or validation_summary.get("test_accessed") is not False
    ):
        raise ValueError("Validation/test separation gate failed")
    summary_runs = {
        (str(row["variant"]), int(row["seed"])): row
        for row in validation_summary["runs"]
    }
    expected = {
        (variant, seed)
        for variant in VALIDATION_VARIANTS
        for seed in VALIDATION_SEEDS
    }
    if set(summary_runs) != expected:
        raise ValueError("Validation matrix is not the complete 5x3 contract")

    records: list[dict[str, Any]] = []
    for key, path in frozen_validation_evaluation_paths(repo).items():
        variant, seed = key
        run = summary_runs[key]
        if sha256_file(path) != run["artifact_sha256"]["validation_all"]:
            raise ValueError(f"Validation artifact hash mismatch: {variant}/seed{seed}")
        record = rollout_macro_record(
            path,
            variant=variant,
            seed=seed,
            split="val",
            validation_rank=None,
        )
        _cross_check_summary(record, run["subsets"]["all"], f"{variant}/seed{seed}/val")
        record["best_epoch"] = int(run["training"]["best_epoch"])
        record["trainable_parameters"] = int(
            run["training"]["parameters"]["trainable_parameters"]
        )
        records.append(record)
    records.sort(key=lambda row: (VALIDATION_VARIANTS.index(row["variant"]), row["seed"]))
    return records
