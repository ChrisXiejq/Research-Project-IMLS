#!/usr/bin/env python3
"""E4: recompute prediction quality from the exact Day 10/11 in-loop windows."""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
import tarfile
from collections import defaultdict
from pathlib import Path

import numpy as np

from distinction_analysis_utils import atomic_write_json, sha256_file, write_csv


HORIZON = 10
CHI2_THRESHOLDS = {"coverage50": 1.38629436112, "coverage90": 4.60517018599, "coverage95": 5.99146454711}
TARGET_COVERAGE = {"coverage50": 0.50, "coverage90": 0.90, "coverage95": 0.95}


def softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp = np.exp(shifted)
    return exp / exp.sum()


def logsumexp(values: np.ndarray) -> float:
    maximum = float(np.max(values))
    return maximum + math.log(float(np.exp(values - maximum).sum()))


def full_horizon(sample: dict) -> bool:
    mask = sample.get("future_valid_mask", [])[:HORIZON]
    future = sample.get("future_xy_world", [])[:HORIZON]
    return len(mask) == HORIZON and len(future) == HORIZON and all(mask)


def trajectory_nll(truth: np.ndarray, means: np.ndarray, covariances: np.ndarray, probabilities: np.ndarray) -> float:
    mode_log_likelihoods = []
    for mode_index in range(len(probabilities)):
        total = math.log(max(float(probabilities[mode_index]), 1e-12))
        for step in range(HORIZON):
            covariance = 0.5 * (covariances[mode_index, step] + covariances[mode_index, step].T)
            covariance = covariance + np.eye(2) * 1e-9
            sign, logdet = np.linalg.slogdet(covariance)
            if sign <= 0:
                raise ValueError("Non-positive-definite covariance in formal prediction log")
            residual = truth[step] - means[mode_index, step]
            total += -0.5 * (2.0 * math.log(2.0 * math.pi) + logdet + residual @ np.linalg.inv(covariance) @ residual)
        mode_log_likelihoods.append(total)
    return -logsumexp(np.asarray(mode_log_likelihoods, dtype=np.float64)) / HORIZON


def sample_metrics(sample: dict, predictor: str, calibration: dict) -> dict:
    truth = np.asarray(sample["future_xy_world"][:HORIZON], dtype=np.float64)
    means = np.asarray(sample["pred_mus_world"], dtype=np.float64)[:, :HORIZON]
    calibrated_covariances = np.asarray(sample["pred_sigmas_world"], dtype=np.float64)[:, :HORIZON]
    calibrated_probabilities = np.asarray(sample["mode_probabilities"], dtype=np.float64)
    calibrated_probabilities /= calibrated_probabilities.sum()
    if predictor == "B1":
        temperature = float(calibration["temperature"])
        covariance_scale = float(calibration["covariance_scale"])
        uncalibrated_probabilities = softmax(temperature * np.log(np.maximum(calibrated_probabilities, 1e-12)))
        uncalibrated_covariances = calibrated_covariances / covariance_scale
    else:
        uncalibrated_probabilities = calibrated_probabilities.copy()
        uncalibrated_covariances = calibrated_covariances.copy()

    top_index = int(np.argmax(calibrated_probabilities))
    errors = np.linalg.norm(means - truth[None, :, :], axis=2)
    top_errors = errors[top_index]
    top_covariances = calibrated_covariances[top_index]
    mahalanobis = []
    for step in range(HORIZON):
        covariance = 0.5 * (top_covariances[step] + top_covariances[step].T) + np.eye(2) * 1e-9
        residual = truth[step] - means[top_index, step]
        mahalanobis.append(float(residual @ np.linalg.inv(covariance) @ residual))
    return {
        "top1_ADE_m": float(top_errors.mean()),
        "top1_FDE_m": float(top_errors[-1]),
        "minADE_m": float(errors.mean(axis=1).min()),
        "calibrated_trajectory_NLL_per_step": trajectory_nll(
            truth, means, calibrated_covariances, calibrated_probabilities
        ),
        "uncalibrated_trajectory_NLL_per_step": trajectory_nll(
            truth, means, uncalibrated_covariances, uncalibrated_probabilities
        ),
        **{
            name: float(np.mean(np.asarray(mahalanobis) <= threshold))
            for name, threshold in CHI2_THRESHOLDS.items()
        },
    }


