#!/usr/bin/env python3
"""Fine-tune the deployed MultiPath model on CARLA prediction logs.

This script intentionally keeps the deployed model interface unchanged:
  input  = [raster image, past_states]
  output = K * (T * 5) trajectory parameters followed by K mode logits

The default mode freezes all layers except the final prediction head.  This is
the shortest low-risk path for dissertation model-side work because it adapts
mode probabilities and trajectory offsets without replacing the planner-facing
model contract.
"""

import argparse
import json
import math
import os
import random
import sys
from typing import Dict, Iterator, Tuple

import numpy as np
import tensorflow as tf
from tensorflow.keras.applications.resnet import preprocess_input

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)
from prediction_dataset_utils import has_full_horizon, read_jsonl, resolve_raster_path, world_future_to_local


def parse_args():
    repo_root = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir, os.pardir))
    parser = argparse.ArgumentParser()
    parser.add_argument("--merged_dir", required=True, help="Directory containing fixed train/val/test JSONL files.")
    parser.add_argument("--base_model", default=os.path.join(SCRIPT_DIR, "l5kit_multipath_10"),
                        help="Existing deployed SavedModel directory.")
    parser.add_argument("--anchors", default=os.path.join(SCRIPT_DIR, "l5kit_clusters_16.npy"))
    parser.add_argument("--output_model", default=os.path.join(SCRIPT_DIR, "l5kit_multipath_10_carla_finetuned"))
    parser.add_argument("--history_json", default=None)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--learning_rate", type=float, default=1.0e-4)
    parser.add_argument("--horizon", type=int, default=10)
    parser.add_argument("--shuffle_buffer", type=int, default=512)
    parser.add_argument("--freeze", choices=["head", "none"], default="head",
                        help="'head' trains only the final Dense layer; 'none' fine-tunes the whole model.")
    parser.add_argument("--max_train_samples", type=int, default=None)
    parser.add_argument("--max_val_samples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--no_image", action="store_true",
                        help="Use zero raster images while keeping the same model input shape.")
    return parser.parse_args()


def sample_generator(jsonl_path: str, result_dir: str, horizon: int, max_samples: int = None,
                     no_image: bool = False) -> Iterator[Tuple[bytes, np.ndarray, np.ndarray]]:
    emitted = 0
    for sample in read_jsonl(jsonl_path):
        if not has_full_horizon(sample, horizon=horizon):
            continue
        raster_path = resolve_raster_path(sample, result_dir=result_dir)
        if not raster_path or not os.path.exists(raster_path):
            continue
        past_states = np.asarray(sample["past_states_local"], dtype=np.float32)
        future_local = world_future_to_local(sample, horizon=horizon).astype(np.float32)
        if no_image:
            raster_path = b""
        else:
            raster_path = raster_path.encode("utf-8")
        yield raster_path, past_states, future_local
        emitted += 1
        if max_samples is not None and emitted >= max_samples:
            return


def count_usable_samples(jsonl_path: str, result_dir: str, horizon: int, max_samples: int = None) -> int:
    count = 0
    for sample in read_jsonl(jsonl_path):
        if not has_full_horizon(sample, horizon=horizon):
            continue
        raster_path = resolve_raster_path(sample, result_dir=result_dir)
        if not raster_path or not os.path.exists(raster_path):
            continue
        count += 1
        if max_samples is not None and count >= max_samples:
            break
    return count


