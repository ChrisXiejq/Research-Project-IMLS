#!/usr/bin/env python3
"""Train an interaction-aware Transformer adapter on top of CARLA MultiPath.

The adapter keeps the deployed MultiPath output contract unchanged:
  output = K * (T * 5) trajectory parameters followed by K mode logits

It adds one new model input, ``interaction_context``.  The base MultiPath model
can be frozen, and the Transformer branch learns a residual correction from
target history plus ego-target interaction features.  This makes the model-side
ablation low-risk: old two-input MultiPath models still run unchanged, while
the new three-input model can be evaluated with the same SMPC planner.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from typing import Iterator, Tuple

import numpy as np
import tensorflow as tf
from tensorflow.keras.applications.resnet import preprocess_input

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)
from finetune_multipath_carla import multipath_loss, top_mode_ade_metric
from prediction_dataset_utils import (
    has_full_horizon,
    interaction_context_from_sample,
    read_jsonl,
    resolve_raster_path,
    world_future_to_local,
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged_dir", required=True, help="Directory containing train/val/test JSONL files.")
    parser.add_argument("--base_model", default=os.path.join(SCRIPT_DIR, "l5kit_multipath_10_carla_finetuned_head_best"))
    parser.add_argument("--anchors", default=os.path.join(SCRIPT_DIR, "l5kit_clusters_16.npy"))
    parser.add_argument("--output_model", default=os.path.join(SCRIPT_DIR, "l5kit_multipath_10_carla_interaction_transformer"))
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--learning_rate", type=float, default=5.0e-5)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--context_dim", type=int, default=8)
    parser.add_argument("--d_model", type=int, default=64)
    parser.add_argument("--num_heads", type=int, default=4)
    parser.add_argument("--ff_dim", type=int, default=128)
    parser.add_argument("--num_layers", type=int, default=2)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--delta_scale", type=float, default=0.15)
    parser.add_argument("--freeze_base", choices=["true", "false"], default="true")
    parser.add_argument("--max_train_samples", type=int, default=None)
    parser.add_argument("--max_val_samples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=11)
    parser.add_argument("--no_image", action="store_true")
    return parser.parse_args()


def sample_generator(
    jsonl_path: str,
    result_dir: str,
    horizon: int,
    max_samples: int | None = None,
    no_image: bool = False,
) -> Iterator[Tuple[bytes, np.ndarray, np.ndarray, np.ndarray]]:
    emitted = 0
    for sample in read_jsonl(jsonl_path):
        if not has_full_horizon(sample, horizon=horizon):
            continue
        raster_path = resolve_raster_path(sample, result_dir=result_dir)
        if not no_image and (not raster_path or not os.path.exists(raster_path)):
            continue
        past_states = np.asarray(sample["past_states_local"], dtype=np.float32)
        context = interaction_context_from_sample(sample).astype(np.float32)
        future_local = world_future_to_local(sample, horizon=horizon).astype(np.float32)
        yield (b"" if no_image else raster_path.encode("utf-8")), past_states, context, future_local
        emitted += 1
        if max_samples is not None and emitted >= max_samples:
            return


def count_usable_samples(jsonl_path: str, result_dir: str, horizon: int, max_samples: int | None, no_image: bool) -> int:
    count = 0
    for sample in read_jsonl(jsonl_path):
        if not has_full_horizon(sample, horizon=horizon):
            continue
        raster_path = resolve_raster_path(sample, result_dir=result_dir)
        if not no_image and (not raster_path or not os.path.exists(raster_path)):
            continue
        count += 1
        if max_samples is not None and count >= max_samples:
            return count
    return count


def make_dataset(
    jsonl_path: str,
    result_dir: str,
    horizon: int,
    context_dim: int,
    batch_size: int,
    shuffle: bool,
    max_samples: int | None,
    no_image: bool,
) -> tf.data.Dataset:
    output_signature = (
        tf.TensorSpec(shape=(), dtype=tf.string),
        tf.TensorSpec(shape=(None, 4), dtype=tf.float32),
        tf.TensorSpec(shape=(context_dim,), dtype=tf.float32),
        tf.TensorSpec(shape=(horizon, 2), dtype=tf.float32),
    )

    dataset = tf.data.Dataset.from_generator(
        lambda: sample_generator(jsonl_path, result_dir, horizon, max_samples=max_samples, no_image=no_image),
        output_signature=output_signature,
    )

    def load_inputs(raster_path, past_states, context, future_local):
        if no_image:
            image = tf.zeros((500, 500, 3), dtype=tf.float32)
        else:
            raw = tf.io.read_file(raster_path)
            image = tf.image.decode_png(raw, channels=3)
            image = tf.image.resize(image, (500, 500), method="bilinear")
            image = preprocess_input(tf.cast(image, tf.float32))
        return (image, past_states, context), future_local

    dataset = dataset.map(load_inputs, num_parallel_calls=tf.data.AUTOTUNE)
    if shuffle:
        dataset = dataset.shuffle(512, reshuffle_each_iteration=True)
    return dataset.batch(batch_size, drop_remainder=False).prefetch(tf.data.AUTOTUNE)


def transformer_block(x, num_heads: int, ff_dim: int, dropout: float, name: str):
    attn = tf.keras.layers.MultiHeadAttention(
        num_heads=num_heads,
        key_dim=max(1, int(x.shape[-1]) // num_heads),
        dropout=dropout,
        name=f"{name}_mha",
    )(x, x)
    x = tf.keras.layers.LayerNormalization(name=f"{name}_attn_norm")(x + attn)
    ff = tf.keras.layers.Dense(ff_dim, activation="gelu", name=f"{name}_ff1")(x)
    ff = tf.keras.layers.Dropout(dropout, name=f"{name}_drop")(ff)
    ff = tf.keras.layers.Dense(int(x.shape[-1]), name=f"{name}_ff2")(ff)
    return tf.keras.layers.LayerNormalization(name=f"{name}_ff_norm")(x + ff)


def build_interaction_adapter_model(args, raw_output_dim: int) -> tf.keras.Model:
    base_model = tf.keras.models.load_model(args.base_model, compile=False)
    if args.freeze_base == "true":
        base_model.trainable = False

    image_input = tf.keras.Input(shape=(500, 500, 3), dtype=tf.float32, name="image")
    past_input = tf.keras.Input(shape=(None, 4), dtype=tf.float32, name="past_states")
    context_input = tf.keras.Input(shape=(args.context_dim,), dtype=tf.float32, name="interaction_context")

    base_pred = base_model([image_input, past_input])
    context_tokens = tf.keras.layers.Lambda(
        lambda z: tf.repeat(tf.expand_dims(z[1], axis=1), tf.shape(z[0])[1], axis=1),
        name="repeat_interaction_context",
    )([past_input, context_input])
    tokens = tf.keras.layers.Concatenate(axis=-1, name="history_context_tokens")([past_input, context_tokens])
    x = tf.keras.layers.Dense(args.d_model, activation="gelu", name="interaction_token_projection")(tokens)
    for idx in range(args.num_layers):
        x = transformer_block(x, args.num_heads, args.ff_dim, args.dropout, name=f"interaction_transformer_{idx}")
    pooled = tf.keras.layers.GlobalAveragePooling1D(name="interaction_pool")(x)
    pooled = tf.keras.layers.Concatenate(name="interaction_head_input")([pooled, context_input])
    pooled = tf.keras.layers.Dense(args.ff_dim, activation="gelu", name="interaction_head_dense")(pooled)
    delta = tf.keras.layers.Dense(raw_output_dim, name="interaction_residual")(pooled)
    delta = tf.keras.layers.Rescaling(
        scale=float(args.delta_scale),
        offset=0.0,
        name="scaled_interaction_residual",
    )(delta)
    output = tf.keras.layers.Add(name="interaction_adapted_multipath_output")([base_pred, delta])
    return tf.keras.Model([image_input, past_input, context_input], output, name="InteractionTransformerMultiPath")


def main():
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)
    tf.random.set_seed(args.seed)

    merged_dir = os.path.abspath(args.merged_dir)
    result_dir = os.path.abspath(os.path.join(merged_dir, os.pardir))
    train_jsonl = os.path.join(merged_dir, "train.jsonl")
    val_jsonl = os.path.join(merged_dir, "val.jsonl")
    if not os.path.exists(train_jsonl) or not os.path.exists(val_jsonl):
        raise FileNotFoundError("Expected train.jsonl and val.jsonl under merged_dir")

    anchors = np.load(args.anchors).astype(np.float32)
    probe_model = tf.keras.models.load_model(args.base_model, compile=False)
    raw_output_dim = int(probe_model.output_shape[-1])
    del probe_model

    train_count = count_usable_samples(train_jsonl, result_dir, args.horizon, args.max_train_samples, args.no_image)
    val_count = count_usable_samples(val_jsonl, result_dir, args.horizon, args.max_val_samples, args.no_image)
    if train_count == 0 or val_count == 0:
        raise ValueError(f"No usable samples: train={train_count}, val={val_count}")

    model = build_interaction_adapter_model(args, raw_output_dim=raw_output_dim)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=args.learning_rate, clipnorm=10.0),
        loss=multipath_loss(anchors, args.horizon),
        metrics=[top_mode_ade_metric(anchors, args.horizon)],
    )
    model.summary()

    train_ds = make_dataset(
        train_jsonl, result_dir, args.horizon, args.context_dim, args.batch_size,
        shuffle=True, max_samples=args.max_train_samples, no_image=args.no_image,
    )
    val_ds = make_dataset(
        val_jsonl, result_dir, args.horizon, args.context_dim, args.batch_size,
        shuffle=False, max_samples=args.max_val_samples, no_image=args.no_image,
    )

    output_model = os.path.abspath(args.output_model)
    os.makedirs(os.path.dirname(output_model), exist_ok=True)
    checkpoint_path = output_model + "_best"
    callbacks = [
        tf.keras.callbacks.ModelCheckpoint(
            checkpoint_path,
            monitor="val_top_mode_ADE",
            mode="min",
            save_best_only=True,
            save_weights_only=False,
        ),
        tf.keras.callbacks.CSVLogger(output_model + "_training_log.csv"),
    ]
    history = model.fit(train_ds, validation_data=val_ds, epochs=args.epochs, callbacks=callbacks)
    model.save(output_model)

    metadata = {
        "model_family": "interaction_transformer_multipath_residual_adapter",
        "merged_dir": merged_dir,
        "base_model": os.path.abspath(args.base_model),
        "anchors": os.path.abspath(args.anchors),
        "output_model": output_model,
        "best_model": checkpoint_path,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "horizon": args.horizon,
        "context_dim": args.context_dim,
        "d_model": args.d_model,
        "num_heads": args.num_heads,
        "ff_dim": args.ff_dim,
        "num_layers": args.num_layers,
        "delta_scale": args.delta_scale,
        "freeze_base": args.freeze_base,
        "train_count_full_horizon": train_count,
        "val_count_full_horizon": val_count,
        "history": {k: [float(x) for x in values] for k, values in history.history.items()},
    }
    with open(output_model + "_history.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
