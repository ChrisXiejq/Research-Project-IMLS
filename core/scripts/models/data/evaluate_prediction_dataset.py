#!/usr/bin/env python3

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
"""Evaluate logged MultiPath predictions on a fixed CARLA dataset split."""

import argparse
import json
import math
import os
from typing import Dict, List

import numpy as np

from prediction_dataset_utils import finite_or_none, mean, percentile, read_jsonl, valid_future_indices


CHI2_2D_1SIGMA = 2.30
CHI2_2D_2SIGMA = 6.18
CHI2_2D_3SIGMA = 11.83


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged_dir", required=True, help="Directory containing train/val/test/all JSONL files.")
    parser.add_argument("--split", default="all", choices=["all", "train", "val", "test"])
    parser.add_argument("--output_json", default=None)
    return parser.parse_args()


def evaluate_split(jsonl_path: str, horizon: int = 10) -> Dict:
    total = 0
    valid_samples = 0
    full_horizon = 0
    valid_points = 0
    missing_raster = 0

    top1_ade = []
    min_ade = []
    top1_fde = []
    min_fde = []
    top_probs = []
    best_probs = []
    entropies = []
    nlls = []
    per_step_top1_errors = [[] for _ in range(horizon)]
    mode_best_counts = None
    top_is_best = 0
    cover1 = 0
    cover2 = 0
    cover3 = 0
    cov_points = 0
    det_bad = 0

    for sample in read_jsonl(jsonl_path):
        total += 1
        raster = sample.get("raster_abspath")
        if raster and not os.path.exists(raster):
            missing_raster += 1

        valid_idx = valid_future_indices(sample, horizon=horizon)
        if not valid_idx:
            continue
        valid_samples += 1
        valid_points += len(valid_idx)
        if len(valid_idx) == horizon:
            full_horizon += 1

        future = np.asarray(sample["future_xy_world"], dtype=np.float32)
        pred_mus = np.asarray(sample["pred_mus_world"], dtype=np.float32)
        pred_sigmas = np.asarray(sample["pred_sigmas_world"], dtype=np.float32)
        probs = np.asarray(sample["mode_probabilities"], dtype=np.float32)
        if mode_best_counts is None:
            mode_best_counts = [0 for _ in range(len(pred_mus))]

        mode_ade = []
        mode_fde = []
        for mode_idx, mode in enumerate(pred_mus):
            errors = []
            for t in valid_idx:
                error = float(np.linalg.norm(mode[t] - future[t]))
                errors.append(error)
                if mode_idx == 0:
                    per_step_top1_errors[t].append(error)
            mode_ade.append(float(np.mean(errors)))
            mode_fde.append(float(errors[-1]))

        best_idx = int(np.argmin(mode_ade))
        top_idx = int(np.argmax(probs))
        mode_best_counts[best_idx] += 1
        top_is_best += int(best_idx == top_idx)
        top_probs.append(float(probs[top_idx]))
        best_probs.append(float(probs[best_idx]))
        entropies.append(float(-np.sum(probs * np.log(np.maximum(probs, 1.0e-12)))))
        top1_ade.append(mode_ade[top_idx])
        min_ade.append(mode_ade[best_idx])
        top1_fde.append(mode_fde[top_idx])
        min_fde.append(mode_fde[best_idx])

        sample_nll = []
        for t in valid_idx:
            log_components = []
            for mode_idx, mode in enumerate(pred_mus):
                residual = future[t] - mode[t]
                cov = pred_sigmas[mode_idx, t]
                det = float(np.linalg.det(cov))
                if det <= 1.0e-9 or not np.isfinite(det):
                    det_bad += 1
                    continue
                inv_cov = np.linalg.inv(cov)
                maha = float(residual.T @ inv_cov @ residual)
                if mode_idx == top_idx:
                    cov_points += 1
                    cover1 += int(maha <= CHI2_2D_1SIGMA)
                    cover2 += int(maha <= CHI2_2D_2SIGMA)
                    cover3 += int(maha <= CHI2_2D_3SIGMA)
                log_components.append(
                    float(np.log(max(float(probs[mode_idx]), 1.0e-12))
                          - math.log(2.0 * math.pi)
                          - 0.5 * math.log(det)
                          - 0.5 * maha)
                )
            if log_components:
                max_log = max(log_components)
                sample_nll.append(-(max_log + math.log(sum(math.exp(v - max_log) for v in log_components))))
        if sample_nll:
            nlls.append(float(np.mean(sample_nll)))

    return {
        "jsonl_path": os.path.abspath(jsonl_path),
        "total_samples": total,
        "valid_labeled_samples": valid_samples,
        "full_horizon_samples": full_horizon,
        "valid_future_points": valid_points,
        "missing_rasters": missing_raster,
        "top1_ADE_mean": finite_or_none(mean(top1_ade)),
        "minADE_mean": finite_or_none(mean(min_ade)),
        "top1_FDE_mean": finite_or_none(mean(top1_fde)),
        "minFDE_mean": finite_or_none(mean(min_fde)),
        "minADE_p50": finite_or_none(percentile(min_ade, 50)),
        "minADE_p90": finite_or_none(percentile(min_ade, 90)),
        "minADE_max": finite_or_none(max(min_ade) if min_ade else float("nan")),
        "minFDE_p50": finite_or_none(percentile(min_fde, 50)),
        "minFDE_p90": finite_or_none(percentile(min_fde, 90)),
        "minFDE_max": finite_or_none(max(min_fde) if min_fde else float("nan")),
        "top_prob_mode_is_best_frac": finite_or_none(top_is_best / valid_samples if valid_samples else float("nan")),
        "mean_probability_assigned_to_best_mode": finite_or_none(mean(best_probs)),
        "mean_top_mode_probability": finite_or_none(mean(top_probs)),
        "mean_mode_entropy": finite_or_none(mean(entropies)),
        "best_mode_counts": mode_best_counts or [],
        "mixture_NLL_mean": finite_or_none(mean(nlls)),
        "mixture_NLL_p50": finite_or_none(percentile(nlls, 50)),
        "mixture_NLL_p90": finite_or_none(percentile(nlls, 90)),
        "top_mode_cov_coverage_1sigma": finite_or_none(cover1 / cov_points if cov_points else float("nan")),
        "top_mode_cov_coverage_2sigma": finite_or_none(cover2 / cov_points if cov_points else float("nan")),
        "top_mode_cov_coverage_3sigma": finite_or_none(cover3 / cov_points if cov_points else float("nan")),
        "covariance_det_bad": det_bad,
        "per_step_top1_error_mean": [finite_or_none(mean(values)) for values in per_step_top1_errors],
    }


def main():
    args = parse_args()
    jsonl_path = os.path.join(os.path.abspath(args.merged_dir), f"{args.split}.jsonl")
    if not os.path.exists(jsonl_path):
        raise FileNotFoundError(jsonl_path)

    metrics = evaluate_split(jsonl_path)
    metrics["split"] = args.split
    output_json = args.output_json or os.path.join(os.path.abspath(args.merged_dir), f"baseline_metrics_{args.split}.json")
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
