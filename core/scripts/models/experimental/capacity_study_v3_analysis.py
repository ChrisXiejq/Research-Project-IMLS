#!/usr/bin/env python3
"""Grouped three-axis inference and interaction-specific V3 metrics."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import itertools
import math
import platform
import time
from collections import defaultdict
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np

from capacity_study_v3_protocol import (
    CONFLICT_ZONE_BOUNDS_M,
    first_deceleration_onset_s,
)


PRIMARY_METRIC = "rollout_macro_nll"
APPENDIX_ONLY_EVIDENCE_PREFIXES = ("history_zero", "history_shuffle")


def aggregate_windows_by_rollout(
    rows: Sequence[Mapping[str, Any]], metric_fields: Sequence[str]
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        key = (
            row["dataset"],
            row["model_cell_id"],
            int(row["seed"]),
            int(row["ego_init_id"]),
            str(row["rollout_id"]),
        )
        grouped[key].append(row)
    result = []
    for key, members in sorted(grouped.items()):
        dataset, cell_id, seed, init_id, rollout_id = key
        payload = {
            "dataset": dataset,
            "model_cell_id": cell_id,
            "seed": seed,
            "ego_init_id": init_id,
            "rollout_id": rollout_id,
            "window_count": len(members),
        }
        for field in metric_fields:
            values = [float(row[field]) for row in members if row.get(field) is not None]
            payload[field] = float(np.mean(values)) if values else None
        result.append(payload)
    return result


def independent_unit_count(rows: Sequence[Mapping[str, Any]]) -> int:
    return len({int(row["ego_init_id"]) for row in rows})


def _cell_seed_init_values(
    rollout_rows: Sequence[Mapping[str, Any]], metric: str
) -> dict[tuple[str, int, int], float]:
    grouped: dict[tuple[str, int, int], list[float]] = defaultdict(list)
    for row in rollout_rows:
        value = row.get(metric)
        if value is None or not math.isfinite(float(value)):
            continue
        grouped[
            (str(row["model_cell_id"]), int(row["seed"]), int(row["ego_init_id"]))
        ].append(float(value))
    return {key: float(np.mean(values)) for key, values in grouped.items()}


def _cluster_effects(
    rollout_rows: Sequence[Mapping[str, Any]],
    terms: Sequence[tuple[str, float]],
    metric: str,
) -> dict[int, float]:
    values = _cell_seed_init_values(rollout_rows, metric)
    seed_init_sets = []
    for cell_id, _ in terms:
        seed_init_sets.append(
            {(seed, init_id) for c, seed, init_id in values if c == cell_id}
        )
    if not seed_init_sets:
        raise ValueError("Contrast requires at least one term")
    common = set.intersection(*seed_init_sets)
    if not common:
        raise ValueError(f"Contrast has no complete paired units: {terms}")
    by_init: dict[int, list[float]] = defaultdict(list)
    for seed, init_id in sorted(common):
        effect = sum(
            coefficient * values[(cell_id, seed, init_id)]
            for cell_id, coefficient in terms
        )
        by_init[init_id].append(effect)
    return {init_id: float(np.mean(effects)) for init_id, effects in by_init.items()}


def cluster_bootstrap_interval(
    effects_by_init: Mapping[int, float],
    *,
    seed: int = 20260822,
    replicates: int = 20_000,
    confidence: float = 0.95,
) -> tuple[float, float]:
    values = np.asarray(list(effects_by_init.values()), dtype=np.float64)
    if values.size < 2:
        return float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(replicates, values.size), replace=True).mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    return float(np.quantile(samples, alpha)), float(np.quantile(samples, 1.0 - alpha))


def paired_sign_flip_p(
    effects_by_init: Mapping[int, float],
    *,
    seed: int = 20260822,
    maximum_draws: int = 100_000,
) -> float:
    values = np.asarray(list(effects_by_init.values()), dtype=np.float64)
    if values.size == 0:
        return float("nan")
    observed = abs(float(np.mean(values)))
    total_exact = 2 ** values.size
    extreme = 0
    draws = 0
    if total_exact <= maximum_draws:
        iterator = itertools.product((-1.0, 1.0), repeat=values.size)
        for signs in iterator:
            statistic = abs(float(np.mean(values * np.asarray(signs))))
            extreme += statistic >= observed - 1.0e-15
            draws += 1
        return float(extreme / draws)
    else:
        rng = np.random.default_rng(seed)
        for _ in range(maximum_draws):
            signs = rng.choice((-1.0, 1.0), size=values.size)
            statistic = abs(float(np.mean(values * signs)))
            extreme += statistic >= observed - 1.0e-15
        draws = maximum_draws
    return float((extreme + 1) / (draws + 1))


def effect_summary(
    rollout_rows: Sequence[Mapping[str, Any]],
    *,
    contrast_id: str,
    terms: Sequence[tuple[str, float]],
    metric: str = PRIMARY_METRIC,
) -> dict[str, Any]:
    effects = _cluster_effects(rollout_rows, terms, metric)
    low, high = cluster_bootstrap_interval(effects)
    values = list(effects.values())
    return {
        "contrast_id": contrast_id,
        "metric": metric,
        "terms": [{"model_cell_id": cell, "coefficient": coefficient} for cell, coefficient in terms],
        "effect": float(np.mean(values)),
        "cluster_interval_95": [low, high],
        "independent_init_groups": len(effects),
        "paired_init_effects": {str(key): value for key, value in sorted(effects.items())},
        "raw_sign_flip_p": paired_sign_flip_p(effects),
    }


def crossed_seed_init_sensitivity(
    rollout_rows: Sequence[Mapping[str, Any]],
    *,
    contrast_id: str,
    terms: Sequence[tuple[str, float]],
    metric: str = PRIMARY_METRIC,
    seed: int = 20260828,
    replicates: int = 20_000,
) -> dict[str, Any]:
    """Propagate both fixed training-seed and held-out init-group variation.

    This is a descriptive crossed bootstrap sensitivity, not a replacement for
    the five-init paired sign-flip analysis.  Seeds and init groups are sampled
    independently, preserving the crossed design instead of treating the 15
    seed-by-init observations as independent replicates.
    """

    values = _cell_seed_init_values(rollout_rows, metric)
    pair_sets = [
        {(run_seed, init_id) for cell, run_seed, init_id in values if cell == cell_id}
        for cell_id, _ in terms
    ]
    if not pair_sets:
        raise ValueError("Crossed sensitivity requires at least one contrast term")
    common = set.intersection(*pair_sets)
    seeds = sorted({run_seed for run_seed, _ in common})
    init_groups = sorted({init_id for _, init_id in common})
    expected = {(run_seed, init_id) for run_seed in seeds for init_id in init_groups}
    if common != expected or len(seeds) < 2 or len(init_groups) < 2:
        raise ValueError(
            f"Crossed sensitivity requires a complete seed-by-init matrix: {contrast_id}"
        )
    matrix = np.asarray(
        [
            [
                sum(
                    coefficient * values[(cell_id, run_seed, init_id)]
                    for cell_id, coefficient in terms
                )
                for init_id in init_groups
            ]
            for run_seed in seeds
        ],
        dtype=np.float64,
    )
    rng = np.random.default_rng(seed)
    seed_indices = rng.integers(0, len(seeds), size=(replicates, len(seeds), 1))
    init_indices = rng.integers(
        0, len(init_groups), size=(replicates, 1, len(init_groups))
    )
    bootstrap = matrix[seed_indices, init_indices].mean(axis=(1, 2))
    low, high = np.quantile(bootstrap, (0.025, 0.975))
    return {
        "contrast_id": contrast_id,
        "metric": metric,
        "terms": [
            {"model_cell_id": cell, "coefficient": coefficient}
            for cell, coefficient in terms
        ],
        "effect": float(np.mean(matrix)),
        "crossed_bootstrap_interval_95": [float(low), float(high)],
        "training_seeds": seeds,
        "heldout_init_groups": init_groups,
        "seed_by_init_effects": {
            str(run_seed): {
                str(init_id): float(matrix[seed_index, init_index])
                for init_index, init_id in enumerate(init_groups)
            }
            for seed_index, run_seed in enumerate(seeds)
        },
        "effects_averaged_by_seed": {
            str(run_seed): float(np.mean(matrix[seed_index]))
            for seed_index, run_seed in enumerate(seeds)
        },
        "effects_averaged_by_init": {
            str(init_id): float(np.mean(matrix[:, init_index]))
            for init_index, init_id in enumerate(init_groups)
        },
        "bootstrap_replicates": replicates,
        "resampling_contract": (
            "Training seeds and held-out init groups were independently resampled; "
            "the 15 crossed observations were not treated as independent units."
        ),
        "inferential_role": "descriptive_crossed_sensitivity",
    }


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    finite = sorted(
        ((key, float(value)) for key, value in p_values.items() if math.isfinite(float(value))),
        key=lambda item: (item[1], item[0]),
    )
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(finite)
    for index, (key, value) in enumerate(finite):
        candidate = min(1.0, (count - index) * value)
        running = max(running, candidate)
        adjusted[key] = running
    for key, value in p_values.items():
        if not math.isfinite(float(value)):
            adjusted[key] = float("nan")
    return adjusted


def synthesize_three_axes(
    window_rows: Sequence[Mapping[str, Any]],
    *,
    dataset: str = "general_test",
) -> dict[str, Any]:
    eligible = [row for row in window_rows if row.get("dataset") == dataset]
    rollout_rows = aggregate_windows_by_rollout(eligible, [PRIMARY_METRIC])
    contrasts = [
        effect_summary(
            rollout_rows,
            contrast_id="H1_capacity_transformer_full_small_minus_large",
            terms=(("transformer-h1p0-small", 1.0), ("transformer-h1p0-large", -1.0)),
        ),
        effect_summary(
            rollout_rows,
            contrast_id="H2_information_mlp_snapshot_minus_full",
            terms=(("mlp-h0p0-large", 1.0), ("mlp-h1p0-large", -1.0)),
        ),
        effect_summary(
            rollout_rows,
            contrast_id="H2_information_transformer_snapshot_minus_full",
            terms=(("transformer-h0p0-large", 1.0), ("transformer-h1p0-large", -1.0)),
        ),
        effect_summary(
            rollout_rows,
            contrast_id="H3_attention_history_gain_difference_in_differences",
            terms=(
                ("transformer-h0p0-large", 1.0),
                ("transformer-h1p0-large", -1.0),
                ("mlp-h0p0-large", -1.0),
                ("mlp-h1p0-large", 1.0),
            ),
        ),
    ]
    supporting = [
        effect_summary(
            rollout_rows,
            contrast_id="architecture_direct_snapshot_mlp_minus_transformer",
            terms=(("mlp-h0p0-large", 1.0), ("transformer-h0p0-large", -1.0)),
        ),
        effect_summary(
            rollout_rows,
            contrast_id="architecture_direct_full_mlp_minus_transformer",
            terms=(("mlp-h1p0-large", 1.0), ("transformer-h1p0-large", -1.0)),
        ),
        effect_summary(
            rollout_rows,
            contrast_id="information_mlp_snapshot_minus_short",
            terms=(("mlp-h0p0-large", 1.0), ("mlp-h0p4-large", -1.0)),
        ),
        effect_summary(
            rollout_rows,
            contrast_id="information_transformer_snapshot_minus_short",
            terms=(("transformer-h0p0-large", 1.0), ("transformer-h0p4-large", -1.0)),
        ),
    ]
    adjusted = holm_adjust({row["contrast_id"]: row["raw_sign_flip_p"] for row in contrasts})
    for row in contrasts:
        row["holm_adjusted_p"] = adjusted[row["contrast_id"]]
    return {
        "schema_version": "capacity_history_three_axis_analysis_v3",
        "status": "pass",
        "dataset": dataset,
        "window_rows": len(eligible),
        "rollout_rows": len(rollout_rows),
        "independent_init_groups": independent_unit_count(rollout_rows),
        "primary_contrasts": contrasts,
        "supporting_contrasts": supporting,
        "sign_convention": "positive favours the named H1/H2/H3 direction",
    }


def target_speed_profile_rmse(
    predicted_xy: Sequence[Sequence[float]],
    true_xy: Sequence[Sequence[float]],
    times_s: Sequence[float],
) -> float | None:
    predicted = np.asarray(predicted_xy, dtype=np.float64)
    truth = np.asarray(true_xy, dtype=np.float64)
    times = np.asarray(times_s, dtype=np.float64)
    if predicted.shape != truth.shape or predicted.ndim != 2 or predicted.shape[1] != 2:
        raise ValueError("Predicted and true trajectories must share shape [time,2]")
    if times.shape != (predicted.shape[0],) or predicted.shape[0] < 2:
        raise ValueError("Trajectory times must match and contain at least two points")
    dt = np.diff(times)
    if np.any(dt <= 0.0):
        raise ValueError("Trajectory times must be strictly increasing")
    predicted_speed = np.linalg.norm(np.diff(predicted, axis=0), axis=1) / dt
    true_speed = np.linalg.norm(np.diff(truth, axis=0), axis=1) / dt
    return float(np.sqrt(np.mean(np.square(predicted_speed - true_speed))))


def response_onset_timing_error_s(
    predicted_xy: Sequence[Sequence[float]],
    true_xy: Sequence[Sequence[float]],
    times_s: Sequence[float],
) -> float | None:
    predicted = np.asarray(predicted_xy, dtype=np.float64)
    truth = np.asarray(true_xy, dtype=np.float64)
    times = np.asarray(times_s, dtype=np.float64)
    if predicted.shape != truth.shape or times.shape != (predicted.shape[0],):
        raise ValueError("Prediction, truth, and times must align")
    if len(times) < 3:
        return None
    interval_times = times[1:]
    dt = np.diff(times)
    predicted_speed = np.linalg.norm(np.diff(predicted, axis=0), axis=1) / dt
    true_speed = np.linalg.norm(np.diff(truth, axis=0), axis=1) / dt
    predicted_onset = first_deceleration_onset_s(interval_times, predicted_speed)
    true_onset = first_deceleration_onset_s(interval_times, true_speed)
    if predicted_onset is None or true_onset is None:
        return None
    return float(predicted_onset - true_onset)


def conflict_zone_probability_mass(
    mode_xy: Sequence[Sequence[Sequence[float]]],
    probabilities: Sequence[float],
    *,
    bounds: Mapping[str, float] = CONFLICT_ZONE_BOUNDS_M,
) -> float:
    trajectories = np.asarray(mode_xy, dtype=np.float64)
    weights = np.asarray(probabilities, dtype=np.float64)
    if trajectories.ndim != 3 or trajectories.shape[2] != 2:
        raise ValueError("Mode trajectories must have shape [mode,time,2]")
    if weights.shape != (trajectories.shape[0],) or np.any(weights < 0.0):
        raise ValueError("Mode probabilities must align and be non-negative")
    total = float(np.sum(weights))
    if not math.isfinite(total) or total <= 0.0:
        raise ValueError("Mode probabilities must have positive finite mass")
    weights = weights / total
    x, y = trajectories[..., 0], trajectories[..., 1]
    enters = np.any(
        (x >= bounds["x_min"])
        & (x <= bounds["x_max"])
        & (y >= bounds["y_min"])
        & (y <= bounds["y_max"]),
        axis=1,
    )
    return float(np.sum(weights[enters]))


def measure_latency(
    predict: Callable[[], Any],
    *,
    warmup_count: int = 20,
    measured_count: int = 100,
    trainable_parameters: int | None = None,
) -> dict[str, Any]:
    if warmup_count < 1 or measured_count < 2:
        raise ValueError("Latency measurement requires warmup>=1 and measured>=2")
    for _ in range(warmup_count):
        predict()
    durations = []
    for _ in range(measured_count):
        started = time.perf_counter()
        predict()
        durations.append(1000.0 * (time.perf_counter() - started))
    return {
        "warmup_count": warmup_count,
        "measured_count": measured_count,
        "batch_size": 1,
        "mean_ms": float(np.mean(durations)),
        "p50_ms": float(np.quantile(durations, 0.50)),
        "p95_ms": float(np.quantile(durations, 0.95)),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "trainable_parameters": trainable_parameters,
        "estimated_dense_multiply_add_flops": (
            2 * int(trainable_parameters) if trainable_parameters is not None else None
        ),
    }


def pareto_membership(
    rows: Sequence[Mapping[str, Any]],
    *,
    error_field: str = "rollout_macro_nll",
    latency_field: str = "mean_ms",
) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        error = float(row[error_field])
        latency = float(row[latency_field])
        dominated = any(
            float(other[error_field]) <= error
            and float(other[latency_field]) <= latency
            and (
                float(other[error_field]) < error
                or float(other[latency_field]) < latency
            )
            for other in rows
            if other is not row
        )
        result.append({**row, "pareto": not dominated})
    return result


def validate_claim_evidence(claim_axis: str, evidence_ids: Iterable[str]) -> None:
    evidence = tuple(str(value) for value in evidence_ids)
    if claim_axis in {"capacity", "information", "architecture"} and any(
        identifier.startswith(APPENDIX_ONLY_EVIDENCE_PREFIXES) for identifier in evidence
    ):
        raise ValueError("Zero/shuffle appendix diagnostics cannot support headline claims")
