#!/usr/bin/env python3
"""Compare original and collision-rollout-filtered Day 8 validation matrices."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import statistics
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def primary(run: dict[str, Any]) -> float:
    return float(run["subsets"]["all"]["uncalibrated_rollout_macro_trajectory_NLL_per_step"])


def reactive_ade(run: dict[str, Any]) -> float:
    return float(run["subsets"]["reactive"]["top1_ADE_mean"])


def analyze(
    original_path: Path,
    filtered_path: Path,
    filter_audit_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    original = read_json(original_path)
    filtered = read_json(filtered_path)
    filter_audit = read_json(filter_audit_path)
    for name, summary in (("original", original), ("filtered", filtered)):
        if summary.get("status") != "pass" or summary.get("test_accessed") is not False:
            raise ValueError(f"{name} validation summary violates the validation-only gate")
        if int(summary.get("observed_runs", -1)) != 15:
            raise ValueError(f"{name} validation summary is not a complete 15-run matrix")
    if filter_audit.get("status") != "pass" or filter_audit.get("test_accessed_for_selection") is not False:
        raise ValueError("Filtered dataset audit violates its no-test gate")

    original_runs = {(run["variant"], int(run["seed"])): run for run in original["runs"]}
    filtered_runs = {(run["variant"], int(run["seed"])): run for run in filtered["runs"]}
    if set(original_runs) != set(filtered_runs):
        raise ValueError("Original and filtered validation matrices are not matched")

    run_rows = []
    for variant, seed in sorted(original_runs):
        before = original_runs[(variant, seed)]
        after = filtered_runs[(variant, seed)]
        run_rows.append(
            {
                "variant": variant,
                "seed": seed,
                "original_validation_macro_nll": primary(before),
                "filtered_validation_macro_nll": primary(after),
                "delta_validation_macro_nll": primary(after) - primary(before),
                "original_reactive_top1_ade_m": reactive_ade(before),
                "filtered_reactive_top1_ade_m": reactive_ade(after),
                "delta_reactive_top1_ade_m": reactive_ade(after) - reactive_ade(before),
            }
        )

    original_rank = {item["variant"]: index + 1 for index, item in enumerate(original["variant_ranking"])}
    filtered_rank = {item["variant"]: index + 1 for index, item in enumerate(filtered["variant_ranking"])}
    variant_rows = []
    for variant in sorted(original_rank):
        rows = [row for row in run_rows if row["variant"] == variant]
        before_item = next(item for item in original["variant_ranking"] if item["variant"] == variant)
        after_item = next(item for item in filtered["variant_ranking"] if item["variant"] == variant)
        variant_rows.append(
            {
                "variant": variant,
                "original_rank": original_rank[variant],
                "filtered_rank": filtered_rank[variant],
                "original_median_validation_macro_nll": float(before_item["median_validation_rollout_macro_NLL"]),
                "filtered_median_validation_macro_nll": float(after_item["median_validation_rollout_macro_NLL"]),
                "median_paired_delta_validation_macro_nll": statistics.median(
                    row["delta_validation_macro_nll"] for row in rows
                ),
                "median_paired_delta_reactive_top1_ade_m": statistics.median(
                    row["delta_reactive_top1_ade_m"] for row in rows
                ),
                "original_representative_seed": int(before_item["representative_seed"]),
                "filtered_representative_seed": int(after_item["representative_seed"]),
            }
        )

    original_selected = str(original["provisional_selected_variant"])
    filtered_selected = str(filtered["provisional_selected_variant"])
    architecture_stable = original_selected == filtered_selected
    result = {
        "schema_version": "day13_collision_filtered_validation_sensitivity_v1",
        "status": "pass",
        "analysis_role": "post-hoc training-data sensitivity; original frozen Day8 remains primary",
        "test_accessed": False,
        "matched_runs": len(run_rows),
        "original_selected_variant": original_selected,
        "filtered_selected_variant": filtered_selected,
        "selected_architecture_stable": architecture_stable,
        "sensitivity_conclusion": (
            "original_validation_architecture_conclusion_robust_to_conservative_rollout_filter"
            if architecture_stable
            else "original_validation_architecture_conclusion_sensitive_to_conservative_rollout_filter"
        ),
        "decision_rule": "robust iff the validation-only selected architecture is unchanged; test remains untouched",
        "filter_counts": filter_audit["counts"],
        "variant_comparison": variant_rows,
        "source": {
            "original_validation_summary_sha256": sha256(original_path),
            "filtered_validation_summary_sha256": sha256(filtered_path),
            "filter_audit_sha256": sha256(filter_audit_path),
        },
        "limitations": [
            "The filter removes whole callback-containing rollouts because Day6 lacks the per-rollout CARLA frame anchor needed for exact window attribution.",
            "This is a conservative sensitivity analysis, not a replacement for the preregistered original model-selection experiment.",
            "Validation is reused for sensitivity comparison; the test split is not accessed or used to select a filtered model.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, rows in (
        (output_dir / "day13_filtered_run_deltas.csv", run_rows),
        (output_dir / "day13_filtered_variant_comparison.csv", variant_rows),
    ):
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    summary_path = output_dir / "day13_filtered_sensitivity_summary.json"
    atomic_json(summary_path, result)
    atomic_json(
        output_dir / "DAY13_FILTERED_SENSITIVITY_COMPLETE.json",
        {
            "schema_version": "day13_filtered_sensitivity_complete_v1",
            "status": "pass",
            "selected_architecture_stable": architecture_stable,
            "summary_sha256": sha256(summary_path),
            "test_accessed": False,
        },
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original-summary", required=True, type=Path)
    parser.add_argument("--filtered-summary", required=True, type=Path)
    parser.add_argument("--filter-audit", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = analyze(
        args.original_summary.resolve(),
        args.filtered_summary.resolve(),
        args.filter_audit.resolve(),
        args.output_dir.resolve(),
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