def make_dataset(jsonl_path: str, result_dir: str, horizon: int, batch_size: int,
                 shuffle: bool, shuffle_buffer: int, max_samples: int = None,
                 no_image: bool = False) -> tf.data.Dataset:
    output_signature = (
        tf.TensorSpec(shape=(), dtype=tf.string),
        tf.TensorSpec(shape=(None, 4), dtype=tf.float32),
        tf.TensorSpec(shape=(horizon, 2), dtype=tf.float32),
    )

    dataset = tf.data.Dataset.from_generator(
        lambda: sample_generator(jsonl_path, result_dir, horizon, max_samples=max_samples, no_image=no_image),
        output_signature=output_signature,
    )

    def load_inputs(raster_path, past_states, future_local):
        if no_image:
            image = tf.zeros((500, 500, 3), dtype=tf.float32)
        else:
            raw = tf.io.read_file(raster_path)
            image = tf.image.decode_png(raw, channels=3)
            image = tf.image.resize(image, (500, 500), method="bilinear")
            image = tf.cast(image, tf.float32)
            image = preprocess_input(image)
        return (image, past_states), future_local

    dataset = dataset.map(load_inputs, num_parallel_calls=tf.data.AUTOTUNE)
    if shuffle:
        dataset = dataset.shuffle(shuffle_buffer, reshuffle_each_iteration=True)
    dataset = dataset.batch(batch_size, drop_remainder=False)
    dataset = dataset.prefetch(tf.data.AUTOTUNE)
    return dataset


def multipath_loss(anchors_np: np.ndarray, label_horizon: int):
    anchors = tf.constant(anchors_np, dtype=tf.float32)
    label_anchors = tf.constant(anchors_np[:, :label_horizon, :], dtype=tf.float32)
    num_anchors = int(anchors_np.shape[0])
    num_timesteps = int(anchors_np.shape[1])

    def loss(y_true, y_pred):
        batch_size = tf.shape(y_true)[0]
        trajectories = tf.reshape(
            y_pred[:, :-num_anchors],
            (batch_size, num_anchors, num_timesteps, 5),
        )
        anchor_probs = tf.nn.softmax(y_pred[:, -num_anchors:])

        distance_to_anchors = tf.reduce_sum(
            tf.norm(label_anchors[None, :, :, :] - y_true[:, None, :, :], axis=-1),
            axis=-1,
        )
        nearest_mode = tf.argmin(distance_to_anchors, axis=-1, output_type=tf.int32)
        batch_indices = tf.range(batch_size, dtype=tf.int32)
        nearest_indices = tf.stack([batch_indices, nearest_mode], axis=-1)

        selected_probs = tf.gather_nd(anchor_probs, nearest_indices)
        class_loss = -tf.math.log(tf.maximum(selected_probs, 1.0e-8))

        trajectories_label = trajectories[:, :, :label_horizon, :]
        trajectories_xy = trajectories_label[:, :, :, :2] + label_anchors[None, :, :, :]
        selected_trajs = tf.gather_nd(trajectories_xy, nearest_indices)
        residual = y_true - selected_trajs
        dx = residual[:, :, 0]
        dy = residual[:, :, 1]

        selected_params = tf.gather_nd(trajectories_label, nearest_indices)
        log_std1 = tf.clip_by_value(tf.abs(selected_params[:, :, 2]), 0.0, 5.0)
        log_std2 = tf.clip_by_value(tf.abs(selected_params[:, :, 3]), 0.0, 5.0)
        std1 = tf.exp(log_std1)
        std2 = tf.exp(log_std2)
        theta = selected_params[:, :, 4]
        cos_th = tf.cos(theta)
        sin_th = tf.sin(theta)

        reg_log_det = tf.reduce_sum(log_std1 + log_std2, axis=-1)
        reg_maha = tf.reduce_sum(
            0.5 * (
                tf.square(dx * cos_th + dy * sin_th) / tf.square(std1)
                + tf.square(-dx * sin_th + dy * cos_th) / tf.square(std2)
            ),
            axis=-1,
        )
        return tf.reduce_mean(class_loss + reg_log_det + reg_maha)

    return loss


