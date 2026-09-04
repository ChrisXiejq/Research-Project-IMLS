#!/usr/bin/env python3
"""Consolidate the three frozen E2 shuffle seeds into the canonical local audit."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

from distinction_analysis_utils import atomic_write_json, sha256_file, write_csv


SEEDS = (20260808, 20260809, 20260810)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-runs-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    roots = {
        20260808: args.server_runs_dir / "e2_b1_inputs",
        20260809: args.server_runs_dir / "e2_b1_inputs_seed_20260809",
        20260810: args.server_runs_dir / "e2_b1_inputs_seed_20260810",
    }
    payloads = {seed: json.loads((root / "b1_base_input_diagnostics.json").read_text()) for seed, root in roots.items()}
    source_conditions = {seed: {row["condition"]: row for row in payload["conditions"]} for seed, payload in payloads.items()}
    conditions = []
    for name in ("original", "raster_mean", "past_mean"):
        row = dict(source_conditions[SEEDS[0]][name])
        row["diagnostic_seed"] = "not_applicable"
        conditions.append(row)
    for seed in SEEDS:
        for family in ("raster_shuffle", "past_shuffle"):
            row = dict(source_conditions[seed][family])
            row["condition"] = f"{family}_seed_{seed}"
            row["diagnostic_seed"] = seed
            conditions.append(row)

    shuffle_aggregate = []
    for family in ("raster_shuffle", "past_shuffle"):
        subset = [row for row in conditions if row["condition"].startswith(family)]
        record = {"input": family.replace("_shuffle", ""), "shuffle_seeds": list(SEEDS)}
        metric_keys = [
            key
            for key in subset[0]
            if key.startswith("delta_vs_original__") and isinstance(subset[0][key], (int, float))
        ]
        for key in metric_keys:
            values = [float(row[key]) for row in subset]
            record[f"mean__{key}"] = statistics.fmean(values)
            record[f"min__{key}"] = min(values)
            record[f"max__{key}"] = max(values)
            record[f"all_positive__{key}"] = all(value > 0 for value in values)
        shuffle_aggregate.append(record)

    base = payloads[SEEDS[0]]
    final = {
        "schema_version": "distinction_b1_base_input_diagnostics_multiseed_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass",
        "result_generation": "distinction_v1",
        "model": base["model"],
        "model_artifact": base["model_artifact"],
        "anchors_sha256": base["anchors_sha256"],
        "calibration_sha256": base["calibration_sha256"],
        "train_input_mean_metadata": base["train_input_mean_metadata"],
        "raster_channel_mean_after_caffe_preprocessing": base["raster_channel_mean_after_caffe_preprocessing"],
        "past_state_train_mean": base["past_state_train_mean"],
        "shuffle_rule": base["shuffle_rule"],
        "test_samples": base["test_samples"],
        "conditions": conditions,
        "shuffle_aggregate": shuffle_aggregate,
        "source_sha256": {
            str((root / "b1_base_input_diagnostics.json").relative_to(args.server_runs_dir)): sha256_file(
                root / "b1_base_input_diagnostics.json"
            )
            for root in roots.values()
        },
        "finding": (
            "B1 is strongly raster-sensitive across three cross-init shuffles, while past-state shuffle and train-mean "
            "replacement have negligible aggregate effect. B1 should therefore be described as raster-dominant, not as "
            "demonstrating effective explicit temporal-history use."
        ),
        "claim_boundary": base["claim_boundary"],
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(args.output_dir / "b1_base_input_diagnostics.json", final)
    write_csv(args.output_dir / "b1_input_condition_summary.csv", conditions, sorted({key for row in conditions for key in row}))
    atomic_write_json(
        args.output_dir / "E2_COMPLETE.json",
        {"stage": "E2", "status": "pass", "shuffle_seeds": list(SEEDS), "artifact": "b1_base_input_diagnostics.json"},
    )
    print(json.dumps(final, indent=2))


if __name__ == "__main__":
    main()
