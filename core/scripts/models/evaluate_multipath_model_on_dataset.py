#!/usr/bin/env python3
"""Run a MultiPath SavedModel on a fixed CARLA split and evaluate predictions."""

import argparse
import json
import math
import os
import sys

import numpy as np
import tensorflow as tf
from tensorflow.keras.applications.resnet import preprocess_input

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(SCRIPT_DIR)
from prediction_dataset_utils import (
    finite_or_none,
    has_full_horizon,
    interaction_context_from_sample,
    mean,
    percentile,
    read_jsonl,
    resolve_raster_path,
    world_future_to_local,
)


def parse_args():
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
    return parser.parse_args()


def load_samples(jsonl_path, result_dir, horizon, max_samples=None, no_image=False):
    count = 0
    for sample in read_jsonl(jsonl_path):
        if not has_full_horizon(sample, horizon=horizon):
            continue
        raster_path = resolve_raster_path(sample, result_dir=result_dir)
        if not raster_path or not os.path.exists(raster_path):
            continue
        past = np.asarray(sample["past_states_local"], dtype=np.float32)
        future_local = world_future_to_local(sample, horizon=horizon).astype(np.float32)
        yield sample, raster_path, past, future_local
        count += 1
        if max_samples is not None and count >= max_samples:
            return


def make_batch(batch, no_image=False):
    images = []
    past_states = []
    interaction_contexts = []
    labels = []
    samples = []
    for sample, raster_path, past, future_local in batch:
        if no_image:
            image = np.zeros((500, 500, 3), dtype=np.float32)
        else:
            raw = tf.io.read_file(raster_path)
            image = tf.image.decode_png(raw, channels=3)
            image = tf.image.resize(image, (500, 500), method="bilinear")
            image = preprocess_input(tf.cast(image, tf.float32)).numpy()
        images.append(image)
        past_states.append(past)
        interaction_contexts.append(interaction_context_from_sample(sample))
        labels.append(future_local)
        samples.append(sample)
    return (
        samples,
        np.asarray(images, dtype=np.float32),
        np.asarray(past_states, dtype=np.float32),
        np.asarray(interaction_contexts, dtype=np.float32),
        np.asarray(labels, dtype=np.float32),
    )


def raw_to_modes(raw_pred, anchors, label_horizon):
    num_anchors, model_horizon, _ = anchors.shape
    trajectories = raw_pred[:, :-num_anchors].reshape((-1, num_anchors, model_horizon, 5))
    logits = raw_pred[:, -num_anchors:]
    probs = tf.nn.softmax(logits, axis=-1).numpy()
    mus = (
        trajectories[:, :, :label_horizon, :2]
        + anchors[None, :, :label_horizon, :]
    )
    return probs, mus


