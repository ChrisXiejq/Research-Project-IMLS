#!/usr/bin/env python3
"""Diagnose frozen-backbone cache drift without mutating formal artifacts."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import json
from pathlib import Path

import numpy as np
import tensorflow as tf

from build_thesis_core_feature_cache_v3 import _final_dense
from prediction_dataset_utils import read_jsonl, resolve_raster_path
from prepare_thesis_core_v3_dataset import load_thesis_normalization
from train_prediction_model_v3 import load_image
from train_thesis_core_cached_v3 import build_cached_model, reconstruct_full_model


def errors(left: np.ndarray, right: np.ndarray) -> dict[str, float]:
    difference = np.abs(np.asarray(left) - np.asarray(right))
    denominator = np.maximum(np.abs(np.asarray(left)), 1.0e-6)
    relative = difference / denominator
    return {
        "maximum_absolute_error": float(np.max(difference)),
        "mean_absolute_error": float(np.mean(difference)),
        "p99_absolute_error": float(np.quantile(difference, 0.99)),
        "maximum_relative_error": float(np.max(relative)),
        "allclose_1e-5": bool(np.allclose(left, right, rtol=1.0e-5, atol=1.0e-5)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-model", required=True, type=Path)
    parser.add_argument("--cache", required=True, type=Path)
    parser.add_argument("--selection-jsonl", required=True, type=Path)
    parser.add_argument("--count", type=int, default=32)
    parser.add_argument("--cached-weights", type=Path)
    parser.add_argument("--anchors", type=Path)
    parser.add_argument("--normalization", type=Path)
    args = parser.parse_args()

    with np.load(args.cache, allow_pickle=False) as handle:
        cached_raw = np.asarray(handle["base_raw"][: args.count])
        cached_features = np.asarray(handle["head_features"][: args.count])
        cached_sequence = np.asarray(handle["sequence"][: args.count])
        cached_mask = np.asarray(handle["mask"][: args.count])
    rows = list(read_jsonl(str(args.selection_jsonl)))[: args.count]
    images = np.stack(
        [load_image(np.asarray(str(resolve_raster_path(row)).encode("utf-8"))) for row in rows]
    )
    past = np.stack([np.asarray(row["past_states_local"], dtype=np.float32) for row in rows])

    models = []
    predictions = []
    features = []
    for _ in range(2):
        base = tf.keras.models.load_model(args.base_model, compile=False)
        final = _final_dense(base)
        extractor = tf.keras.Model(base.inputs, [base.output, final.input])
        raw, feature = extractor.predict_on_batch([images, past])
        models.append(base)
        predictions.append(np.asarray(raw))
        features.append(np.asarray(feature))

    report = {
        "schema_version": "capacity_history_cache_parity_diagnostic_v3",
        "samples": len(rows),
        "cached_vs_reload_1_raw": errors(cached_raw, predictions[0]),
        "cached_vs_reload_1_features": errors(cached_features, features[0]),
        "reload_1_vs_reload_2_raw": errors(predictions[0], predictions[1]),
        "reload_1_vs_reload_2_features": errors(features[0], features[1]),
    }
    if args.cached_weights:
        if not args.anchors or not args.normalization:
            raise ValueError("Adapter audit requires --anchors and --normalization")
        anchors = np.load(args.anchors)
        normalization = load_thesis_normalization(args.normalization)
        spec = {
            "family": "transformer",
            "capacity_tier": "large",
            "history_horizon_s": 1.0,
        }
        cached_arrays = {
            "base_raw": cached_raw,
            "head_features": cached_features,
        }
        cached_model, _ = build_cached_model(spec, models[0], cached_arrays, anchors, normalization)
        cached_model.load_weights(args.cached_weights)
        full = reconstruct_full_model(spec, args.base_model, anchors, normalization, cached_model)
        cached_output = cached_model.predict_on_batch(
            (cached_raw, cached_sequence, cached_mask)
        )
        full_output = full.predict_on_batch(
            [images, past, cached_sequence, cached_mask]
        )
        report["adapter_cached_vs_full"] = errors(cached_output, full_output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    tf.keras.utils.set_random_seed(20260822)
    tf.config.experimental.enable_op_determinism()
    main()
