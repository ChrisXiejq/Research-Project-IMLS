#!/usr/bin/env python3
"""Capacity- and history-controlled full-distribution V3 prediction models."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import tensorflow as tf

from capacity_model_config_v3 import (
    EncoderCapacityConfig,
    HeadCapacityConfig,
    config_for_cell,
)
from capacity_study_v3_protocol import HISTORY_MASKS
from interaction_adapter_v2 import (
    AddLearnedPosition,
    ApplyTokenMask,
    MaskedMeanPooling,
    MaskedZScore,
    MultipathResidualMerge,
    PairwiseAttentionMask,
    _infer_multipath_dimensions,
    configure_v2_b1_head,
)


@tf.keras.utils.register_keras_serializable(package="imls")
class FixedHistoryHorizon(tf.keras.layers.Layer):
    def __init__(self, history_horizon_s: float, **kwargs):
        super().__init__(**kwargs)
        value = float(history_horizon_s)
        if value not in HISTORY_MASKS:
            raise ValueError(f"Unsupported history horizon: {value}")
        self.history_horizon_s = value
        self.fixed_mask_values = [float(item) for item in HISTORY_MASKS[value]]

    def call(self, inputs):
        sequence, mask = inputs
        fixed = tf.constant(self.fixed_mask_values, dtype=mask.dtype)[None, :]
        effective = mask * fixed
        return sequence * tf.cast(effective[..., None], sequence.dtype), effective

    def get_config(self):
        return {**super().get_config(), "history_horizon_s": self.history_horizon_s}


def build_capacity_head_adapter(
    base_model: tf.keras.Model,
    capacity_tier: str,
) -> tuple[tf.keras.Model, HeadCapacityConfig]:
    """Build full B1 or a zero-output low-rank delta over the frozen B0 head."""

    final_dense = next(
        (layer for layer in reversed(base_model.layers) if isinstance(layer, tf.keras.layers.Dense)),
        None,
    )
    if final_dense is None:
        raise ValueError("Base model has no Dense prediction head")
    input_dim = int(final_dense.kernel.shape[0])
    output_dim = int(final_dense.kernel.shape[1])
    config = config_for_cell("head", capacity_tier, None)
    # Recompute against the actual model in case a compatible backbone changes dimensions.
    from capacity_model_config_v3 import search_head_capacity

    config = search_head_capacity(
        capacity_tier, input_dim=input_dim, output_dim=output_dim
    )
    if config.adaptation == "full_head":
        return configure_v2_b1_head(base_model), config

    base_model.trainable = False
    features = final_dense.input
    rank_features = tf.keras.layers.Dense(
        int(config.rank),
        use_bias=False,
        kernel_initializer="glorot_uniform",
        name=f"v3_{capacity_tier}_head_low_rank_in",
    )(features)
    delta = tf.keras.layers.Dense(
        output_dim,
        use_bias=True,
        kernel_initializer="zeros",
        bias_initializer="zeros",
        name=f"v3_{capacity_tier}_head_low_rank_out",
    )(rank_features)
    output = tf.keras.layers.Add(name=f"v3_{capacity_tier}_head_merge")(
        [base_model.output, delta]
    )
    model = tf.keras.Model(
        base_model.inputs,
        output,
        name=f"multipath_head_{capacity_tier}_v3",
    )
    return model, config


def _full_distribution_heads(
    context,
    *,
    num_modes: int,
    num_timesteps: int,
):
    zero = tf.keras.initializers.Zeros()
    mean_raw = tf.keras.layers.Dense(
        num_modes * num_timesteps * 2,
        kernel_initializer=zero,
        bias_initializer=zero,
        name="mean_residual_head",
    )(context)
    std_raw = tf.keras.layers.Dense(
        num_modes * num_timesteps * 2,
        kernel_initializer=zero,
        bias_initializer=zero,
        name="std_residual_head",
    )(context)
    angle_raw = tf.keras.layers.Dense(
        num_modes * num_timesteps,
        kernel_initializer=zero,
        bias_initializer=zero,
        name="orientation_residual_head",
    )(context)
    logit_raw = tf.keras.layers.Dense(
        num_modes,
        kernel_initializer=zero,
        bias_initializer=zero,
        name="logit_residual_head",
    )(context)
    return mean_raw, std_raw, angle_raw, logit_raw


def _capacity_residual_from_history(
    base_raw,
    sequence,
    mask,
    *,
    anchors: np.ndarray,
    normalization: Mapping[str, Any],
    family: str,
    capacity_tier: str,
    history_horizon_s: float,
    dropout: float,
):
    config = config_for_cell(family, capacity_tier, history_horizon_s)
    assert isinstance(config, EncoderCapacityConfig)
    num_modes = int(np.asarray(anchors).shape[0])
    output_dim = int(base_raw.shape[-1])
    per_mode = output_dim - num_modes
    if per_mode <= 0 or per_mode % (num_modes * 5) != 0:
        raise ValueError("Cached/full base output is incompatible with MultiPath dimensions")
    num_timesteps = per_mode // (num_modes * 5)
    horizon_sequence, horizon_mask = FixedHistoryHorizon(
        history_horizon_s, name="fixed_history_horizon"
    )([sequence, mask])
    normalized = MaskedZScore(
        normalization["mean"], normalization["std"], name="train_only_zscore"
    )([horizon_sequence, horizon_mask])

    if family == "mlp":
        x = tf.keras.layers.Flatten(name="mlp_flatten")(normalized)
        x = tf.keras.layers.Concatenate(name="mlp_mask_concat")([x, horizon_mask])
        x = tf.keras.layers.Dense(config.width, activation="gelu", name="mlp_dense_1")(x)
        x = tf.keras.layers.Dropout(dropout, name="mlp_dropout")(x)
        context = tf.keras.layers.Dense(
            config.width, activation="gelu", name="mlp_dense_2"
        )(x)
    else:
        width = config.width
        x = tf.keras.layers.Dense(width, name="token_projection")(normalized)
        x = AddLearnedPosition(6, width, name="position_embedding")(x)
        x = ApplyTokenMask(name="position_token_mask")([x, horizon_mask])
        attention_mask = PairwiseAttentionMask(name="pairwise_attention_mask")(
            horizon_mask
        )
        for index in range(int(config.transformer_layers)):
            prefix = f"transformer_block_{index + 1}"
            attended = tf.keras.layers.MultiHeadAttention(
                num_heads=int(config.transformer_heads),
                key_dim=width // int(config.transformer_heads),
                dropout=dropout,
                name=f"{prefix}_self_attention",
            )(x, x, attention_mask=attention_mask)
            attended = tf.keras.layers.Dropout(
                dropout, name=f"{prefix}_attention_dropout"
            )(attended)
            x = tf.keras.layers.LayerNormalization(
                epsilon=1.0e-6, name=f"{prefix}_attention_norm"
            )(tf.keras.layers.Add(name=f"{prefix}_attention_add")([x, attended]))
            fed = tf.keras.layers.Dense(
                int(config.transformer_ff_dim),
                activation="gelu",
                name=f"{prefix}_ff_expand",
            )(x)
            fed = tf.keras.layers.Dropout(dropout, name=f"{prefix}_ff_dropout")(fed)
            fed = tf.keras.layers.Dense(width, name=f"{prefix}_ff_contract")(fed)
            fed = tf.keras.layers.Dropout(
                dropout, name=f"{prefix}_residual_dropout"
            )(fed)
            x = tf.keras.layers.LayerNormalization(
                epsilon=1.0e-6, name=f"{prefix}_output_norm"
            )(tf.keras.layers.Add(name=f"{prefix}_output_add")([x, fed]))
            x = ApplyTokenMask(name=f"{prefix}_token_mask")([x, horizon_mask])
        context = MaskedMeanPooling(name="masked_temporal_pool")([x, horizon_mask])

    mean_raw, std_raw, angle_raw, logit_raw = _full_distribution_heads(
        context, num_modes=num_modes, num_timesteps=num_timesteps
    )
    output = MultipathResidualMerge(
        num_modes,
        num_timesteps,
        True,
        name="structured_residual_merge",
    )([base_raw, mean_raw, std_raw, angle_raw, logit_raw])
    return output, config


def build_cached_capacity_interaction_adapter(
    base_output_dim: int,
    anchors: np.ndarray,
    normalization: Mapping[str, Any],
    family: str,
    capacity_tier: str,
    history_horizon_s: float,
    *,
    dropout: float = 0.1,
) -> tuple[tf.keras.Model, EncoderCapacityConfig]:
    """Build the trainable adapter over cached frozen-B0 outputs."""

    base_raw = tf.keras.Input((int(base_output_dim),), name="cached_base_raw")
    sequence = tf.keras.Input((6, 12), name="interaction_sequence")
    mask = tf.keras.Input((6,), name="interaction_sequence_mask")
    output, config = _capacity_residual_from_history(
        base_raw,
        sequence,
        mask,
        anchors=anchors,
        normalization=normalization,
        family=family,
        capacity_tier=capacity_tier,
        history_horizon_s=history_horizon_s,
        dropout=dropout,
    )
    return (
        tf.keras.Model(
            [base_raw, sequence, mask],
            output,
            name=(
                f"cached_multipath_{family}_{capacity_tier}_"
                f"h{history_horizon_s:.1f}_v3".replace(".", "p")
            ),
        ),
        config,
    )


def build_capacity_interaction_adapter(
    base_model: tf.keras.Model,
    anchors: np.ndarray,
    normalization: Mapping[str, Any],
    family: str,
    capacity_tier: str,
    history_horizon_s: float,
    *,
    dropout: float = 0.1,
) -> tuple[tf.keras.Model, EncoderCapacityConfig]:
    if family not in {"mlp", "transformer"}:
        raise ValueError(f"Unsupported V3 encoder family: {family}")
    config = config_for_cell(family, capacity_tier, history_horizon_s)
    assert isinstance(config, EncoderCapacityConfig)
    num_modes, num_timesteps = _infer_multipath_dimensions(base_model, anchors)
    base_model.trainable = False
    image_shape = tuple(base_model.inputs[0].shape[1:])
    state_shape = tuple(base_model.inputs[1].shape[1:])
    image = tf.keras.Input(image_shape, name="image_input_v3")
    past = tf.keras.Input(state_shape, name="state_input_v3")
    sequence = tf.keras.Input((6, 12), name="interaction_sequence")
    mask = tf.keras.Input((6,), name="interaction_sequence_mask")
    base_raw = base_model([image, past], training=False)
    output, config = _capacity_residual_from_history(
        base_raw,
        sequence,
        mask,
        anchors=anchors,
        normalization=normalization,
        family=family,
        capacity_tier=capacity_tier,
        history_horizon_s=history_horizon_s,
        dropout=dropout,
    )
    model = tf.keras.Model(
        [image, past, sequence, mask],
        output,
        name=(
            f"multipath_{family}_{capacity_tier}_"
            f"h{history_horizon_s:.1f}_v3".replace(".", "p")
        ),
    )
    return model, config