def load_calibration(model_tar: Path) -> dict:
    with tarfile.open(model_tar, "r:gz") as archive:
        handle = archive.extractfile("models/B1/seed_37/calibration.json")
        assert handle is not None
        return json.load(io.TextIOWrapper(handle, encoding="utf-8"))["parameters"]


def load_formal(archive_path: Path, contract_name: str, source_stage: str, calibration: dict) -> tuple[list[dict], dict]:
    rows = []
    with tarfile.open(archive_path, "r:gz") as archive:
        contract_handle = archive.extractfile(contract_name)
        assert contract_handle is not None
        contract = json.load(io.TextIOWrapper(contract_handle, encoding="utf-8"))
        cell_contracts = {cell["cell_id"]: cell for cell in contract["cells"]}
        members = [
            member
            for member in archive
            if member.isfile()
            and member.name.endswith("prediction_dataset_labeled.jsonl")
            and member.name.split("/", 1)[0] in cell_contracts
        ]
        for member in sorted(members, key=lambda item: item.name):
            cell_id = member.name.split("/", 1)[0]
            cell = cell_contracts[cell_id]
            handle = archive.extractfile(member)
            assert handle is not None
            rollout = member.name.split("/prediction_dataset/", 1)[0]
            for raw in handle:
                sample = json.loads(raw)
                if not full_horizon(sample):
                    continue
                diagnostics = sample.get("target_reactive_diagnostics") or {}
                row = {
                    "source_stage": source_stage,
                    "predictor": cell["predictor"],
                    "risk_policy": cell["risk_policy"],
                    "target_style": cell["target_style"],
                    "target_offset_m": float(cell.get("target_offset_m", contract.get("target_offset_m", 0.0))),
                    "ego_init_id": int(sample["ego_init_id"]),
                    "cell_id": cell_id,
                    "rollout": rollout,
                    "sample_id": int(sample["sample_id"]),
                    "response_active": int(bool(diagnostics.get("active", 0))),
                    **sample_metrics(sample, cell["predictor"], calibration),
                }
                rows.append(row)
    return rows, contract


METRICS = (
    "top1_ADE_m",
    "top1_FDE_m",
    "minADE_m",
    "calibrated_trajectory_NLL_per_step",
    "uncalibrated_trajectory_NLL_per_step",
)


def summarize(rows: list[dict], group_fields: tuple[str, ...]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in group_fields)].append(row)
    output = []
    for key, subset in sorted(groups.items(), key=lambda item: str(item[0])):
        rollouts = defaultdict(list)
        for row in subset:
            rollouts[row["rollout"]].append(row)
        record = {field: value for field, value in zip(group_fields, key)}
        record.update(
            {
                "samples": len(subset),
                "rollouts": len(rollouts),
                "independent_init_groups": len({row["ego_init_id"] for row in subset}),
            }
        )
        for metric in METRICS:
            record[f"sample_micro_{metric}"] = float(np.mean([row[metric] for row in subset]))
            record[f"rollout_macro_{metric}"] = float(
                np.mean([np.mean([row[metric] for row in rollout]) for rollout in rollouts.values()])
            )
        for coverage, target in TARGET_COVERAGE.items():
            observed = float(np.mean([row[coverage] for row in subset]))
            record[f"observed_{coverage}"] = observed
            record[f"absolute_error_{coverage}"] = abs(observed - target)
        record["calibrated_coverage_MAE"] = float(
            np.mean([record[f"absolute_error_{coverage}"] for coverage in TARGET_COVERAGE])
        )
        output.append(record)
    return output


