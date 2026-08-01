#!/usr/bin/env python3
"""V2 interaction-conditioned residual adapters for frozen MultiPath output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import numpy as np
import tensorflow as tf


VARIANTS = ("B2-M", "B2-D", "T1", "T2")


def configure_v2_b1_head(base_model: tf.keras.Model) -> tf.keras.Model:
    """Freeze B1 except for its final Dense prediction head."""

    for layer in base_model.layers:
        layer.trainable = False
    for layer in reversed(base_model.layers):
        if isinstance(layer, tf.keras.layers.Dense):
            layer.trainable = True
            break
    else:
        raise ValueError("B1 base model has no Dense prediction head")
    return base_model


@tf.keras.utils.register_keras_serializable(package="imls")
class MaskedZScore(tf.keras.layers.Layer):
    def __init__(self, mean, std, **kwargs):
        super().__init__(**kwargs)
        self.mean_values = [float(value) for value in mean]
        self.std_values = [float(value) for value in std]

    def call(self, inputs):
        sequence, mask = inputs
        mean = tf.constant(self.mean_values, dtype=sequence.dtype)[None, None, :]
        std = tf.constant(self.std_values, dtype=sequence.dtype)[None, None, :]
        valid = tf.cast(mask[..., None], sequence.dtype)
        return ((sequence - mean) / std) * valid

    def get_config(self):
        return {**super().get_config(), "mean": self.mean_values, "std": self.std_values}


@tf.keras.utils.register_keras_serializable(package="imls")
class MaskedMeanPooling(tf.keras.layers.Layer):
    def call(self, inputs):
        sequence, mask = inputs
        valid = tf.cast(mask[..., None], sequence.dtype)
        denominator = tf.maximum(tf.reduce_sum(valid, axis=1), 1.0)
        return tf.reduce_sum(sequence * valid, axis=1) / denominator


@tf.keras.utils.register_keras_serializable(package="imls")
class AddLearnedPosition(tf.keras.layers.Layer):
    def __init__(self, sequence_length: int, width: int, **kwargs):
        super().__init__(**kwargs)
        self.sequence_length = int(sequence_length)
        self.width = int(width)

    def build(self, input_shape):
        self.embedding = self.add_weight(
            name="embedding",
            shape=(self.sequence_length, self.width),
            initializer="glorot_uniform",
            trainable=True,
        )
        super().build(input_shape)

    def call(self, inputs):
        return inputs + self.embedding[None, :, :]

    def get_config(self):
        return {
            **super().get_config(),
            "sequence_length": self.sequence_length,
            "width": self.width,
        }


@tf.keras.utils.register_keras_serializable(package="imls")
class PairwiseAttentionMask(tf.keras.layers.Layer):
    """Expand a [batch, time] token mask to [batch, query, key]."""

    def call(self, mask):
        valid = tf.cast(mask > 0.0, tf.bool)
        return tf.logical_and(valid[:, :, None], valid[:, None, :])


@tf.keras.utils.register_keras_serializable(package="imls")
class ApplyTokenMask(tf.keras.layers.Layer):
    def call(self, inputs):
        sequence, mask = inputs
        return sequence * tf.cast(mask[..., None], sequence.dtype)


@tf.keras.utils.register_keras_serializable(package="imls")
class MultipathResidualMerge(tf.keras.layers.Layer):
    def __init__(
        self,
        num_modes: int,
        num_timesteps: int,
        distributional: bool,
        mean_scale_m: float = 2.0,
        log_std_scale: float = 0.35,
        orientation_scale_rad: float = 0.35,
        logit_scale: float = 2.0,
        maximum_abs_std_parameter: float = 5.0,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.num_modes = int(num_modes)
        self.num_timesteps = int(num_timesteps)
        self.distributional = bool(distributional)
        self.mean_scale_m = float(mean_scale_m)
        self.log_std_scale = float(log_std_scale)
        self.orientation_scale_rad = float(orientation_scale_rad)
        self.logit_scale = float(logit_scale)
        self.maximum_abs_std_parameter = float(maximum_abs_std_parameter)

    def call(self, inputs):
        base_raw, mean_raw, std_raw, angle_raw, logit_raw = inputs
        batch = tf.shape(base_raw)[0]
        trajectories = tf.reshape(
            base_raw[:, :-self.num_modes],
            (batch, self.num_modes, self.num_timesteps, 5),
        )
        logits = base_raw[:, -self.num_modes:]
        mean_delta = self.mean_scale_m * tf.tanh(
            tf.reshape(mean_raw, (batch, self.num_modes, self.num_timesteps, 2))
        )
        xy = trajectories[..., :2] + mean_delta
        if self.distributional:
            std_delta = self.log_std_scale * tf.tanh(
                tf.reshape(std_raw, (batch, self.num_modes, self.num_timesteps, 2))
            )
            base_std_parameters = trajectories[..., 2:4]
            adjusted_abs_std = tf.clip_by_value(
                tf.abs(trajectories[..., 2:4]) + std_delta,
                0.0,
                self.maximum_abs_std_parameter,
            )
            base_sign = tf.where(base_std_parameters < 0.0, -1.0, 1.0)
            std_parameters = base_sign * adjusted_abs_std
            angle_delta = self.orientation_scale_rad * tf.tanh(
                tf.reshape(angle_raw, (batch, self.num_modes, self.num_timesteps))
            )
            angles = trajectories[..., 4] + angle_delta
            logits = logits + self.logit_scale * tf.tanh(logit_raw)
        else:
            std_parameters = trajectories[..., 2:4]
            angles = trajectories[..., 4]
        merged = tf.concat([xy, std_parameters, angles[..., None]], axis=-1)
        return tf.concat([tf.reshape(merged, (batch, -1)), logits], axis=-1)

    def get_config(self):
        return {
            **super().get_config(),
            "num_modes": self.num_modes,
            "num_timesteps": self.num_timesteps,
            "distributional": self.distributional,
            "mean_scale_m": self.mean_scale_m,
            "log_std_scale": self.log_std_scale,
            "orientation_scale_rad": self.orientation_scale_rad,
            "logit_scale": self.logit_scale,
            "maximum_abs_std_parameter": self.maximum_abs_std_parameter,
        }


def load_normalization(path: str | Path) -> Dict[str, Any]:
    payload = json.loads(Path(path).read_text())
    if payload.get("fit_split") != "train" or payload.get("schema_id") != "give_way_interaction_sequence_v2":
        raise ValueError("Normalization is not the frozen train-only V2 artifact")
    if len(payload.get("mean", [])) != 12 or len(payload.get("std", [])) != 12:
        raise ValueError("Expected 12-feature normalization")
    if not np.all(np.isfinite(payload["mean"])) or not np.all(np.asarray(payload["std"]) > 0.0):
        raise ValueError("Normalization values must be finite with positive std")
    return payload


def _infer_multipath_dimensions(base_model: tf.keras.Model, anchors: np.ndarray) -> tuple[int, int]:
    num_modes, num_timesteps = int(anchors.shape[0]), int(anchors.shape[1])
    expected = num_modes * num_timesteps * 5 + num_modes
    actual = int(base_model.output_shape[-1])
    if actual != expected:
        raise ValueError(f"Base output width {actual} != expected MultiPath width {expected}")
    return num_modes, num_timesteps


def build_interaction_adapter(
    base_model: tf.keras.Model,
    anchors: np.ndarray,
    normalization: Dict[str, Any],
    variant: str,
    *,
    transformer_width: int = 64,
    transformer_heads: int = 4,
    transformer_layers: int = 1,
    transformer_ff_dim: int = 128,
    mlp_width: int = 80,
    dropout: float = 0.1,
) -> tf.keras.Model:
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant {variant}; expected one of {VARIANTS}")
    num_modes, num_timesteps = _infer_multipath_dimensions(base_model, anchors)
    base_model.trainable = False
    image_shape = tuple(base_model.inputs[0].shape[1:])
    state_shape = tuple(base_model.inputs[1].shape[1:])
    image = tf.keras.Input(image_shape, name="image_input_v2")
    past = tf.keras.Input(state_shape, name="state_input_v2")
    sequence = tf.keras.Input((6, 12), name="interaction_sequence")
    mask = tf.keras.Input((6,), name="interaction_sequence_mask")
    base_raw = base_model([image, past], training=False)
    normalized = MaskedZScore(
        normalization["mean"], normalization["std"], name="train_only_zscore"
    )([sequence, mask])

    if variant.startswith("B2-"):
        x = tf.keras.layers.Flatten(name="mlp_flatten")(normalized)
        x = tf.keras.layers.Concatenate(name="mlp_mask_concat")([x, mask])
        x = tf.keras.layers.Dense(mlp_width, activation="gelu", name="mlp_dense_1")(x)
        x = tf.keras.layers.Dropout(dropout, name="mlp_dropout")(x)
        context = tf.keras.layers.Dense(mlp_width, activation="gelu", name="mlp_dense_2")(x)
    else:
        x = tf.keras.layers.Dense(transformer_width, name="token_projection")(normalized)
        x = AddLearnedPosition(6, transformer_width, name="position_embedding")(x)
        x = ApplyTokenMask(name="position_token_mask")([x, mask])
        attention_mask = PairwiseAttentionMask(name="pairwise_attention_mask")(mask)
        for index in range(transformer_layers):
            prefix = f"transformer_block_{index + 1}"
            attended = tf.keras.layers.MultiHeadAttention(
                num_heads=transformer_heads,
                key_dim=transformer_width // transformer_heads,
                dropout=dropout,
                name=f"{prefix}_self_attention",
            )(x, x, attention_mask=attention_mask)
            attended = tf.keras.layers.Dropout(
                dropout, name=f"{prefix}_attention_dropout"
            )(attended)
            x = tf.keras.layers.Add(name=f"{prefix}_attention_add")([x, attended])
            x = tf.keras.layers.LayerNormalization(
                epsilon=1.0e-6, name=f"{prefix}_attention_norm"
            )(x)
            fed = tf.keras.layers.Dense(
                transformer_ff_dim,
                activation="gelu",
                name=f"{prefix}_ff_expand",
            )(x)
            fed = tf.keras.layers.Dropout(
                dropout, name=f"{prefix}_ff_dropout"
            )(fed)
            fed = tf.keras.layers.Dense(
                transformer_width, name=f"{prefix}_ff_contract"
            )(fed)
            fed = tf.keras.layers.Dropout(
                dropout, name=f"{prefix}_residual_dropout"
            )(fed)
            x = tf.keras.layers.Add(name=f"{prefix}_output_add")([x, fed])
            x = tf.keras.layers.LayerNormalization(
                epsilon=1.0e-6, name=f"{prefix}_output_norm"
            )(x)
            x = ApplyTokenMask(name=f"{prefix}_token_mask")([x, mask])
        context = MaskedMeanPooling(name="masked_temporal_pool")([x, mask])

    zero = tf.keras.initializers.Zeros()
    mean_raw = tf.keras.layers.Dense(
        num_modes * num_timesteps * 2,
        kernel_initializer=zero,
        bias_initializer=zero,
        name="mean_residual_head",
    )(context)
    distributional = variant in ("B2-D", "T2")
    if distributional:
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
    else:
        std_raw = tf.keras.layers.Lambda(lambda value: value[:, :0], name="empty_std_head")(context)
        angle_raw = tf.keras.layers.Lambda(lambda value: value[:, :0], name="empty_angle_head")(context)
        logit_raw = tf.keras.layers.Lambda(lambda value: value[:, :0], name="empty_logit_head")(context)
    output = MultipathResidualMerge(
        num_modes,
        num_timesteps,
        distributional,
        name="structured_residual_merge",
    )([base_raw, mean_raw, std_raw, angle_raw, logit_raw])
    return tf.keras.Model(
        [image, past, sequence, mask],
        output,
        name=f"multipath_interaction_{variant.lower().replace('-', '_')}_v2",
    )


def masked_multipath_loss(anchors: np.ndarray, label_horizon: int = 10):
    anchors_tensor = tf.constant(np.asarray(anchors, dtype=np.float32))
    label_anchors = anchors_tensor[:, :label_horizon, :]
    num_modes, num_timesteps = int(anchors.shape[0]), int(anchors.shape[1])

    def loss(y_true, y_pred):
        xy_true = y_true[..., :2]
        valid = tf.cast(y_true[..., 2] > 0.0, y_pred.dtype)
        valid_count = tf.maximum(tf.reduce_sum(valid, axis=-1), 1.0)
        trajectories = tf.reshape(
            y_pred[:, :-num_modes], (-1, num_modes, num_timesteps, 5)
        )
        probabilities = tf.nn.softmax(y_pred[:, -num_modes:])
        anchor_distance = tf.norm(
            label_anchors[None, ...] - xy_true[:, None, :, :], axis=-1
        )
        anchor_distance = tf.reduce_sum(anchor_distance * valid[:, None, :], axis=-1) / valid_count[:, None]
        nearest_mode = tf.argmin(anchor_distance, axis=-1, output_type=tf.int32)
        indices = tf.stack([tf.range(tf.shape(y_pred)[0]), nearest_mode], axis=-1)
        class_loss = -tf.math.log(tf.maximum(tf.gather_nd(probabilities, indices), 1.0e-8))
        selected = tf.gather_nd(trajectories[:, :, :label_horizon, :], indices)
        predicted_xy = selected[..., :2] + tf.gather(label_anchors, nearest_mode)
        residual = xy_true - predicted_xy
        log_std = tf.clip_by_value(tf.abs(selected[..., 2:4]), 0.0, 5.0)
        std = tf.exp(log_std)
        theta = selected[..., 4]
        cosine, sine = tf.cos(theta), tf.sin(theta)
        dx, dy = residual[..., 0], residual[..., 1]
        maha = 0.5 * (
            tf.square(dx * cosine + dy * sine) / tf.square(std[..., 0])
            + tf.square(-dx * sine + dy * cosine) / tf.square(std[..., 1])
        )
        regression = tf.reduce_sum(
            (tf.reduce_sum(log_std, axis=-1) + maha) * valid, axis=-1
        ) / valid_count
        return tf.reduce_mean(class_loss + regression)

    loss.__name__ = "masked_multipath_nll"
    return loss


def masked_top_mode_ade(anchors: np.ndarray, label_horizon: int = 10):
    anchors_tensor = tf.constant(np.asarray(anchors, dtype=np.float32))
    num_modes, num_timesteps = int(anchors.shape[0]), int(anchors.shape[1])

    def metric(y_true, y_pred):
        valid = tf.cast(y_true[..., 2] > 0.0, y_pred.dtype)
        trajectories = tf.reshape(
            y_pred[:, :-num_modes], (-1, num_modes, num_timesteps, 5)
        )
        top_mode = tf.argmax(y_pred[:, -num_modes:], axis=-1, output_type=tf.int32)
        indices = tf.stack([tf.range(tf.shape(y_pred)[0]), top_mode], axis=-1)
        selected = tf.gather_nd(trajectories[:, :, :label_horizon, :2], indices)
        predicted = selected + tf.gather(anchors_tensor[:, :label_horizon, :], top_mode)
        errors = tf.norm(predicted - y_true[..., :2], axis=-1)
        return tf.reduce_sum(errors * valid) / tf.maximum(tf.reduce_sum(valid), 1.0)

    metric.__name__ = "masked_top_mode_ADE"
    return metric


def parameter_report(model: tf.keras.Model) -> Dict[str, int]:
    trainable = int(sum(np.prod(weight.shape) for weight in model.trainable_weights))
    total = int(model.count_params())
    return {"total_parameters": total, "trainable_parameters": trainable}
