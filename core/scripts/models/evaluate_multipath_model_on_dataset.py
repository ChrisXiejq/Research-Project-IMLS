#!/usr/bin/env python3
"""Deployment-equivalent MultiPath accuracy and calibration evaluator.

Calibration parameters are fitted only when ``--split val
--fit-calibration`` is used.  A fitted JSON can then be supplied to a single
test evaluation with ``--calibration-json``.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import tensorflow as tf

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)
# Import registers the V2 custom Keras layers before SavedModel restoration.
import interaction_adapter_v2  # noqa: F401,E402
from multipath_gmm_utils import (
    COVARIANCE_SCALE_SEMANTICS,
    STD_PARAMETERIZATION,
    GMMDecodeResult,
    audit_covariances,
    decode_multipath_raw,
)
from prediction_dataset_utils import (
    finite_or_none,
    has_full_horizon,
    infer_init_id,
    interaction_context_from_sample,
    mean,
    percentile,
    read_jsonl,
    resolve_raster_path,
    world_future_to_local,
)
from prediction_input_contract import load_logged_raster, preprocess_resnet_raster


CHI2_THRESHOLDS_2D = {
    "1sigma": {"mahalanobis_sq": 2.30, "nominal_coverage": 0.6827},
    "2sigma": {"mahalanobis_sq": 6.18, "nominal_coverage": 0.9545},
    "3sigma": {"mahalanobis_sq": 11.83, "nominal_coverage": 0.9973},
}


class NoUsableSubsetSamples(ValueError):
    """Raised when a requested evaluation subset has no full-horizon samples."""


def rollout_group_key(sample: Mapping[str, Any]) -> str:
    """Uniquely identify one experimental rollout, including its 2x2 cell."""

    return f"{sample.get('cell_id', '<missing-cell>')}::{sample.get('source_subrun', '<missing-subrun>')}"


def init_group_key(sample: Mapping[str, Any]) -> str:
    """Return the paired-design clustering unit shared by all four cells."""

    init_id = sample.get("ego_init_id")
    if init_id is None:
        init_id = infer_init_id(str(sample.get("source_subrun", "")))
    return f"ego_init_{int(init_id):02d}" if init_id is not None else "<missing-init>"


def aggregate_group_rows(
    rows_by_group: Mapping[str, Sequence[Mapping[str, float]]]
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    metrics_by_group: Dict[str, Dict[str, Any]] = {}
    for group_key, rows in sorted(rows_by_group.items()):
        metrics_by_group[group_key] = {
            "samples": len(rows),
            "top1_ADE_mean": finite_or_none(mean([row["top1_ADE"] for row in rows])),
            "top1_FDE_mean": finite_or_none(mean([row["top1_FDE"] for row in rows])),
            "top1_FDE_p90": finite_or_none(
                percentile([row["top1_FDE"] for row in rows], 90)
            ),
            "trajectory_mixture_NLL_per_step_mean": finite_or_none(
                mean([row["trajectory_mixture_NLL_per_step"] for row in rows])
            ),
            "pointwise_mixture_NLL_mean": finite_or_none(
                mean([row["pointwise_mixture_NLL"] for row in rows])
            ),
        }
    fields = (
        "top1_ADE_mean",
        "top1_FDE_mean",
        "top1_FDE_p90",
        "trajectory_mixture_NLL_per_step_mean",
        "pointwise_mixture_NLL_mean",
    )
    macro = {
        field: finite_or_none(
            mean([metrics[field] for metrics in metrics_by_group.values()])
        )
        for field in fields
    }
    return metrics_by_group, macro


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged_dir", required=True)
    parser.add_argument("--split", default="test", choices=["train", "val", "test", "all"])
    parser.add_argument("--model", required=True, help="SavedModel directory to evaluate.")
    parser.add_argument("--anchors", default=os.path.join(SCRIPT_DIR, "l5kit_clusters_16.npy"))
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--output_json", default=None)
    parser.add_argument("--max_samples", type=int, default=None)
    parser.add_argument("--no_image", action="store_true")
    parser.add_argument("--calibration-json", default=None)
    parser.add_argument("--fit-calibration", action="store_true")
    parser.add_argument("--calibration-output-json", default=None)
    parser.add_argument("--temperature-min", type=float, default=0.25)
    parser.add_argument("--temperature-max", type=float, default=4.0)
    parser.add_argument("--temperature-count", type=int, default=25)
    parser.add_argument("--covariance-scale-min", type=float, default=1.0e-4)
    parser.add_argument("--covariance-scale-max", type=float, default=4.0)
    parser.add_argument("--covariance-scale-count", type=int, default=49)
    parser.add_argument(
        "--subset",
        default="all",
        choices=["all", "assertive", "reactive", "pre_response", "response_active"],
        help="Optional V2 behavioural subset; split selection remains unchanged.",
    )
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_hash(path: Path) -> Dict[str, Any]:
    if path.is_file():
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256_file(path)}
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total_bytes = 0
    for item in files:
        relative = str(item.relative_to(path)).encode("utf-8")
        file_digest = sha256_file(item)
        digest.update(relative)
        digest.update(b"\0")
        digest.update(file_digest.encode("ascii"))
        total_bytes += item.stat().st_size
    return {
        "path": str(path),
        "files": len(files),
        "bytes": total_bytes,
        "sha256_tree": digest.hexdigest(),
    }


def logsumexp(values: np.ndarray, axis: int = -1) -> np.ndarray:
    maximum = np.max(values, axis=axis, keepdims=True)
    finite_maximum = np.where(np.isfinite(maximum), maximum, 0.0)
    result = finite_maximum + np.log(
        np.sum(np.exp(values - finite_maximum), axis=axis, keepdims=True)
    )
    return np.squeeze(result, axis=axis)


def log_softmax(logits: np.ndarray, temperature: float) -> np.ndarray:
    scaled = np.asarray(logits, dtype=np.float64) / float(temperature)
    return scaled - logsumexp(scaled, axis=-1)[..., None]


def decode_raw_predictions(
    raw_predictions: Any,
    anchors: Any,
    *,
    temperature: float = 1.0,
    covariance_scale: float = 1.0,
) -> GMMDecodeResult:
    """Named offline wrapper used by the equivalence test."""

    return decode_multipath_raw(
        raw_predictions,
        anchors,
        temperature=temperature,
        covariance_scale=covariance_scale,
    )


def load_samples(
    jsonl_path: str,
    result_dir: str,
    horizon: int,
    max_samples: Optional[int] = None,
    no_image: bool = False,
    subset: str = "all",
):
    count = 0
    for sample in read_jsonl(jsonl_path):
        target_style = sample.get("target_style")
        diagnostics = sample.get("target_reactive_diagnostics") or {}
        include = {
            "all": True,
            "assertive": target_style == "assertive_constant_speed",
            "reactive": target_style == "defensive_reactive",
            "pre_response": target_style == "defensive_reactive"
            and not bool(diagnostics.get("active"))
            and not bool(diagnostics.get("released_latched")),
            "response_active": target_style == "defensive_reactive"
            and bool(diagnostics.get("active")),
        }[subset]
        if not include:
            continue
        if not has_full_horizon(sample, horizon=horizon):
            continue
        raster_path = resolve_raster_path(sample, result_dir=result_dir)
        if not no_image and (not raster_path or not os.path.exists(raster_path)):
            continue
        past = np.asarray(sample["past_states_local"], dtype=np.float32)
        future_local = world_future_to_local(sample, horizon=horizon).astype(np.float32)
        yield sample, raster_path, past, future_local
        count += 1
        if max_samples is not None and count >= max_samples:
            return


def make_batch(batch, no_image: bool = False):
    images = []
    past_states = []
    interaction_contexts = []
    interaction_sequences = []
    interaction_masks = []
    labels = []
    samples = []
    for sample, raster_path, past, future_local in batch:
        if no_image:
            image = np.zeros((500, 500, 3), dtype=np.float32)
        else:
            image = load_logged_raster(raster_path)
            if tuple(image.shape[:2]) != (500, 500):
                import cv2

                image = cv2.resize(image, (500, 500), interpolation=cv2.INTER_LINEAR)
            image = preprocess_resnet_raster(image)[0]
        images.append(image)
        past_states.append(past)
        interaction_contexts.append(interaction_context_from_sample(sample))
        interaction_sequences.append(sample.get("interaction_sequence"))
        interaction_masks.append(sample.get("interaction_sequence_mask"))
        labels.append(future_local)
        samples.append(sample)
    return (
        samples,
        np.asarray(images, dtype=np.float32),
        np.asarray(past_states, dtype=np.float32),
        np.asarray(interaction_contexts, dtype=np.float32),
        np.asarray(interaction_sequences, dtype=np.float32),
        np.asarray(interaction_masks, dtype=np.float32),
        np.asarray(labels, dtype=np.float32),
    )


def run_model(
    model: tf.keras.Model,
    input_count: int,
    iterator: Iterable,
    batch_size: int,
    no_image: bool,
) -> Tuple[List[Dict[str, Any]], np.ndarray, np.ndarray, Dict[str, Any]]:
    sample_rows: List[Dict[str, Any]] = []
    raw_outputs: List[np.ndarray] = []
    labels: List[np.ndarray] = []
    prediction_seconds = 0.0
    prediction_calls = 0
    batch = []

    def consume(items) -> None:
        nonlocal prediction_seconds, prediction_calls
        (
            samples,
            images,
            past_states,
            contexts,
            sequences,
            sequence_masks,
            batch_labels,
        ) = make_batch(items, no_image=no_image)
        if input_count == 2:
            model_inputs = [images, past_states]
        elif input_count == 3:
            model_inputs = [images, past_states, contexts]
        elif input_count == 4:
            if sequences.shape[1:] != (6, 12) or sequence_masks.shape[1:] != (6,):
                raise ValueError(
                    "V2 model requires interaction_sequence [N,6,12] and mask [N,6]"
                )
            model_inputs = [images, past_states, sequences, sequence_masks]
        else:
            raise ValueError(f"Unsupported model input count: {input_count}")
        started = time.perf_counter()
        predictions = np.asarray(model.predict_on_batch(model_inputs))
        prediction_seconds += time.perf_counter() - started
        prediction_calls += 1
        sample_rows.extend(samples)
        raw_outputs.append(predictions)
        labels.append(batch_labels)

    for item in iterator:
        batch.append(item)
        if len(batch) >= batch_size:
            consume(batch)
            batch = []
    if batch:
        consume(batch)
    if not raw_outputs:
        raise NoUsableSubsetSamples(
            "No full-horizon samples with usable model inputs"
        )

    raw_array = np.concatenate(raw_outputs, axis=0)
    label_array = np.concatenate(labels, axis=0)
    return sample_rows, raw_array, label_array, {
        "prediction_calls": prediction_calls,
        "total_prediction_seconds": prediction_seconds,
        "mean_prediction_ms_per_sample": 1000.0 * prediction_seconds / len(sample_rows),
        "batch_size": batch_size,
    }


def gaussian_logpdf_and_mahalanobis(
    residual: np.ndarray, covariance: np.ndarray
) -> Tuple[float, float, float]:
    if not np.all(np.isfinite(covariance)):
        return float("-inf"), float("nan"), float("nan")
    covariance = 0.5 * (covariance + covariance.T)
    sign, log_determinant = np.linalg.slogdet(covariance)
    if sign <= 0 or not np.isfinite(log_determinant):
        return float("-inf"), float("nan"), float(log_determinant)
    try:
        solved = np.linalg.solve(covariance, residual)
    except np.linalg.LinAlgError:
        return float("-inf"), float("nan"), float(log_determinant)
    mahalanobis_sq = float(residual.T @ solved)
    logpdf = (
        -math.log(2.0 * math.pi)
        - 0.5 * float(log_determinant)
        - 0.5 * mahalanobis_sq
    )
    return logpdf, mahalanobis_sq, float(log_determinant)


def summary(values: Sequence[float]) -> Dict[str, Any]:
    return {
        "count": len(values),
        "mean": finite_or_none(mean(list(values))),
        "p50": finite_or_none(percentile(list(values), 50)),
        "p90": finite_or_none(percentile(list(values), 90)),
        "max": finite_or_none(max(values) if values else float("nan")),
    }


def evaluate_decoded(
    decoded: GMMDecodeResult,
    labels: np.ndarray,
    samples: Sequence[Mapping[str, Any]],
    horizon: int,
    *,
    temperature: float,
    covariance_scale: float,
) -> Dict[str, Any]:
    probabilities = np.asarray(decoded.probabilities)
    means_array = np.asarray(decoded.means)[:, :, :horizon]
    covariance_array = np.asarray(decoded.covariances)[:, :, :horizon]
    label_array = np.asarray(labels)[:, :horizon]
    if probabilities.ndim != 2:
        raise ValueError(f"Expected batched probabilities, got {probabilities.shape}")

    top_ade: List[float] = []
    min_ade: List[float] = []
    top_fde: List[float] = []
    min_fde: List[float] = []
    best_probs: List[float] = []
    top_probs: List[float] = []
    entropies: List[float] = []
    trajectory_nll_per_step: List[float] = []
    pointwise_nll: List[float] = []
    top_mode_log_determinants: List[float] = []
    top_mode_determinants: List[float] = []
    mode_counts = [0 for _ in range(probabilities.shape[1])]
    top_is_best = 0
    coverage_hits = {name: 0 for name in CHI2_THRESHOLDS_2D}
    coverage_total = 0
    per_horizon_hits = {
        name: [0 for _ in range(horizon)] for name in CHI2_THRESHOLDS_2D
    }
    per_horizon_total = [0 for _ in range(horizon)]
    rollout_rows: Dict[str, List[Dict[str, float]]] = collections.defaultdict(list)
    init_group_rows: Dict[str, List[Dict[str, float]]] = collections.defaultdict(list)

    for sample_index, sample in enumerate(samples):
        probs = probabilities[sample_index].astype(np.float64)
        mus = means_array[sample_index].astype(np.float64)
        covariances = covariance_array[sample_index].astype(np.float64)
        label = label_array[sample_index].astype(np.float64)
        displacement = np.linalg.norm(mus - label[None, :, :], axis=-1)
        mode_ade = np.mean(displacement, axis=-1)
        mode_fde = displacement[:, -1]
        best = int(np.argmin(mode_ade))
        top = int(np.argmax(probs))
        mode_counts[best] += 1
        top_is_best += int(best == top)
        top_ade_value = float(mode_ade[top])
        min_ade_value = float(mode_ade[best])
        top_fde_value = float(mode_fde[top])
        min_fde_value = float(mode_fde[best])
        top_ade.append(top_ade_value)
        min_ade.append(min_ade_value)
        top_fde.append(top_fde_value)
        min_fde.append(min_fde_value)
        best_probs.append(float(probs[best]))
        top_probs.append(float(probs[top]))
        entropies.append(float(-np.sum(probs * np.log(np.maximum(probs, 1.0e-300)))))

        log_probabilities = np.log(np.maximum(probs, 1.0e-300))
        mode_trajectory_logpdf = np.zeros(len(probs), dtype=np.float64)
        timestep_nlls: List[float] = []
        for timestep in range(horizon):
            component_logpdf = np.full(len(probs), -np.inf, dtype=np.float64)
            for mode_index in range(len(probs)):
                residual = label[timestep] - mus[mode_index, timestep]
                logpdf, mahalanobis_sq, log_determinant = gaussian_logpdf_and_mahalanobis(
                    residual, covariances[mode_index, timestep]
                )
                component_logpdf[mode_index] = logpdf
                mode_trajectory_logpdf[mode_index] += logpdf
                if mode_index == top and np.isfinite(mahalanobis_sq):
                    coverage_total += 1
                    per_horizon_total[timestep] += 1
                    top_mode_log_determinants.append(log_determinant)
                    top_mode_determinants.append(math.exp(log_determinant))
                    for name, specification in CHI2_THRESHOLDS_2D.items():
                        hit = int(mahalanobis_sq <= specification["mahalanobis_sq"])
                        coverage_hits[name] += hit
                        per_horizon_hits[name][timestep] += hit
            timestep_nlls.append(
                float(-logsumexp(log_probabilities + component_logpdf, axis=0))
            )
        trajectory_nll = float(
            -logsumexp(log_probabilities + mode_trajectory_logpdf, axis=0) / horizon
        )
        point_nll = float(np.mean(timestep_nlls))
        trajectory_nll_per_step.append(trajectory_nll)
        pointwise_nll.append(point_nll)

        row = {
            "top1_ADE": top_ade_value,
            "minADE": min_ade_value,
            "top1_FDE": top_fde_value,
            "minFDE": min_fde_value,
            "trajectory_mixture_NLL_per_step": trajectory_nll,
            "pointwise_mixture_NLL": point_nll,
        }
        rollout_rows[rollout_group_key(sample)].append(row)
        init_group_rows[init_group_key(sample)].append(row)

    coverage = {}
    coverage_errors = []
    for name, specification in CHI2_THRESHOLDS_2D.items():
        empirical = coverage_hits[name] / coverage_total if coverage_total else float("nan")
        error = empirical - specification["nominal_coverage"]
        coverage_errors.append(abs(error))
        coverage[name] = {
            **specification,
            "empirical_coverage": finite_or_none(empirical),
            "signed_error": finite_or_none(error),
            "absolute_error": finite_or_none(abs(error)),
            "per_horizon_empirical": [
                finite_or_none(
                    per_horizon_hits[name][index] / per_horizon_total[index]
                    if per_horizon_total[index]
                    else float("nan")
                )
                for index in range(horizon)
            ],
        }

    rollout_metrics, rollout_macro = aggregate_group_rows(rollout_rows)
    init_group_metrics, init_group_macro = aggregate_group_rows(init_group_rows)

    covariance_audit = audit_covariances(covariance_array)
    historical_axis_stds = np.asarray(decoded.axis_standard_deviations)[:, :, :horizon]
    calibrated_axis_stds = historical_axis_stds * math.sqrt(covariance_scale)
    total = len(samples)
    flat_metrics = {
        "samples": total,
        "top1_ADE_mean": finite_or_none(mean(top_ade)),
        "minADE_mean": finite_or_none(mean(min_ade)),
        "top1_FDE_mean": finite_or_none(mean(top_fde)),
        "minFDE_mean": finite_or_none(mean(min_fde)),
        "minADE_p50": finite_or_none(percentile(min_ade, 50)),
        "minADE_p90": finite_or_none(percentile(min_ade, 90)),
        "minFDE_p50": finite_or_none(percentile(min_fde, 50)),
        "minFDE_p90": finite_or_none(percentile(min_fde, 90)),
        "top_prob_mode_is_best_frac": finite_or_none(
            top_is_best / total if total else float("nan")
        ),
        "mean_probability_assigned_to_best_mode": finite_or_none(mean(best_probs)),
        "mean_top_mode_probability": finite_or_none(mean(top_probs)),
        "mean_mode_entropy": finite_or_none(mean(entropies)),
        "best_mode_counts": mode_counts,
        "trajectory_mixture_NLL_per_step_mean": finite_or_none(
            mean(trajectory_nll_per_step)
        ),
        "pointwise_mixture_NLL_mean": finite_or_none(mean(pointwise_nll)),
    }
    return {
        **flat_metrics,
        "calibration_parameters": {
            "temperature": temperature,
            "covariance_scale": covariance_scale,
            "covariance_scale_semantics": COVARIANCE_SCALE_SEMANTICS,
        },
        "accuracy": {
            "top1_ADE": summary(top_ade),
            "minADE": summary(min_ade),
            "top1_FDE": summary(top_fde),
            "minFDE": summary(min_fde),
            "top_prob_mode_is_best_fraction": flat_metrics[
                "top_prob_mode_is_best_frac"
            ],
            "best_mode_counts": mode_counts,
            "mean_mode_entropy": flat_metrics["mean_mode_entropy"],
        },
        "probabilistic": {
            "trajectory_mixture_NLL_per_step": summary(trajectory_nll_per_step),
            "pointwise_mixture_NLL": summary(pointwise_nll),
            "top_mode_2d_covariance_coverage": coverage,
            "coverage_mean_absolute_error": finite_or_none(mean(coverage_errors)),
            "top_mode_2sigma_tail_rate": finite_or_none(
                1.0 - coverage["2sigma"]["empirical_coverage"]
                if coverage["2sigma"]["empirical_coverage"] is not None
                else float("nan")
            ),
            "top_mode_covariance_determinant": summary(top_mode_determinants),
            "top_mode_log_covariance_determinant": summary(
                top_mode_log_determinants
            ),
            "covariance_audit": covariance_audit,
        },
        "historical_std_parameterization": {
            "name": STD_PARAMETERIZATION,
            "formula": "axis_std = exp(abs(raw_std_parameter))",
            "raw_parameter_absolute": summary(
                np.abs(
                    np.asarray(decoded.raw_trajectory_parameters)[:, :, :horizon, 2:4]
                )
                .reshape(-1)
                .tolist()
            ),
            "uncalibrated_axis_standard_deviation": summary(
                historical_axis_stds.reshape(-1).tolist()
            ),
            "posthoc_scaled_axis_standard_deviation": summary(
                calibrated_axis_stds.reshape(-1).tolist()
            ),
            "theoretical_uncalibrated_minimum_std": 1.0,
        },
        "rollout_aggregation": {
            "independent_rollouts": len(rollout_metrics),
            "group_key": "cell_id::source_subrun",
            "macro_mean": rollout_macro,
            "per_rollout": rollout_metrics,
        },
        "init_group_aggregation": {
            "independent_init_groups": len(init_group_metrics),
            "group_key": "ego_init_id",
            "design_role": "paired clustering unit shared by all available 2x2 cells",
            "macro_mean": init_group_macro,
            "per_init_group": init_group_metrics,
        },
    }


def calibration_sufficient_statistics(
    decoded: GMMDecodeResult, labels: np.ndarray, horizon: int
) -> Tuple[np.ndarray, np.ndarray]:
    means_array = np.asarray(decoded.means, dtype=np.float64)[:, :, :horizon]
    covariance_array = np.asarray(decoded.covariances, dtype=np.float64)[:, :, :horizon]
    label_array = np.asarray(labels, dtype=np.float64)[:, :horizon]
    sample_count, mode_count = means_array.shape[:2]
    log_determinant_sums = np.zeros((sample_count, mode_count), dtype=np.float64)
    mahalanobis_sums = np.zeros((sample_count, mode_count), dtype=np.float64)
    for sample_index in range(sample_count):
        for mode_index in range(mode_count):
            for timestep in range(horizon):
                residual = (
                    label_array[sample_index, timestep]
                    - means_array[sample_index, mode_index, timestep]
                )
                logpdf, mahalanobis_sq, log_determinant = gaussian_logpdf_and_mahalanobis(
                    residual, covariance_array[sample_index, mode_index, timestep]
                )
                if not np.isfinite(logpdf):
                    raise ValueError(
                        "Cannot fit calibration with invalid covariance: "
                        f"sample={sample_index}, mode={mode_index}, timestep={timestep}"
                    )
                log_determinant_sums[sample_index, mode_index] += log_determinant
                mahalanobis_sums[sample_index, mode_index] += mahalanobis_sq
    return log_determinant_sums, mahalanobis_sums


def positive_log_grid(minimum: float, maximum: float, count: int) -> np.ndarray:
    if minimum <= 0 or maximum <= 0 or maximum < minimum or count < 2:
        raise ValueError(
            f"Invalid positive log grid: minimum={minimum}, maximum={maximum}, count={count}"
        )
    values = np.geomspace(minimum, maximum, count)
    return np.unique(np.concatenate([values, np.asarray([1.0])]))


def fit_validation_calibration(
    raw_predictions: np.ndarray,
    anchors: np.ndarray,
    labels: np.ndarray,
    samples: Sequence[Mapping[str, Any]],
    horizon: int,
    args: argparse.Namespace,
) -> Dict[str, Any]:
    base = decode_raw_predictions(raw_predictions, anchors)
    covariance_audit = audit_covariances(np.asarray(base.covariances)[:, :, :horizon])
    if covariance_audit["invalid_matrices"]:
        raise ValueError(
            f"Cannot calibrate: {covariance_audit['invalid_matrices']} invalid covariance matrices"
        )
    log_determinants, mahalanobis = calibration_sufficient_statistics(
        base, labels, horizon
    )
    logits = np.asarray(base.logits, dtype=np.float64)
    rollout_indices: Dict[str, List[int]] = collections.defaultdict(list)
    init_group_ids = set()
    for sample_index, sample in enumerate(samples):
        rollout_indices[rollout_group_key(sample)].append(sample_index)
        init_group_ids.add(init_group_key(sample))
    temperatures = positive_log_grid(
        args.temperature_min, args.temperature_max, args.temperature_count
    )
    covariance_scales = positive_log_grid(
        args.covariance_scale_min,
        args.covariance_scale_max,
        args.covariance_scale_count,
    )
    candidates: List[Dict[str, float]] = []
    constant = -horizon * math.log(2.0 * math.pi)
    for covariance_scale in covariance_scales:
        mode_logpdf = (
            constant
            - 0.5
            * (
                log_determinants
                + 2.0 * horizon * math.log(float(covariance_scale))
                + mahalanobis / float(covariance_scale)
            )
        )
        for temperature in temperatures:
            log_probabilities = log_softmax(logits, float(temperature))
            per_sample = -logsumexp(log_probabilities + mode_logpdf, axis=1) / horizon
            per_rollout = [
                float(np.mean(per_sample[indices]))
                for indices in rollout_indices.values()
            ]
            score = float(np.mean(per_rollout))
            candidates.append(
                {
                    "temperature": float(temperature),
                    "covariance_scale": float(covariance_scale),
                    "validation_trajectory_mixture_NLL_per_step": score,
                    "distance_from_identity": abs(math.log(float(temperature)))
                    + abs(math.log(float(covariance_scale))),
                }
            )
    candidates.sort(
        key=lambda item: (
            item["validation_trajectory_mixture_NLL_per_step"],
            item["distance_from_identity"],
        )
    )
    best = candidates[0]
    identity = min(
        candidates,
        key=lambda item: abs(math.log(item["temperature"]))
        + abs(math.log(item["covariance_scale"])),
    )
    return {
        "calibration_schema_version": "multipath_posthoc_calibration_v2",
        "fit_split": "val",
        "fit_criterion": (
            "macro mean over validation rollouts of trajectory mixture NLL per valid step"
        ),
        "parameters": {
            "temperature": best["temperature"],
            "covariance_scale": best["covariance_scale"],
            "covariance_scale_semantics": COVARIANCE_SCALE_SEMANTICS,
        },
        "search": {
            "temperature_candidates": len(temperatures),
            "covariance_scale_candidates": len(covariance_scales),
            "joint_candidates": len(candidates),
            "independent_validation_rollouts": len(rollout_indices),
            "validation_rollout_group_key": "cell_id::source_subrun",
            "independent_validation_init_groups": len(init_group_ids),
            "validation_init_group_key": "ego_init_id",
            "temperature_range": [float(temperatures[0]), float(temperatures[-1])],
            "covariance_scale_range": [
                float(covariance_scales[0]),
                float(covariance_scales[-1]),
            ],
            "identity_validation_NLL_per_step": identity[
                "validation_trajectory_mixture_NLL_per_step"
            ],
            "best_validation_NLL_per_step": best[
                "validation_trajectory_mixture_NLL_per_step"
            ],
            "top_candidates": candidates[:10],
        },
    }


def load_calibration(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        calibration = json.load(handle)
    if calibration.get("fit_split") != "val":
        raise ValueError(
            f"Calibration must be fitted on validation split, got {calibration.get('fit_split')}"
        )
    parameters = calibration.get("parameters") or {}
    temperature = float(parameters["temperature"])
    covariance_scale = float(parameters["covariance_scale"])
    if temperature <= 0 or covariance_scale <= 0:
        raise ValueError("Calibration temperature and covariance scale must be positive")
    return calibration


def evaluate(args: argparse.Namespace) -> Dict[str, Any]:
    if args.fit_calibration and args.split != "val":
        raise ValueError("--fit-calibration is only allowed with --split val")
    if args.fit_calibration and args.calibration_json:
        raise ValueError("Do not combine --fit-calibration and --calibration-json")

    merged_dir = os.path.abspath(args.merged_dir)
    result_dir = os.path.abspath(os.path.join(merged_dir, os.pardir))
    jsonl_path = os.path.join(merged_dir, f"{args.split}.jsonl")
    anchors = np.load(args.anchors).astype(np.float32)
    if anchors.shape[1] < args.horizon:
        raise ValueError(
            f"Anchor horizon {anchors.shape[1]} is shorter than --horizon {args.horizon}"
        )

    model = tf.keras.models.load_model(args.model, compile=False)
    input_count = len(getattr(model, "inputs", []))
    preloaded_calibration = (
        load_calibration(args.calibration_json) if args.calibration_json else None
    )
    iterator = load_samples(
        jsonl_path,
        result_dir,
        args.horizon,
        max_samples=args.max_samples,
        no_image=args.no_image,
        subset=args.subset,
    )
    try:
        samples, raw_predictions, labels, latency = run_model(
            model,
            input_count,
            iterator,
            args.batch_size,
            args.no_image,
        )
    except NoUsableSubsetSamples:
        if args.subset == "all":
            raise
        return {
            "evaluation_schema_version": "multipath_accuracy_calibration_v2",
            "status": "not_applicable",
            "reason": "no_full_horizon_samples_in_requested_subset",
            "model": os.path.abspath(args.model),
            "model_artifact": artifact_hash(Path(args.model).resolve()),
            "merged_dir": merged_dir,
            "split": args.split,
            "subset": args.subset,
            "calibration_fit_uses_test": False,
            "model_input_count": input_count,
            "uses_interaction_context": bool(input_count >= 3),
            "samples": 0,
            "independent_rollouts": 0,
            "independent_init_groups": 0,
            "calibration": preloaded_calibration,
        }
    uncalibrated_decoded = decode_raw_predictions(raw_predictions, anchors)
    uncalibrated_metrics = evaluate_decoded(
        uncalibrated_decoded,
        labels,
        samples,
        args.horizon,
        temperature=1.0,
        covariance_scale=1.0,
    )

    calibration = preloaded_calibration
    if args.fit_calibration:
        calibration = fit_validation_calibration(
            raw_predictions, anchors, labels, samples, args.horizon, args
        )
        if not args.calibration_output_json:
            raise ValueError("--calibration-output-json is required with --fit-calibration")
        calibration.update(
            {
                "model_artifact": artifact_hash(Path(args.model).resolve()),
                "anchors_artifact": artifact_hash(Path(args.anchors).resolve()),
                "validation_jsonl": artifact_hash(Path(jsonl_path).resolve()),
                "samples": len(samples),
                "horizon": args.horizon,
                "std_parameterization": STD_PARAMETERIZATION,
            }
        )
        calibration_output = Path(args.calibration_output_json).expanduser().resolve()
        calibration_output.parent.mkdir(parents=True, exist_ok=True)
        calibration_output.write_text(
            json.dumps(calibration, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    calibrated_metrics = None
    if calibration is not None:
        parameters = calibration["parameters"]
        calibrated_decoded = decode_raw_predictions(
            raw_predictions,
            anchors,
            temperature=float(parameters["temperature"]),
            covariance_scale=float(parameters["covariance_scale"]),
        )
        calibrated_metrics = evaluate_decoded(
            calibrated_decoded,
            labels,
            samples,
            args.horizon,
            temperature=float(parameters["temperature"]),
            covariance_scale=float(parameters["covariance_scale"]),
        )

    failing_gates = []
    if uncalibrated_metrics["probabilistic"]["covariance_audit"]["invalid_matrices"]:
        failing_gates.append("uncalibrated_invalid_covariance")
    if calibrated_metrics and calibrated_metrics["probabilistic"]["covariance_audit"][
        "invalid_matrices"
    ]:
        failing_gates.append("calibrated_invalid_covariance")

    return {
        "evaluation_schema_version": "multipath_accuracy_calibration_v2",
        "status": "pass" if not failing_gates else "fail",
        "failing_gates": failing_gates,
        "model": os.path.abspath(args.model),
        "model_artifact": artifact_hash(Path(args.model).resolve()),
        "anchors": os.path.abspath(args.anchors),
        "anchors_artifact": artifact_hash(Path(args.anchors).resolve()),
        "merged_dir": merged_dir,
        "jsonl": artifact_hash(Path(jsonl_path).resolve()),
        "split": args.split,
        "subset": args.subset,
        "calibration_fit_uses_test": False,
        "model_input_count": input_count,
        "uses_interaction_context": bool(input_count >= 3),
        "samples": len(samples),
        "independent_rollouts": len({rollout_group_key(sample) for sample in samples}),
        "independent_init_groups": len({init_group_key(sample) for sample in samples}),
        "horizon": args.horizon,
        "latency": latency,
        "uncalibrated": uncalibrated_metrics,
        "calibration": calibration,
        "calibrated": calibrated_metrics,
        # Compatibility keys retain the historical uncalibrated point metrics.
        **{
            key: uncalibrated_metrics[key]
            for key in (
                "top1_ADE_mean",
                "minADE_mean",
                "top1_FDE_mean",
                "minFDE_mean",
                "minADE_p50",
                "minADE_p90",
                "minFDE_p50",
                "minFDE_p90",
                "top_prob_mode_is_best_frac",
                "mean_probability_assigned_to_best_mode",
                "mean_top_mode_probability",
                "mean_mode_entropy",
                "best_mode_counts",
            )
        },
    }


def main() -> None:
    args = parse_args()
    metrics = evaluate(args)
    output_json = args.output_json or os.path.join(
        os.path.abspath(args.merged_dir),
        f"model_calibration_metrics_{args.split}_{os.path.basename(os.path.abspath(args.model))}.json",
    )
    Path(output_json).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2, sort_keys=True)
        handle.write("\n")
    if metrics["status"] == "not_applicable":
        print(
            json.dumps(
                {
                    "status": metrics["status"],
                    "split": metrics["split"],
                    "subset": metrics["subset"],
                    "samples": 0,
                    "reason": metrics["reason"],
                    "output_json": str(Path(output_json).expanduser().resolve()),
                },
                indent=2,
            )
        )
        return
    print(
        json.dumps(
            {
                "status": metrics["status"],
                "split": metrics["split"],
                "samples": metrics["samples"],
                "independent_rollouts": metrics["independent_rollouts"],
                "uncalibrated": {
                    "top1_ADE_mean": metrics["uncalibrated"]["top1_ADE_mean"],
                    "top1_FDE_mean": metrics["uncalibrated"]["top1_FDE_mean"],
                    "trajectory_mixture_NLL_per_step_mean": metrics["uncalibrated"][
                        "trajectory_mixture_NLL_per_step_mean"
                    ],
                    "coverage_mean_absolute_error": metrics["uncalibrated"][
                        "probabilistic"
                    ]["coverage_mean_absolute_error"],
                    "invalid_covariances": metrics["uncalibrated"]["probabilistic"][
                        "covariance_audit"
                    ]["invalid_matrices"],
                },
                "calibrated": (
                    {
                        "parameters": metrics["calibration"]["parameters"],
                        "trajectory_mixture_NLL_per_step_mean": metrics["calibrated"][
                            "trajectory_mixture_NLL_per_step_mean"
                        ],
                        "coverage_mean_absolute_error": metrics["calibrated"][
                            "probabilistic"
                        ]["coverage_mean_absolute_error"],
                        "invalid_covariances": metrics["calibrated"]["probabilistic"][
                            "covariance_audit"
                        ]["invalid_matrices"],
                    }
                    if metrics["calibrated"] is not None
                    else None
                ),
                "output_json": str(Path(output_json).expanduser().resolve()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
