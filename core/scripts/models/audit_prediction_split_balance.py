#!/usr/bin/env python3
"""E6: audit split disjointness and covariate balance from the frozen Day 6 bundle."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from distinction_analysis_utils import atomic_write_json, sha256_file, write_csv


def split_for_init(init_id: int) -> str:
    return "train" if init_id <= 40 else "val" if init_id <= 45 else "test"


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def sample_covariates(sample: dict) -> dict:
    ego = sample.get("ego_state") or {}
    target = sample.get("target_state") or {}
    ex, ey = safe_float(ego.get("x")), safe_float(ego.get("y_rhs"))
    tx, ty = safe_float(target.get("x")), safe_float(target.get("y_rhs"))
    diagnostics = sample.get("target_reactive_diagnostics") or {}
    valid_steps = sum(bool(value) for value in sample.get("future_valid_mask", [])[:10])
    return {
        "ego_speed_mps": safe_float(ego.get("speed")),
        "target_speed_mps": safe_float(target.get("speed", sample.get("target_actual_speed_mps"))),
        "ego_target_distance_m": math.hypot(ex - tx, ey - ty),
        "future_valid_steps": float(valid_steps),
        "response_active": float(bool(diagnostics.get("active", 0))),
        "target_start_offset_m": safe_float(sample.get("target_start_offset_m")),
    }


def standardized_mean_difference(reference: list[float], comparison: list[float]) -> float | None:
    if not reference or not comparison:
        return None
    ref = np.asarray(reference, dtype=np.float64)
    cmp = np.asarray(comparison, dtype=np.float64)
    pooled = math.sqrt((float(np.var(ref, ddof=1)) + float(np.var(cmp, ddof=1))) / 2.0)
    if pooled < 1e-12:
        return 0.0 if abs(float(ref.mean() - cmp.mean())) < 1e-12 else None
    return float((cmp.mean() - ref.mean()) / pooled)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-tar", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    keys = set()
    duplicates = []
    rollout_inits: dict[str, int] = {}
    with tarfile.open(args.dataset_tar, "r:gz") as archive:
        members = sorted(
            (member for member in archive if member.isfile() and member.name.endswith("prediction_dataset_labeled.jsonl")),
            key=lambda member: member.name,
        )
        for member in members:
            handle = archive.extractfile(member)
            assert handle is not None
            for raw in handle:
                sample = json.loads(raw)
                init_id = int(sample["ego_init_id"])
                split = split_for_init(init_id)
                rollout = f'{sample["cell_id"]}/{sample["source_subrun"]}'
                key = (rollout, int(sample["sample_id"]), int(sample["target_vehicle_idx"]))
                if key in keys:
                    duplicates.append(key)
                keys.add(key)
                rollout_inits[rollout] = init_id
                row = {
                    "split": split,
                    "ego_init_id": init_id,
                    "rollout": rollout,
                    "cell_id": sample["cell_id"],
                    "target_style": sample["target_style"],
                    "ego_policy": sample["ego_policy"],
                    "full_horizon": int(sum(bool(x) for x in sample.get("future_valid_mask", [])[:10]) == 10),
                    **sample_covariates(sample),
                }
                rows.append(row)

    counts = {}
    for split in ("train", "val", "test"):
        subset = [row for row in rows if row["split"] == split]
        split_rollouts = {row["rollout"] for row in subset}
        counts[split] = {
            "raw_samples": len(subset),
            "full_horizon_samples": sum(row["full_horizon"] for row in subset),
            "rollouts": len(split_rollouts),
            "init_ids": sorted({row["ego_init_id"] for row in subset}),
            "cells": dict(sorted(Counter(row["cell_id"] for row in subset).items())),
            "styles": dict(sorted(Counter(row["target_style"] for row in subset).items())),
        }

    covariate_names = (
        "ego_speed_mps",
        "target_speed_mps",
        "ego_target_distance_m",
        "future_valid_steps",
        "response_active",
        "target_start_offset_m",
    )
    covariate_summary = []
    for covariate in covariate_names:
        values = {split: [row[covariate] for row in rows if row["split"] == split] for split in ("train", "val", "test")}
        record = {"covariate": covariate}
        for split, split_values in values.items():
            array = np.asarray(split_values, dtype=np.float64)
            record[f"{split}_mean"] = float(array.mean())
            record[f"{split}_std"] = float(array.std(ddof=1))
        record["val_minus_train_SMD"] = standardized_mean_difference(values["train"], values["val"])
        record["test_minus_train_SMD"] = standardized_mean_difference(values["train"], values["test"])
        covariate_summary.append(record)

    init_sets = {split: set(counts[split]["init_ids"]) for split in counts}
    disjoint = not (
        init_sets["train"] & init_sets["val"]
        or init_sets["train"] & init_sets["test"]
        or init_sets["val"] & init_sets["test"]
    )
    max_abs_smd = max(
        abs(value)
        for row in covariate_summary
        for value in (row["val_minus_train_SMD"], row["test_minus_train_SMD"])
        if value is not None
    )
    balance_flag = "acceptable_descriptive_balance" if max_abs_smd < 0.5 else "material_covariate_shift_present"

    write_csv(args.output_dir / "split_window_covariates.csv", rows, list(rows[0]))
    write_csv(args.output_dir / "split_covariate_balance.csv", covariate_summary, list(covariate_summary[0]))
    payload = {
        "schema_version": "distinction_split_balance_audit_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass" if disjoint and not duplicates and len(rollout_inits) == 200 else "fail",
        "result_generation": "distinction_v1",
        "dataset_sha256": sha256_file(args.dataset_tar),
        "counts": counts,
        "checks": {
            "rollout_count_is_200": len(rollout_inits) == 200,
            "init_groups_disjoint": disjoint,
            "duplicate_sample_keys": len(duplicates),
            "each_init_has_four_cells": all(
                len({row["cell_id"] for row in rows if row["ego_init_id"] == init_id}) == 4
                for init_id in range(1, 51)
            ),
        },
        "covariate_balance": covariate_summary,
        "maximum_absolute_window_level_SMD": max_abs_smd,
        "balance_interpretation": balance_flag,
        "boundary": (
            "SMDs are descriptive window-level diagnostics. The split is deliberately by ego initialization, "
            "so identical distributions are not expected and no independence is claimed between adjacent windows."
        ),
    }
    atomic_write_json(args.output_dir / "split_balance_audit.json", payload)
    atomic_write_json(
        args.output_dir / "E6_COMPLETE.json",
        {"stage": "E6", "status": payload["status"], "balance_interpretation": balance_flag, "artifact": "split_balance_audit.json"},
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
