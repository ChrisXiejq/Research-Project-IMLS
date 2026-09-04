#!/usr/bin/env python3
"""Verify that offline and deployment wrappers decode one raw output equally."""

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

from deploy_multipath_model import DeployMultiPath
from evaluate_multipath_model_on_dataset import decode_raw_predictions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--seed", type=int, default=20260731)
    return parser.parse_args()


def compare_case(
    raw: np.ndarray,
    anchors: np.ndarray,
    temperature: float,
    covariance_scale: float,
) -> dict:
    offline = decode_raw_predictions(
        raw,
        anchors,
        temperature=temperature,
        covariance_scale=covariance_scale,
    )
    deployment = DeployMultiPath.__new__(DeployMultiPath)
    deployment.anchors = anchors
    deployment.num_anchors = anchors.shape[0]
    deployment.num_timesteps = anchors.shape[1]
    deployment.calibration = {
        "temperature": temperature,
        "covariance_scale": covariance_scale,
    }
    online = deployment._make_gmm(raw)

    probability_difference = float(
        np.max(np.abs(offline.probabilities[0] - online.mode_probabilities))
    )
    mean_difference = float(np.max(np.abs(offline.means[0] - online.mus)))
    covariance_difference = float(
        np.max(np.abs(offline.covariances[0] - online.sigmas))
    )
    reference_differences = None
    if temperature == 1.0 and covariance_scale == 1.0:
        entry = tf.convert_to_tensor(raw[0])
        num_modes, num_timesteps, _ = anchors.shape
        trajectory = tf.reshape(
            entry[:-num_modes], (num_modes, num_timesteps, 5)
        )
        reference_probabilities = tf.nn.softmax(entry[-num_modes:]).numpy()
        reference_means = []
        reference_covariances = []
        for mode_index in range(num_modes):
            reference_means.append(
                trajectory[mode_index, :, :2].numpy() + anchors[mode_index]
            )
            std_1 = tf.math.exp(tf.math.abs(trajectory[mode_index, :, 2])).numpy()
            std_2 = tf.math.exp(tf.math.abs(trajectory[mode_index, :, 3])).numpy()
            cosine = tf.math.cos(trajectory[mode_index, :, 4]).numpy()
            sine = tf.math.sin(trajectory[mode_index, :, 4]).numpy()
            mode_covariances = []
            for axis_1, axis_2, cos_value, sin_value in zip(
                std_1, std_2, cosine, sine
            ):
                rotation = np.asarray(
                    [[cos_value, -sin_value], [sin_value, cos_value]]
                )
                diagonal = np.diag([axis_1**2, axis_2**2])
                mode_covariances.append(rotation @ diagonal @ rotation.T)
            reference_covariances.append(mode_covariances)
        reference_means = np.asarray(reference_means)
        reference_covariances = np.asarray(reference_covariances)
        reference_differences = {
            "max_abs_probability_difference": float(
                np.max(
                    np.abs(
                        offline.probabilities[0] - reference_probabilities
                    )
                )
            ),
            "max_abs_mean_difference": float(
                np.max(np.abs(offline.means[0] - reference_means))
            ),
            "max_abs_covariance_difference": float(
                np.max(
                    np.abs(
                        offline.covariances[0] - reference_covariances
                    )
                )
            ),
        }
    passed = (
        probability_difference <= 1.0e-7
        and mean_difference <= 1.0e-7
        and covariance_difference <= 1.0e-6
        and (
            reference_differences is None
            or (
                reference_differences["max_abs_probability_difference"] <= 1.0e-7
                and reference_differences["max_abs_mean_difference"] <= 1.0e-7
                and reference_differences["max_abs_covariance_difference"] <= 1.0e-5
            )
        )
    )
    return {
        "status": "pass" if passed else "fail",
        "temperature": temperature,
        "covariance_scale": covariance_scale,
        "max_abs_probability_difference": probability_difference,
        "max_abs_mean_difference": mean_difference,
        "max_abs_covariance_difference": covariance_difference,
        "historical_tensorflow_reference": reference_differences,
    }


def main() -> int:
    args = parse_args()
    anchors = np.load(args.anchors).astype(np.float32)
    rng = np.random.default_rng(args.seed)
    output_width = anchors.shape[0] * anchors.shape[1] * 5 + anchors.shape[0]
    raw = rng.normal(0.0, 0.35, size=(1, output_width)).astype(np.float32)
    cases = [
        compare_case(raw, anchors, temperature=1.0, covariance_scale=1.0),
        compare_case(raw, anchors, temperature=1.7, covariance_scale=0.03125),
    ]
    report = {
        "equivalence_schema_version": "multipath_gmm_equivalence_v1",
        "status": "pass" if all(case["status"] == "pass" for case in cases) else "fail",
        "seed": args.seed,
        "raw_output_shape": list(raw.shape),
        "anchors_shape": list(anchors.shape),
        "cases": cases,
    }
    if args.output_json:
        output_path = Path(args.output_json).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