def evaluate(args):
    merged_dir = os.path.abspath(args.merged_dir)
    result_dir = os.path.abspath(os.path.join(merged_dir, os.pardir))
    jsonl_path = os.path.join(merged_dir, f"{args.split}.jsonl")
    anchors = np.load(args.anchors).astype(np.float32)
    if anchors.shape[1] < args.horizon:
        raise ValueError(f"Anchor horizon {anchors.shape[1]} is shorter than --horizon {args.horizon}")
    if anchors.shape[1] != args.horizon:
        print(f"Evaluating first {args.horizon} steps of {anchors.shape[1]}-step model output.")

    model = tf.keras.models.load_model(args.model, compile=False)
    uses_interaction_context = len(getattr(model, "inputs", [])) >= 3
    top_ade = []
    min_ade = []
    top_fde = []
    min_fde = []
    best_probs = []
    top_probs = []
    entropies = []
    top_is_best = 0
    mode_counts = [0 for _ in range(anchors.shape[0])]
    total = 0

    iterator = load_samples(jsonl_path, result_dir, args.horizon, max_samples=args.max_samples, no_image=args.no_image)
    batch = []
    for item in iterator:
        batch.append(item)
        if len(batch) < args.batch_size:
            continue
        samples, images, past_states, interaction_contexts, labels = make_batch(batch, no_image=args.no_image)
        model_inputs = [images, past_states, interaction_contexts] if uses_interaction_context else [images, past_states]
        pred = model.predict_on_batch(model_inputs)
        probs, mus = raw_to_modes(pred, anchors, args.horizon)
        for b in range(len(samples)):
            mode_ade = np.mean(np.linalg.norm(mus[b] - labels[b][None, :, :], axis=-1), axis=-1)
            mode_fde = np.linalg.norm(mus[b, :, -1, :] - labels[b, -1, :][None, :], axis=-1)
            best = int(np.argmin(mode_ade))
            top = int(np.argmax(probs[b]))
            mode_counts[best] += 1
            top_is_best += int(best == top)
            top_ade.append(float(mode_ade[top]))
            min_ade.append(float(mode_ade[best]))
            top_fde.append(float(mode_fde[top]))
            min_fde.append(float(mode_fde[best]))
            best_probs.append(float(probs[b, best]))
            top_probs.append(float(probs[b, top]))
            entropies.append(float(-np.sum(probs[b] * np.log(np.maximum(probs[b], 1.0e-12)))))
            total += 1
        batch = []
    if batch:
        samples, images, past_states, interaction_contexts, labels = make_batch(batch, no_image=args.no_image)
        model_inputs = [images, past_states, interaction_contexts] if uses_interaction_context else [images, past_states]
        pred = model.predict_on_batch(model_inputs)
        probs, mus = raw_to_modes(pred, anchors, args.horizon)
        for b in range(len(samples)):
            mode_ade = np.mean(np.linalg.norm(mus[b] - labels[b][None, :, :], axis=-1), axis=-1)
            mode_fde = np.linalg.norm(mus[b, :, -1, :] - labels[b, -1, :][None, :], axis=-1)
            best = int(np.argmin(mode_ade))
            top = int(np.argmax(probs[b]))
            mode_counts[best] += 1
            top_is_best += int(best == top)
            top_ade.append(float(mode_ade[top]))
            min_ade.append(float(mode_ade[best]))
            top_fde.append(float(mode_fde[top]))
            min_fde.append(float(mode_fde[best]))
            best_probs.append(float(probs[b, best]))
            top_probs.append(float(probs[b, top]))
            entropies.append(float(-np.sum(probs[b] * np.log(np.maximum(probs[b], 1.0e-12)))))
            total += 1

    return {
        "model": os.path.abspath(args.model),
        "split": args.split,
        "uses_interaction_context": bool(uses_interaction_context),
        "samples": total,
        "top1_ADE_mean": finite_or_none(mean(top_ade)),
        "minADE_mean": finite_or_none(mean(min_ade)),
        "top1_FDE_mean": finite_or_none(mean(top_fde)),
        "minFDE_mean": finite_or_none(mean(min_fde)),
        "minADE_p50": finite_or_none(percentile(min_ade, 50)),
        "minADE_p90": finite_or_none(percentile(min_ade, 90)),
        "minFDE_p50": finite_or_none(percentile(min_fde, 50)),
        "minFDE_p90": finite_or_none(percentile(min_fde, 90)),
        "top_prob_mode_is_best_frac": finite_or_none(top_is_best / total if total else float("nan")),
        "mean_probability_assigned_to_best_mode": finite_or_none(mean(best_probs)),
        "mean_top_mode_probability": finite_or_none(mean(top_probs)),
        "mean_mode_entropy": finite_or_none(mean(entropies)),
        "best_mode_counts": mode_counts,
    }


def main():
    args = parse_args()
    metrics = evaluate(args)
    output_json = args.output_json or os.path.join(
        os.path.abspath(args.merged_dir),
        f"model_metrics_{args.split}_{os.path.basename(os.path.abspath(args.model))}.json",
    )
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