def predictor_contrasts(rows: list[dict], active_only: bool) -> list[dict]:
    source = [row for row in rows if row["response_active"]] if active_only else rows
    rollout_metrics = defaultdict(lambda: defaultdict(list))
    for row in source:
        key = (row["risk_policy"], row["target_style"], row["target_offset_m"], row["ego_init_id"])
        for metric in METRICS:
            rollout_metrics[(key, row["predictor"])][metric].append(row[metric])
    paired_keys = sorted({key for key, predictor in rollout_metrics if predictor == "B1"} & {key for key, predictor in rollout_metrics if predictor == "B0"})
    output = []
    for metric in METRICS:
        deltas = []
        for key in paired_keys:
            left = np.mean(rollout_metrics[(key, "B1")][metric])
            right = np.mean(rollout_metrics[(key, "B0")][metric])
            deltas.append((key, float(left - right)))
        for offset in sorted({key[2] for key, _ in deltas}):
            subset = [(key, value) for key, value in deltas if key[2] == offset]
            if not subset:
                continue
            output.append(
                {
                    "subset": "response_active" if active_only else "all",
                    "target_offset_m": offset,
                    "metric": metric,
                    "paired_rollout_conditions": len(subset),
                    "independent_init_groups": len({key[3] for key, _ in subset}),
                    "B1_minus_B0_mean": float(np.mean([value for _, value in subset])),
                    "B1_better_fraction": float(np.mean([value < 0 for _, value in subset])),
                }
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day10-tar", type=Path, required=True)
    parser.add_argument("--day11-tar", type=Path, required=True)
    parser.add_argument("--model-tar", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    calibration = load_calibration(args.model_tar)
    day10_rows, day10_contract = load_formal(args.day10_tar, "day10_run_contract.json", "day10_offset_0", calibration)
    day11_rows, day11_contract = load_formal(
        args.day11_tar, "day11_run_contract.json", "day11_offsets_pm3", calibration
    )
    rows = day10_rows + day11_rows
    expected_rollouts = int(day10_contract["expected_rollouts"]) + int(day11_contract["expected_rollouts"])
    observed_rollouts = len({row["rollout"] for row in rows})
    if observed_rollouts != expected_rollouts:
        raise ValueError(f"Expected {expected_rollouts} formal rollouts, found {observed_rollouts}")

    all_summary = summarize(rows, ("predictor", "target_offset_m"))
    condition_summary = summarize(rows, ("predictor", "risk_policy", "target_style", "target_offset_m"))
    active_rows = [row for row in rows if row["response_active"]]
    active_summary = summarize(active_rows, ("predictor", "target_offset_m")) if active_rows else []
    contrasts = predictor_contrasts(rows, False) + predictor_contrasts(rows, True)

    write_csv(args.output_dir / "formal_inloop_sample_metrics.csv", rows, list(rows[0]))
    write_csv(args.output_dir / "formal_inloop_predictor_offset_summary.csv", all_summary, list(all_summary[0]))
    write_csv(args.output_dir / "formal_inloop_condition_summary.csv", condition_summary, list(condition_summary[0]))
    if active_summary:
        write_csv(args.output_dir / "formal_inloop_response_active_summary.csv", active_summary, list(active_summary[0]))
    write_csv(args.output_dir / "formal_inloop_B1_minus_B0_contrasts.csv", contrasts, list(contrasts[0]))

    audit = {
        "schema_version": "distinction_formal_inloop_prediction_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass",
        "result_generation": "distinction_v1",
        "source_sha256": {
            "day10": sha256_file(args.day10_tar),
            "day11": sha256_file(args.day11_tar),
            "models": sha256_file(args.model_tar),
        },
        "calibration_recovery": {
            "B1_logged_values": "calibrated probabilities and covariance matrices",
            "temperature": calibration["temperature"],
            "covariance_scale": calibration["covariance_scale"],
            "uncalibrated_probability_recovery": "softmax(temperature * log(calibrated_probability))",
            "uncalibrated_covariance_recovery": "logged_covariance / covariance_scale",
            "B0": "identity calibration",
        },
        "counts": {
            "formal_rollouts": observed_rollouts,
            "full_horizon_windows": len(rows),
            "response_active_full_horizon_windows": len(active_rows),
            "day10_windows": len(day10_rows),
            "day11_windows": len(day11_rows),
        },
        "predictor_offset_summary": all_summary,
        "response_active_summary": active_summary,
        "B1_minus_B0_contrasts": contrasts,
        "claim_boundary": (
            "These are post hoc diagnostics on logged, outcome-dependent in-loop windows. They describe deployed-stack behavior "
            "but do not replace the frozen offline test or identify a causal closed-loop predictor effect."
        ),
    }
    atomic_write_json(args.output_dir / "formal_inloop_prediction_analysis.json", audit)
    atomic_write_json(
        args.output_dir / "E4_COMPLETE.json",
        {"stage": "E4", "status": "pass", "formal_rollouts": observed_rollouts, "artifact": "formal_inloop_prediction_analysis.json"},
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
