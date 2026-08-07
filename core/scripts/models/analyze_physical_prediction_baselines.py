#!/usr/bin/env python3
"""E1: evaluate leakage-safe physical baselines on the frozen V2 split."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import tarfile
from collections import defaultdict
from pathlib import Path

import numpy as np

from distinction_analysis_utils import atomic_write_json, sha256_file, write_csv


HORIZON = 10
BASELINES = ("CV", "CA", "train_mean")


def split_for_init(init_id: int) -> str:
    if init_id <= 40:
        return "train"
    if init_id <= 45:
        return "val"
    return "test"


def world_to_local(sample: dict, points: np.ndarray) -> np.ndarray:
    rotation = np.asarray(sample["target_to_world_R"], dtype=np.float64)
    translation = np.asarray(sample["target_to_world_t"], dtype=np.float64)
    return (points - translation[None, :]) @ rotation


def valid_full_horizon(sample: dict) -> bool:
    mask = sample.get("future_valid_mask", [])[:HORIZON]
    future = sample.get("future_xy_world", [])[:HORIZON]
    return len(mask) == HORIZON and len(future) == HORIZON and all(mask) and all(
        row and row[0] is not None and row[1] is not None for row in future
    )


def predictions(sample: dict, train_mean: np.ndarray) -> dict[str, np.ndarray]:
    rotation = np.asarray(sample["target_to_world_R"], dtype=np.float64)
    history = [row for row in sample.get("interaction_history_world", []) if row.get("valid")]
    current = history[-1]["target"]
    previous = history[-2]["target"]
    velocity_world = np.asarray([current["vx_rhs"], current["vy_rhs"]], dtype=np.float64)
    previous_velocity_world = np.asarray([previous["vx_rhs"], previous["vy_rhs"]], dtype=np.float64)
    velocity_local = velocity_world @ rotation
    previous_velocity_local = previous_velocity_world @ rotation
    history_dt = float(history[-1]["time_offset_s"] - history[-2]["time_offset_s"])
    acceleration_local = np.clip((velocity_local - previous_velocity_local) / history_dt, -4.0, 4.0)
    times = np.arange(1, HORIZON + 1, dtype=np.float64) * float(sample.get("dt_s", 0.2))
    return {
        "CV": times[:, None] * velocity_local[None, :],
        "CA": times[:, None] * velocity_local[None, :] + 0.5 * times[:, None] ** 2 * acceleration_local[None, :],
        "train_mean": train_mean.copy(),
    }


def load_samples(dataset_tar: Path) -> list[dict]:
    samples = []
    with tarfile.open(dataset_tar, "r:gz") as archive:
        members = sorted(
            (member for member in archive if member.isfile() and member.name.endswith("prediction_dataset_labeled.jsonl")),
            key=lambda member: member.name,
        )
        if len(members) != 200:
            raise ValueError(f"Expected 200 rollout label files, found {len(members)}")
        for member in members:
            handle = archive.extractfile(member)
            assert handle is not None
            for raw in handle:
                sample = json.loads(raw)
                if not valid_full_horizon(sample):
                    continue
                sample["_rollout"] = f'{sample["cell_id"]}/{sample["source_subrun"]}'
                sample["_split"] = split_for_init(int(sample["ego_init_id"]))
                samples.append(sample)
    return samples


def metric_row(sample: dict, baseline: str, prediction: np.ndarray, truth: np.ndarray, variance: np.ndarray) -> dict:
    errors = np.linalg.norm(prediction - truth, axis=1)
    residual = truth - prediction
    point_nll = 0.5 * (
        np.sum(np.log(2.0 * math.pi * variance), axis=1) + np.sum(residual * residual / variance, axis=1)
    )
    diagnostics = sample.get("target_reactive_diagnostics") or {}
    return {
        "baseline": baseline,
        "split": sample["_split"],
        "rollout": sample["_rollout"],
        "ego_init_id": int(sample["ego_init_id"]),
        "cell_id": sample["cell_id"],
        "target_style": sample["target_style"],
        "response_active": int(bool(diagnostics.get("active", 0))),
        "ADE_m": float(errors.mean()),
        "FDE_m": float(errors[-1]),
        "diagonal_gaussian_NLL_nats_per_step": float(point_nll.mean()),
    }


def aggregate(rows: list[dict], group_fields: tuple[str, ...]) -> list[dict]:
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[field] for field in group_fields)].append(row)
    output = []
    for key, subset in sorted(grouped.items(), key=lambda item: str(item[0])):
        rollout_groups: dict[str, list[dict]] = defaultdict(list)
        for row in subset:
            rollout_groups[row["rollout"]].append(row)
        record = {field: value for field, value in zip(group_fields, key)}
        record.update(
            {
                "samples": len(subset),
                "rollouts": len(rollout_groups),
                "independent_init_groups": len({row["ego_init_id"] for row in subset}),
            }
        )
        for metric in ("ADE_m", "FDE_m", "diagonal_gaussian_NLL_nats_per_step"):
            record[f"sample_micro_{metric}"] = float(np.mean([row[metric] for row in subset]))
            record[f"rollout_macro_{metric}"] = float(
                np.mean([np.mean([row[metric] for row in rollout]) for rollout in rollout_groups.values()])
            )
        output.append(record)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-tar", type=Path, required=True)
    parser.add_argument("--b1-test-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    samples = load_samples(args.dataset_tar)
    train = [sample for sample in samples if sample["_split"] == "train"]
    train_truth = np.stack(
        [world_to_local(sample, np.asarray(sample["future_xy_world"][:HORIZON], dtype=np.float64)) for sample in train]
    )
    train_mean = train_truth.mean(axis=0)

    train_residuals: dict[str, list[np.ndarray]] = defaultdict(list)
    for sample, truth in zip(train, train_truth):
        for name, prediction in predictions(sample, train_mean).items():
            train_residuals[name].append(truth - prediction)
    residual_variances = {
        name: np.maximum(np.var(np.stack(values), axis=0, ddof=1), 1e-4) for name, values in train_residuals.items()
    }

    rows = []
    for sample in samples:
        if sample["_split"] != "test":
            continue
        truth = world_to_local(sample, np.asarray(sample["future_xy_world"][:HORIZON], dtype=np.float64))
        for name, prediction in predictions(sample, train_mean).items():
            rows.append(metric_row(sample, name, prediction, truth, residual_variances[name]))

    summary_all = aggregate(rows, ("baseline", "split"))
    summary_style = aggregate(rows, ("baseline", "split", "target_style"))
    active_rows = [row for row in rows if row["response_active"]]
    summary_active = aggregate(active_rows, ("baseline", "split"))

    b1_payload = json.loads(args.b1_test_summary.read_text(encoding="utf-8"))
    b1_run = next(run for run in b1_payload["runs"] if run["variant"] == "B1")
    b1_all = b1_run["subsets"]["all"]
    comparison = []
    for item in summary_all:
        comparison.append(
            {
                "baseline": item["baseline"],
                "baseline_rollout_macro_ADE_m": item["rollout_macro_ADE_m"],
                "baseline_rollout_macro_FDE_m": item["rollout_macro_FDE_m"],
                "B1_top1_ADE_mean_m": b1_all["top1_ADE_mean"],
                "B1_top1_FDE_mean_m": b1_all["top1_FDE_mean"],
                "B1_minus_baseline_ADE_m": b1_all["top1_ADE_mean"] - item["rollout_macro_ADE_m"],
                "B1_minus_baseline_FDE_m": b1_all["top1_FDE_mean"] - item["rollout_macro_FDE_m"],
            }
        )

    row_fields = list(rows[0])
    write_csv(args.output_dir / "physical_baseline_sample_metrics.csv", rows, row_fields)
    summary_fields = list(summary_all[0])
    write_csv(args.output_dir / "physical_baseline_summary.csv", summary_all, summary_fields)
    write_csv(args.output_dir / "physical_baseline_by_style.csv", summary_style, list(summary_style[0]))
    if summary_active:
        write_csv(args.output_dir / "physical_baseline_response_active.csv", summary_active, list(summary_active[0]))
    write_csv(args.output_dir / "B1_vs_physical_baselines.csv", comparison, list(comparison[0]))

    payload = {
        "schema_version": "distinction_physical_baselines_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass",
        "result_generation": "distinction_v1",
        "dataset_sha256": sha256_file(args.dataset_tar),
        "split_rule": "train init 01-40; validation 41-45; test 46-50",
        "fit_rule": "train_mean and per-horizon diagonal residual variances fitted on full-horizon train samples only",
        "baseline_definitions": {
            "CV": "current target world velocity transformed into the current target-local frame",
            "CA": "last-two-velocity finite-difference acceleration, componentwise clipped to [-4,4] m/s^2",
            "train_mean": "global mean local trajectory over full-horizon training samples",
        },
        "counts": {
            "full_horizon_all": len(samples),
            "full_horizon_train": len(train),
            "full_horizon_test": len(rows) // len(BASELINES),
            "test_metric_rows": len(rows),
            "response_active_test_metric_rows": len(active_rows),
        },
        "test_summary": summary_all,
        "B1_reference": {
            "artifact_sha256": b1_run["artifact_sha256"],
            "seed": b1_run["seed"],
            "top1_ADE_mean_m": b1_all["top1_ADE_mean"],
            "top1_FDE_mean_m": b1_all["top1_FDE_mean"],
        },
        "comparison": comparison,
        "nll_boundary": "Physical-baseline NLL uses train-fitted diagonal Gaussian residuals and is not numerically identical to MultiPath mixture NLL.",
    }
    atomic_write_json(args.output_dir / "physical_baseline_analysis.json", payload)
    atomic_write_json(
        args.output_dir / "E1_COMPLETE.json",
        {"stage": "E1", "status": "pass", "artifacts": ["physical_baseline_analysis.json", "B1_vs_physical_baselines.csv"]},
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
