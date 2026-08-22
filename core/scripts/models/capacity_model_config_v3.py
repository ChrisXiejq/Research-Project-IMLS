#!/usr/bin/env python3
"""Deterministic parameter accounting and capacity matching for V3 models."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from capacity_study_v3_protocol import (
    CAPACITY_TARGETS,
    CAPACITY_TOLERANCE_FRACTION,
    HISTORY_HORIZONS_S,
    validate_capacity_count,
)


DEFAULT_FEATURE_DIM = 12
DEFAULT_SEQUENCE_LENGTH = 6
DEFAULT_BASE_FEATURE_DIM = 512
DEFAULT_MULTIPATH_OUTPUT_DIM = 2016


@dataclass(frozen=True)
class HeadCapacityConfig:
    capacity_tier: str
    adaptation: str
    rank: int | None
    trainable_parameters: int


@dataclass(frozen=True)
class EncoderCapacityConfig:
    family: str
    capacity_tier: str
    history_horizon_s: float
    trainable_parameters: int
    width: int
    transformer_heads: int | None = None
    transformer_layers: int | None = None
    transformer_ff_dim: int | None = None


def low_rank_head_parameter_count(
    rank: int,
    *,
    input_dim: int = DEFAULT_BASE_FEATURE_DIM,
    output_dim: int = DEFAULT_MULTIPATH_OUTPUT_DIM,
) -> int:
    if rank < 1:
        raise ValueError("Low-rank head rank must be positive")
    return rank * input_dim + rank * output_dim + output_dim


def full_head_parameter_count(
    *,
    input_dim: int = DEFAULT_BASE_FEATURE_DIM,
    output_dim: int = DEFAULT_MULTIPATH_OUTPUT_DIM,
) -> int:
    return (input_dim + 1) * output_dim


def mlp_parameter_count(
    width: int,
    *,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    feature_dim: int = DEFAULT_FEATURE_DIM,
    output_dim: int = DEFAULT_MULTIPATH_OUTPUT_DIM,
) -> int:
    if width < 1:
        raise ValueError("MLP width must be positive")
    flattened = sequence_length * feature_dim + sequence_length
    first = flattened * width + width
    second = width * width + width
    residual_heads = width * output_dim + output_dim
    return first + second + residual_heads


def transformer_parameter_count(
    width: int,
    heads: int,
    layers: int,
    ff_dim: int,
    *,
    sequence_length: int = DEFAULT_SEQUENCE_LENGTH,
    feature_dim: int = DEFAULT_FEATURE_DIM,
    output_dim: int = DEFAULT_MULTIPATH_OUTPUT_DIM,
) -> int:
    if width < 1 or heads < 1 or layers < 1 or ff_dim < 1:
        raise ValueError("Transformer dimensions must be positive")
    if width % heads:
        raise ValueError("Transformer width must be divisible by attention heads")
    token_projection = feature_dim * width + width
    positions = sequence_length * width
    # Keras MHA with query/key/value/output projections, all with bias.
    attention = 4 * width * width + 4 * width
    layer_norms = 4 * width
    feed_forward = width * ff_dim + ff_dim + ff_dim * width + width
    residual_heads = width * output_dim + output_dim
    return token_projection + positions + layers * (
        attention + layer_norms + feed_forward
    ) + residual_heads


def _nearest(target: int, candidates: list[tuple[int, tuple[Any, ...]]]) -> tuple[int, tuple[Any, ...]]:
    if not candidates:
        raise ValueError("Capacity search has no candidates")
    return min(candidates, key=lambda row: (abs(row[0] - target), row[0], row[1]))


def search_head_capacity(
    capacity_tier: str,
    *,
    input_dim: int = DEFAULT_BASE_FEATURE_DIM,
    output_dim: int = DEFAULT_MULTIPATH_OUTPUT_DIM,
) -> HeadCapacityConfig:
    target = CAPACITY_TARGETS[capacity_tier]
    if capacity_tier == "large":
        actual = full_head_parameter_count(input_dim=input_dim, output_dim=output_dim)
        validate_capacity_count(actual, target)
        return HeadCapacityConfig(capacity_tier, "full_head", None, actual)
    maximum_rank = min(input_dim, output_dim)
    actual, values = _nearest(
        target,
        [
            (
                low_rank_head_parameter_count(
                    rank, input_dim=input_dim, output_dim=output_dim
                ),
                (rank,),
            )
            for rank in range(1, maximum_rank + 1)
        ],
    )
    validate_capacity_count(actual, target)
    return HeadCapacityConfig(capacity_tier, "low_rank_delta", int(values[0]), actual)


def search_mlp_capacity(
    capacity_tier: str,
    history_horizon_s: float,
    *,
    output_dim: int = DEFAULT_MULTIPATH_OUTPUT_DIM,
) -> EncoderCapacityConfig:
    if history_horizon_s not in HISTORY_HORIZONS_S:
        raise ValueError(f"Unsupported history horizon: {history_horizon_s}")
    target = CAPACITY_TARGETS[capacity_tier]
    actual, values = _nearest(
        target,
        [
            (mlp_parameter_count(width, output_dim=output_dim), (width,))
            for width in range(16, 1025)
        ],
    )
    validate_capacity_count(actual, target)
    return EncoderCapacityConfig(
        "mlp", capacity_tier, history_horizon_s, actual, int(values[0])
    )


def search_transformer_capacity(
    capacity_tier: str,
    history_horizon_s: float,
    *,
    output_dim: int = DEFAULT_MULTIPATH_OUTPUT_DIM,
) -> EncoderCapacityConfig:
    if history_horizon_s not in HISTORY_HORIZONS_S:
        raise ValueError(f"Unsupported history horizon: {history_horizon_s}")
    target = CAPACITY_TARGETS[capacity_tier]
    candidates: list[tuple[int, tuple[Any, ...]]] = []
    for layers in (1, 2, 3, 4):
        for heads in (2, 4, 8):
            for width in range(24, 321, 8):
                if width % heads:
                    continue
                for multiplier in (2, 4):
                    ff_dim = width * multiplier
                    count = transformer_parameter_count(
                        width, heads, layers, ff_dim, output_dim=output_dim
                    )
                    candidates.append(
                        (count, (layers, width, heads, ff_dim, multiplier))
                    )
    actual, values = _nearest(target, candidates)
    layers, width, heads, ff_dim, _ = values
    validate_capacity_count(actual, target)
    return EncoderCapacityConfig(
        "transformer",
        capacity_tier,
        history_horizon_s,
        actual,
        int(width),
        int(heads),
        int(layers),
        int(ff_dim),
    )


def capacity_manifest(output_dim: int = DEFAULT_MULTIPATH_OUTPUT_DIM) -> dict[str, Any]:
    head = [
        asdict(search_head_capacity(tier, output_dim=output_dim))
        for tier in CAPACITY_TARGETS
    ]
    encoders: list[dict[str, Any]] = []
    for horizon_s in HISTORY_HORIZONS_S:
        for tier in CAPACITY_TARGETS:
            encoders.append(asdict(search_mlp_capacity(tier, horizon_s, output_dim=output_dim)))
            encoders.append(
                asdict(search_transformer_capacity(tier, horizon_s, output_dim=output_dim))
            )
    by_key = {
        (row["family"], row["history_horizon_s"], row["capacity_tier"]): row
        for row in encoders
    }
    pair_audits = []
    for horizon_s in HISTORY_HORIZONS_S:
        for tier, target in CAPACITY_TARGETS.items():
            mlp = by_key[("mlp", horizon_s, tier)]
            transformer = by_key[("transformer", horizon_s, tier)]
            gap = abs(
                mlp["trainable_parameters"] - transformer["trainable_parameters"]
            )
            if gap / target > CAPACITY_TOLERANCE_FRACTION + 1.0e-12:
                raise ValueError(f"MLP/Transformer pair is outside tolerance: {horizon_s}/{tier}")
            pair_audits.append(
                {
                    "history_horizon_s": horizon_s,
                    "capacity_tier": tier,
                    "mlp_parameters": mlp["trainable_parameters"],
                    "transformer_parameters": transformer["trainable_parameters"],
                    "absolute_gap": gap,
                    "gap_over_target": gap / target,
                    "status": "pass",
                }
            )
    return {
        "schema_version": "capacity_model_manifest_v3",
        "status": "frozen",
        "output_dim": output_dim,
        "capacity_targets": CAPACITY_TARGETS,
        "tolerance_fraction": CAPACITY_TOLERANCE_FRACTION,
        "head_configs": head,
        "encoder_configs": encoders,
        "matched_pair_audits": pair_audits,
    }


def config_for_cell(
    family: str, capacity_tier: str, history_horizon_s: float | None
) -> HeadCapacityConfig | EncoderCapacityConfig:
    if family == "head":
        if history_horizon_s is not None:
            raise ValueError("Head cell history must be null")
        return search_head_capacity(capacity_tier)
    if history_horizon_s is None:
        raise ValueError("Encoder cells require a history horizon")
    if family == "mlp":
        return search_mlp_capacity(capacity_tier, history_horizon_s)
    if family == "transformer":
        return search_transformer_capacity(capacity_tier, history_horizon_s)
    raise ValueError(f"Unknown family: {family}")
