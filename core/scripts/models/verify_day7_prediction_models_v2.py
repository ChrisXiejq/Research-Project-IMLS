#!/usr/bin/env python3
"""Day 7 gate: real-input equivalence plus synthetic overfit/save/load for B2/T1/T2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
import tensorflow as tf

from interaction_adapter_v2 import (
    VARIANTS,
    build_interaction_adapter,
    configure_v2_b1_head,
    load_normalization,
    masked_multipath_loss,
    masked_top_mode_ade,
    parameter_report,
)
from multipath_gmm_utils import audit_covariances, decode_multipath_raw
from prediction_dataset_utils import read_jsonl, resolve_raster_path
from prediction_input_contract import load_logged_raster, preprocess_resnet_raster


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged-dir", required=True)
    parser.add_argument("--base-model", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--completion-json", default=None)
    parser.add_argument("--seed", type=int, default=11)
    return parser.parse_args()


def local_masked_label(sample: dict, horizon: int) -> np.ndarray:
    result = np.zeros((horizon, 3), dtype=np.float32)
    rotation = np.asarray(sample["target_to_world_R"], dtype=np.float32)
    translation = np.asarray(sample["target_to_world_t"], dtype=np.float32)
    future = sample.get("future_xy_world") or []
    mask = sample.get("future_valid_mask") or []
    for index in range(min(horizon, len(mask), len(future))):
        if mask[index] and future[index] and future[index][0] is not None:
            result[index, :2] = (np.asarray(future[index], dtype=np.float32) - translation) @ rotation
            result[index, 2] = 1.0
    if not np.any(result[:, 2]):
        raise ValueError("Smoke sample has no valid future label")
    return result


def first_usable_sample(path: Path) -> dict:
    for sample in read_jsonl(str(path)):
        if any(sample.get("future_valid_mask") or []):
            return sample
    raise ValueError(f"No usable sample in {path}")


def synthetic_base(output_width: int) -> tf.keras.Model:
    image = tf.keras.Input((8, 8, 3), name="synthetic_image")
    state = tf.keras.Input((5, 4), name="synthetic_state")
    x = tf.keras.layers.Concatenate()(
        [tf.keras.layers.Flatten()(image), tf.keras.layers.Flatten()(state)]
    )
    output = tf.keras.layers.Dense(
        output_width,
        kernel_initializer="zeros",
        bias_initializer="zeros",
        trainable=False,
    )(x)
    return tf.keras.Model([image, state], output, name="synthetic_frozen_multipath")


def relative_difference(left: int, right: int) -> float:
    return abs(left - right) / max(left, right, 1)


def main() -> None:
    args = parse_args()
    np.random.seed(args.seed)
    tf.random.set_seed(args.seed)
    merged = Path(args.merged_dir).resolve()
    completion = json.loads((merged / "DAY7_COMPLETE.json").read_text())
    if completion.get("status") != "pass":
        raise ValueError("Day 7 merge/split gate has not passed")
    normalization = load_normalization(merged / "interaction_normalization_train.json")
    anchors = np.load(args.anchors).astype(np.float32)
    base = tf.keras.models.load_model(args.base_model, compile=False)
    sample = first_usable_sample(merged / "train.jsonl")
    raster_path = resolve_raster_path(sample)
    raster = load_logged_raster(raster_path)
    image = preprocess_resnet_raster(raster)
    past = np.asarray(sample["past_states_local"], dtype=np.float32)[None, ...]
    sequence = np.asarray(sample["interaction_sequence"], dtype=np.float32)[None, ...]
    mask = np.asarray(sample["interaction_sequence_mask"], dtype=np.float32)[None, ...]
    label = local_masked_label(sample, min(10, anchors.shape[1]))[None, ...]
    base_output = np.asarray(base.predict_on_batch([image, past]))

    report = {
        "status": "pass",
        "seed": args.seed,
        "real_sample": {
            "source_subrun": sample.get("source_subrun"),
            "valid_future_steps": int(np.sum(label[..., 2])),
            "raster_path": raster_path,
        },
        "variants": {},
        "parameter_matching": {},
    }
    b1_real_loss = float(masked_multipath_loss(anchors, label.shape[1])(label, base_output).numpy())
    if not math.isfinite(b1_real_loss):
        raise AssertionError("B1 real-sample loss is non-finite")
    tiny_b1 = configure_v2_b1_head(synthetic_base(int(base.output_shape[-1])))
    tiny_b1.compile(
        optimizer=tf.keras.optimizers.Adam(1.0e-3, clipnorm=10.0),
        loss=masked_multipath_loss(anchors, label.shape[1]),
        metrics=[masked_top_mode_ade(anchors, label.shape[1])],
    )
    b1_batch = 8
    b1_inputs = [
        np.zeros((b1_batch, 8, 8, 3), dtype=np.float32),
        np.zeros((b1_batch, 5, 4), dtype=np.float32),
    ]
    b1_label = np.zeros((b1_batch, label.shape[1], 3), dtype=np.float32)
    b1_label[..., :2] = anchors[0, : label.shape[1], :] + 0.5
    b1_label[..., 2] = 1.0
    b1_initial_loss = float(tiny_b1.evaluate(b1_inputs, b1_label, verbose=0)[0])
    for _ in range(20):
        tiny_b1.train_on_batch(b1_inputs, b1_label)
    b1_final_loss = float(tiny_b1.evaluate(b1_inputs, b1_label, verbose=0)[0])
    if not math.isfinite(b1_final_loss) or b1_final_loss >= b1_initial_loss:
        raise AssertionError(
            f"B1 synthetic overfit failed: initial={b1_initial_loss}, final={b1_final_loss}"
        )
    b1_output = np.asarray(tiny_b1.predict_on_batch(b1_inputs))
    with tempfile.TemporaryDirectory(prefix="day7_B1_") as temporary:
        save_path = os.path.join(temporary, "saved_model")
        tiny_b1.save(save_path)
        restored_b1 = tf.keras.models.load_model(save_path, compile=False)
        restored_b1_output = np.asarray(restored_b1.predict_on_batch(b1_inputs))
    b1_save_difference = float(np.max(np.abs(restored_b1_output - b1_output)))
    if b1_save_difference > 1.0e-5:
        raise AssertionError(f"B1 save/load difference {b1_save_difference}")
    report["variants"]["B1"] = {
        **parameter_report(tiny_b1),
        "real_sample_masked_loss": b1_real_loss,
        "synthetic_initial_loss": b1_initial_loss,
        "synthetic_final_loss": b1_final_loss,
        "save_load_max_abs_difference": b1_save_difference,
    }
    trainable_counts = {}
    output_width = int(base.output_shape[-1])
    for variant in VARIANTS:
        real_model = build_interaction_adapter(base, anchors, normalization, variant)
        real_output = np.asarray(real_model.predict_on_batch([image, past, sequence, mask]))
        initial_difference = float(np.max(np.abs(real_output - base_output)))
        if initial_difference > 1.0e-5:
            raise AssertionError(f"{variant} zero-init differs from base by {initial_difference}")
        params = parameter_report(real_model)
        trainable_counts[variant] = params["trainable_parameters"]
        real_loss = float(masked_multipath_loss(anchors, label.shape[1])(label, real_output).numpy())
        if not math.isfinite(real_loss):
            raise AssertionError(f"{variant} real-sample loss is non-finite")
        del real_model

        tiny_base = synthetic_base(output_width)
        model = build_interaction_adapter(tiny_base, anchors, normalization, variant)
        model.compile(
            optimizer=tf.keras.optimizers.Adam(1.0e-3, clipnorm=10.0),
            loss=masked_multipath_loss(anchors, label.shape[1]),
            metrics=[masked_top_mode_ade(anchors, label.shape[1])],
        )
        batch = 8
        synthetic_inputs = [
            np.zeros((batch, 8, 8, 3), dtype=np.float32),
            np.zeros((batch, 5, 4), dtype=np.float32),
            np.random.normal(size=(batch, 6, 12)).astype(np.float32),
            np.ones((batch, 6), dtype=np.float32),
        ]
        synthetic_label = np.zeros((batch, label.shape[1], 3), dtype=np.float32)
        synthetic_label[..., :2] = anchors[0, : label.shape[1], :] + 0.5
        synthetic_label[..., 2] = 1.0
        initial_loss = float(model.evaluate(synthetic_inputs, synthetic_label, verbose=0)[0])
        losses = []
        for _ in range(20):
            losses.append(float(model.train_on_batch(synthetic_inputs, synthetic_label)[0]))
        final_loss = float(model.evaluate(synthetic_inputs, synthetic_label, verbose=0)[0])
        if not math.isfinite(final_loss) or final_loss >= initial_loss:
            raise AssertionError(
                f"{variant} synthetic overfit failed: initial={initial_loss}, final={final_loss}"
            )
        synthetic_output = np.asarray(model.predict_on_batch(synthetic_inputs))
        decoded = decode_multipath_raw(synthetic_output[:1], anchors)
        covariance_audit = audit_covariances(decoded.covariances)
        if covariance_audit["invalid_matrices"] != 0:
            raise AssertionError(f"{variant} emitted invalid covariance")
        with tempfile.TemporaryDirectory(prefix=f"day7_{variant}_") as temporary:
            save_path = os.path.join(temporary, "saved_model")
            model.save(save_path)
            restored = tf.keras.models.load_model(save_path, compile=False)
            restored_output = np.asarray(restored.predict_on_batch(synthetic_inputs))
        save_load_difference = float(np.max(np.abs(restored_output - synthetic_output)))
        if save_load_difference > 1.0e-5:
            raise AssertionError(f"{variant} save/load difference {save_load_difference}")
        report["variants"][variant] = {
            **params,
            "zero_init_base_max_abs_difference": initial_difference,
            "real_sample_masked_loss": real_loss,
            "synthetic_initial_loss": initial_loss,
            "synthetic_final_loss": final_loss,
            "synthetic_min_train_loss": min(losses),
            "save_load_max_abs_difference": save_load_difference,
            "covariance_audit": covariance_audit,
        }
        tf.keras.backend.clear_session()

    for control, transformer in (("B2-M", "T1"), ("B2-D", "T2")):
        difference = relative_difference(trainable_counts[control], trainable_counts[transformer])
        report["parameter_matching"][f"{control}_vs_{transformer}"] = {
            "control_trainable": trainable_counts[control],
            "transformer_trainable": trainable_counts[transformer],
            "relative_difference": difference,
            "within_20_percent": difference <= 0.20,
        }
        if difference > 0.20:
            raise AssertionError(f"Parameter matching failed for {control} vs {transformer}: {difference}")

    output = Path(args.output_json).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    report_sha256 = hashlib.sha256(output.read_bytes()).hexdigest()
    completion_path = Path(
        args.completion_json or output.with_name("DAY7_MODEL_IMPLEMENTATION_COMPLETE.json")
    ).resolve()
    completion_payload = {
        "status": "pass",
        "variants": ["B1", *VARIANTS],
        "model_smoke_report": str(output),
        "model_smoke_report_sha256": report_sha256,
    }
    completion_temporary = completion_path.with_suffix(completion_path.suffix + ".tmp")
    completion_temporary.write_text(
        json.dumps(completion_payload, indent=2, sort_keys=True) + "\n"
    )
    os.replace(completion_temporary, completion_path)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