def top_mode_ade_metric(anchors_np: np.ndarray, label_horizon: int):
    anchors = tf.constant(anchors_np, dtype=tf.float32)
    label_anchors = tf.constant(anchors_np[:, :label_horizon, :], dtype=tf.float32)
    num_anchors = int(anchors_np.shape[0])
    num_timesteps = int(anchors_np.shape[1])

    def metric(y_true, y_pred):
        batch_size = tf.shape(y_true)[0]
        trajectories = tf.reshape(
            y_pred[:, :-num_anchors],
            (batch_size, num_anchors, num_timesteps, 5),
        )
        anchor_probs = tf.nn.softmax(y_pred[:, -num_anchors:])
        top_mode = tf.argmax(anchor_probs, axis=-1, output_type=tf.int32)
        top_indices = tf.stack([tf.range(batch_size, dtype=tf.int32), top_mode], axis=-1)
        trajectories_label = trajectories[:, :, :label_horizon, :]
        trajectories_xy = trajectories_label[:, :, :, :2] + label_anchors[None, :, :, :]
        top_trajs = tf.gather_nd(trajectories_xy, top_indices)
        return tf.reduce_mean(tf.norm(top_trajs - y_true, axis=-1))

    metric.__name__ = "top_mode_ADE"
    return metric


def set_trainable_layers(model: tf.keras.Model, freeze: str) -> Dict:
    if freeze == "none":
        for layer in model.layers:
            layer.trainable = True
        return {"freeze": "none", "trainable_layers": [layer.name for layer in model.layers if layer.trainable]}

    for layer in model.layers:
        layer.trainable = False

    trainable = []
    for layer in reversed(model.layers):
        if isinstance(layer, tf.keras.layers.Dense):
            layer.trainable = True
            trainable.append(layer.name)
            break
    if not trainable:
        model.layers[-1].trainable = True
        trainable.append(model.layers[-1].name)
    return {"freeze": "head", "trainable_layers": list(reversed(trainable))}


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
    if anchors.shape[1] < args.horizon:
        raise ValueError(f"Anchor horizon {anchors.shape[1]} is shorter than --horizon {args.horizon}")
    if anchors.shape[1] != args.horizon:
        print(
            f"Using first {args.horizon} steps of {anchors.shape[1]}-step model output for CARLA labels."
        )

    train_count = count_usable_samples(train_jsonl, result_dir, args.horizon, args.max_train_samples)
    val_count = count_usable_samples(val_jsonl, result_dir, args.horizon, args.max_val_samples)
    if train_count == 0 or val_count == 0:
        raise ValueError(f"No usable samples: train={train_count}, val={val_count}")

    print(f"Loading base model: {args.base_model}")
    model = tf.keras.models.load_model(args.base_model, compile=False)
    trainable_info = set_trainable_layers(model, args.freeze)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=args.learning_rate, clipnorm=10.0),
        loss=multipath_loss(anchors, args.horizon),
        metrics=[top_mode_ade_metric(anchors, args.horizon)],
    )
    model.summary()

    train_ds = make_dataset(
        train_jsonl, result_dir, args.horizon, args.batch_size,
        shuffle=True, shuffle_buffer=args.shuffle_buffer,
        max_samples=args.max_train_samples, no_image=args.no_image,
    )
    val_ds = make_dataset(
        val_jsonl, result_dir, args.horizon, args.batch_size,
        shuffle=False, shuffle_buffer=args.shuffle_buffer,
        max_samples=args.max_val_samples, no_image=args.no_image,
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

    history = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=args.epochs,
        callbacks=callbacks,
    )

    print(f"Saving final model: {output_model}")
    model.save(output_model)
    metadata = {
        "merged_dir": merged_dir,
        "base_model": os.path.abspath(args.base_model),
        "anchors": os.path.abspath(args.anchors),
        "output_model": output_model,
        "best_model": checkpoint_path,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "horizon": args.horizon,
        "freeze": args.freeze,
        "trainable_info": trainable_info,
        "train_count_full_horizon": train_count,
        "val_count_full_horizon": val_count,
        "history": {k: [float(x) for x in values] for k, values in history.history.items()},
    }
    history_json = args.history_json or output_model + "_history.json"
    with open(history_json, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
