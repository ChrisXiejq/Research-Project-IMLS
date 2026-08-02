#!/usr/bin/env python3
"""Combine Day 10 nominal and Day 11 shifted timing results.

The synthesis uses only the fixed-medium/adaptive arms that are common to both
frozen contracts.  Effect means use all balanced conditions, while inference
is performed on five ego-init cluster means.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from analyze_day10_closed_loop import PRIMARY_METRICS, load_rollouts as load_day10, write_csv
from analyze_day11_timing_shift import (
    add_holm_adjustment,
    difference_in_differences,
    load_rollouts as load_day11,
    paired,
)


COMMON_POLICIES = ("fixed_medium", "adaptive")
OFFSETS = (-3.0, 0.0, 3.0)
OFFSET_PAIRS = ((0.0, -3.0), (3.0, 0.0), (3.0, -3.0))
COMPATIBILITY_KEYS = (
    "predictors",
    "anchors_sha256",
    "normalization",
    "init_sha256",
    "authority_regime",
    "reactive_parameters",
    "adaptive_parameters",
    "target_speed_mps",
    "ego_init_ids",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def label_offset(value: float) -> str:
    if value == 0.0:
        return "0"
    return ("p" if value > 0 else "m") + str(abs(int(value)))


def verify_compatibility(day10_root: Path, day11_root: Path, day10: dict[str, Any], day11: dict[str, Any]) -> dict[str, Any]:
    contract10 = day10["contract"]
    contract11 = day11["contract"]
    mismatches = [key for key in COMPATIBILITY_KEYS if contract10.get(key) != contract11.get(key)]
    day10_contract_sha = sha256(day10_root / "day10_run_contract.json")
    linked_sha = contract11.get("day10_contract_sha256")
    if linked_sha != day10_contract_sha:
        mismatches.append("day10_contract_sha256_link")
    if float(contract10.get("target_offset_m")) != 0.0:
        mismatches.append("day10_target_offset_m")
    if sorted(map(float, contract11.get("target_offsets_m", []))) != [-3.0, 3.0]:
        mismatches.append("day11_target_offsets_m")
    if mismatches:
        raise ValueError(f"Day10/Day11 contracts are not synthesis-compatible: {mismatches}")
    return {
        "status": "pass",
        "matching_keys": list(COMPATIBILITY_KEYS),
        "day10_contract_sha256": day10_contract_sha,
        "day11_linked_day10_contract_sha256": linked_sha,
        "batch_note": "offset=0 was executed in Day10; offsets=-3/+3 were executed in Day11",
    }


def build_rows(day10_rows: list[dict[str, Any]], day11_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in day10_rows:
        if row["risk_policy"] not in COMMON_POLICIES:
            continue
        rows.append(
            {
                **{key: row[key] for key in (
                    "predictor",
                    "risk_policy",
                    "target_style",
                    "ego_init_id",
                    *PRIMARY_METRICS,
                    "footprint_collision",
                    "yield_order_valid",
                    "reactive_active_samples",
                )},
                "target_offset_m": 0.0,
                "offset_label": "0",
                "source_batch": "day10_nominal",
                "source_cell_id": row["cell_id"],
            }
        )
    for row in day11_rows:
        rows.append(
            {
                **{key: row[key] for key in (
                    "predictor",
                    "risk_policy",
                    "target_style",
                    "ego_init_id",
                    *PRIMARY_METRICS,
                    "footprint_collision",
                    "yield_order_valid",
                    "reactive_active_samples",
                )},
                "target_offset_m": float(row["target_offset_m"]),
                "offset_label": row["offset_label"],
                "source_batch": "day11_shifted",
                "source_cell_id": row["cell_id"],
            }
        )
    expected_keys = {
        (predictor, policy, style, offset, init_id)
        for predictor in ("B1", "B0")
        for policy in COMMON_POLICIES
        for style in ("assertive", "reactive")
        for offset in OFFSETS
        for init_id in range(46, 51)
    }
    observed_keys = {
        (row["predictor"], row["risk_policy"], row["target_style"], row["target_offset_m"], row["ego_init_id"])
        for row in rows
    }
    if observed_keys != expected_keys or len(rows) != 120:
        raise ValueError(
            f"Unbalanced timing synthesis: rows={len(rows)}, missing={len(expected_keys-observed_keys)}, extra={len(observed_keys-expected_keys)}"
        )
    return sorted(
        rows,
        key=lambda row: (
            row["predictor"], row["risk_policy"], row["target_style"], row["target_offset_m"], row["ego_init_id"]
        ),
    )


def cell_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    keys = sorted({
        (row["predictor"], row["risk_policy"], row["target_style"], row["target_offset_m"])
        for row in rows
    })
    for predictor, policy, style, offset in keys:
        subset = [
            row for row in rows
            if (row["predictor"], row["risk_policy"], row["target_style"], row["target_offset_m"])
            == (predictor, policy, style, offset)
        ]
        summaries.append(
            {
                "predictor": predictor,
                "risk_policy": policy,
                "target_style": style,
                "target_offset_m": offset,
                "source_batch": subset[0]["source_batch"],
                "rollouts": len(subset),
                **{
                    f"mean_{metric}": statistics.fmean(row[metric] for row in subset)
                    for metric in PRIMARY_METRICS
                },
                "collisions": sum(row["footprint_collision"] for row in subset),
                "yield_order_failures": sum(1 - row["yield_order_valid"] for row in subset),
                "reactive_active_samples": sum(row["reactive_active_samples"] for row in subset),
            }
        )
    return summaries


def build_contrasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contrasts: list[dict[str, Any]] = []
    for policy in COMMON_POLICIES:
        contrasts += paired(
            rows,
            {"predictor": "B1", "risk_policy": policy},
            {"predictor": "B0", "risk_policy": policy},
            ("target_style", "target_offset_m", "ego_init_id"),
            f"B1_minus_B0__{policy}__all_offsets",
            "synthesis_predictor_pooled_primary",
        )
        for offset in OFFSETS:
            contrasts += paired(
                rows,
                {"predictor": "B1", "risk_policy": policy, "target_offset_m": offset},
                {"predictor": "B0", "risk_policy": policy, "target_offset_m": offset},
                ("target_style", "ego_init_id"),
                f"B1_minus_B0__{policy}__offset_{label_offset(offset)}",
                "synthesis_predictor_by_offset_primary",
            )
    for predictor in ("B1", "B0"):
        contrasts += paired(
            rows,
            {"predictor": predictor, "risk_policy": "adaptive"},
            {"predictor": predictor, "risk_policy": "fixed_medium"},
            ("target_style", "target_offset_m", "ego_init_id"),
            f"adaptive_minus_fixed_medium__{predictor}__all_offsets",
            "synthesis_policy_pooled_primary",
        )
        for offset in OFFSETS:
            contrasts += paired(
                rows,
                {"predictor": predictor, "risk_policy": "adaptive", "target_offset_m": offset},
                {"predictor": predictor, "risk_policy": "fixed_medium", "target_offset_m": offset},
                ("target_style", "ego_init_id"),
                f"adaptive_minus_fixed_medium__{predictor}__offset_{label_offset(offset)}",
                "synthesis_policy_by_offset_primary",
            )
    for predictor in ("B1", "B0"):
        for policy in COMMON_POLICIES:
            for left_offset, right_offset in OFFSET_PAIRS:
                contrasts += paired(
                    rows,
                    {"predictor": predictor, "risk_policy": policy, "target_offset_m": left_offset},
                    {"predictor": predictor, "risk_policy": policy, "target_offset_m": right_offset},
                    ("target_style", "ego_init_id"),
                    f"offset_{label_offset(left_offset)}_minus_{label_offset(right_offset)}__{predictor}__{policy}",
                    "synthesis_offset_primary",
                )
    for policy in COMMON_POLICIES:
        for left_offset, right_offset in OFFSET_PAIRS:
            contrasts += difference_in_differences(
                rows,
                {"predictor": "B1", "risk_policy": policy, "target_offset_m": left_offset},
                {"predictor": "B1", "risk_policy": policy, "target_offset_m": right_offset},
                {"predictor": "B0", "risk_policy": policy, "target_offset_m": left_offset},
                {"predictor": "B0", "risk_policy": policy, "target_offset_m": right_offset},
                ("target_style", "ego_init_id"),
                f"predictor_x_offset_{label_offset(left_offset)}_vs_{label_offset(right_offset)}__{policy}",
                "synthesis_predictor_x_offset_primary",
            )
    for predictor in ("B1", "B0"):
        for left_offset, right_offset in OFFSET_PAIRS:
            contrasts += difference_in_differences(
                rows,
                {"predictor": predictor, "risk_policy": "adaptive", "target_offset_m": left_offset},
                {"predictor": predictor, "risk_policy": "adaptive", "target_offset_m": right_offset},
                {"predictor": predictor, "risk_policy": "fixed_medium", "target_offset_m": left_offset},
                {"predictor": predictor, "risk_policy": "fixed_medium", "target_offset_m": right_offset},
                ("target_style", "ego_init_id"),
                f"policy_x_offset_{label_offset(left_offset)}_vs_{label_offset(right_offset)}__{predictor}",
                "synthesis_policy_x_offset_primary",
            )
    add_holm_adjustment(contrasts)
    return contrasts


def analyze(day10_root: Path, day11_root: Path, output_dir: Path) -> dict[str, Any]:
    rows10, sources10 = load_day10(day10_root)
    rows11, sources11 = load_day11(day11_root)
    compatibility = verify_compatibility(day10_root, day11_root, sources10, sources11)
    rows = build_rows(rows10, rows11)
    summaries = cell_summaries(rows)
    contrasts = build_contrasts(rows)
    payload = {
        "schema_version": "day12_three_level_timing_synthesis_v1",
        "status": "pass",
        "analysis_unit": "balanced rollout-condition effects aggregated within five independent ego-init groups before inference",
        "offsets_m": list(OFFSETS),
        "rollouts": len(rows),
        "cells": len(summaries),
        "contrasts": len(contrasts),
        "primary_metrics": list(PRIMARY_METRICS),
        "compatibility": compatibility,
        "multiplicity_control": "Holm family-wise adjustment within each declared inference scope",
        "safety_gate": {
            "collisions": sum(row["footprint_collision"] for row in rows),
            "yield_order_failures": sum(1 - row["yield_order_valid"] for row in rows),
        },
        "statistical_notes": [
            "Effect means use all balanced conditions at offsets -3, 0, and +3 m.",
            "Inference uses five ego-init cluster means; Day10 and Day11 do not create ten independent init groups.",
            "The minimum attainable two-sided exact p-value is 0.0625 before multiplicity correction.",
            "Offset=0 and shifted offsets were executed in separate frozen batches, so a residual batch effect cannot be fully excluded.",
        ],
        "source": {
            "day10_complete_sha256": sha256(day10_root / "DAY10_COMPLETE.json"),
            "day11_complete_sha256": sha256(day11_root / "DAY11_COMPLETE.json"),
            "day10_contract_sha256": sha256(day10_root / "day10_run_contract.json"),
            "day11_contract_sha256": sha256(day11_root / "day11_run_contract.json"),
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "day12_timing_rollout_metrics.csv", rows)
    write_csv(output_dir / "day12_timing_cell_summary.csv", summaries)
    write_csv(output_dir / "day12_timing_paired_contrasts.csv", contrasts)
    summary_path = output_dir / "day12_timing_synthesis_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    complete = {
        "schema_version": "day12_timing_synthesis_complete_v1",
        "status": "pass",
        "rollouts": len(rows),
        "cells": len(summaries),
        "summary_sha256": sha256(summary_path),
    }
    (output_dir / "DAY12_TIMING_SYNTHESIS_COMPLETE.json").write_text(
        json.dumps(complete, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day10-results", required=True, type=Path)
    parser.add_argument("--day11-results", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    payload = analyze(
        args.day10_results.resolve(), args.day11_results.resolve(), args.output_dir.resolve()
    )
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
