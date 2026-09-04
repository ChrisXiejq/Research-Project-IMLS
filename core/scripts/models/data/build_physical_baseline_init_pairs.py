#!/usr/bin/env python3
"""Add the planned five-init paired direction audit to E1 using frozen B1 outputs."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import csv
import json
import statistics
from collections import defaultdict
from pathlib import Path

from distinction_analysis_utils import atomic_write_json, sha256_file, write_csv


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-sample-csv", type=Path, required=True)
    parser.add_argument("--b1-original-json", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    with args.baseline_sample_csv.open("r", encoding="utf-8", newline="") as handle:
        source = list(csv.DictReader(handle))
    grouped = defaultdict(lambda: defaultdict(list))
    for row in source:
        grouped[(row["baseline"], int(row["ego_init_id"]))]["ADE_m"].append(float(row["ADE_m"]))
        grouped[(row["baseline"], int(row["ego_init_id"]))]["FDE_m"].append(float(row["FDE_m"]))
    b1 = json.loads(args.b1_original_json.read_text(encoding="utf-8"))["all"]["uncalibrated"]["init_group_aggregation"]["per_init_group"]
    rows = []
    for baseline in sorted({key[0] for key in grouped}):
        for init_id in range(46, 51):
            base = grouped[(baseline, init_id)]
            b1_row = b1[f"ego_init_{init_id:02d}"]
            baseline_ade = statistics.fmean(base["ADE_m"])
            baseline_fde = statistics.fmean(base["FDE_m"])
            rows.append(
                {
                    "baseline": baseline,
                    "ego_init_id": init_id,
                    "B1_ADE_m": b1_row["top1_ADE_mean"],
                    "baseline_ADE_m": baseline_ade,
                    "B1_minus_baseline_ADE_m": b1_row["top1_ADE_mean"] - baseline_ade,
                    "B1_ADE_better": int(b1_row["top1_ADE_mean"] < baseline_ade),
                    "B1_FDE_m": b1_row["top1_FDE_mean"],
                    "baseline_FDE_m": baseline_fde,
                    "B1_minus_baseline_FDE_m": b1_row["top1_FDE_mean"] - baseline_fde,
                    "B1_FDE_better": int(b1_row["top1_FDE_mean"] < baseline_fde),
                }
            )
    direction = []
    for baseline in sorted({row["baseline"] for row in rows}):
        subset = [row for row in rows if row["baseline"] == baseline]
        direction.append(
            {
                "baseline": baseline,
                "independent_init_groups": 5,
                "B1_ADE_better_init_count": sum(row["B1_ADE_better"] for row in subset),
                "B1_FDE_better_init_count": sum(row["B1_FDE_better"] for row in subset),
                "mean_B1_minus_baseline_ADE_m": statistics.fmean(row["B1_minus_baseline_ADE_m"] for row in subset),
                "mean_B1_minus_baseline_FDE_m": statistics.fmean(row["B1_minus_baseline_FDE_m"] for row in subset),
            }
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "B1_vs_physical_baseline_by_init.csv", rows, list(rows[0]))
    atomic_write_json(
        args.output_dir / "physical_baseline_init_direction_audit.json",
        {
            "schema_version": "distinction_physical_baseline_init_pairs_v1",
            "status": "pass",
            "analysis_unit": "held-out ego_init_id",
            "direction_summary": direction,
            "pairs": rows,
            "source_sha256": {
                "baseline_sample_metrics": sha256_file(args.baseline_sample_csv),
                "B1_original_condition": sha256_file(args.b1_original_json),
            },
        },
    )
    atomic_write_json(
        args.output_dir / "E1_COMPLETE.json",
        {
            "stage": "E1",
            "status": "pass",
            "five_init_pairing_complete": True,
            "all_physical_baselines_B1_ADE_direction_count": {row["baseline"]: row["B1_ADE_better_init_count"] for row in direction},
            "artifacts": ["physical_baseline_analysis.json", "physical_baseline_init_direction_audit.json"],
        },
    )
    print(json.dumps(direction, indent=2))


if __name__ == "__main__":
    main()
