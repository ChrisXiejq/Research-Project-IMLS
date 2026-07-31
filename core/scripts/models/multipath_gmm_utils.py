#!/usr/bin/env python3
"""Shared MultiPath raw-output to GMM conversion.

This module is the single numerical contract used by offline evaluation and
online deployment.  Keeping it TensorFlow-free also makes the conversion easy
to unit test without loading a SavedModel.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

import numpy as np


STD_PARAMETERIZATION = "exp_abs_raw"
COVARIANCE_SCALE_SEMANTICS = "multiplicative factor applied to the 2x2 covariance matrix"


@dataclass(frozen=True)
class GMMDecodeResult:
    probabilities: np.ndarray
    means: np.ndarray
    covariances: np.ndarray
    logits: np.ndarray
    raw_trajectory_parameters: np.ndarray
    axis_standard_deviations: np.ndarray


def _as_batch(raw_prediction: Any) -> Tuple[np.ndarray, bool]:
    raw = np.asarray(raw_prediction)
    squeeze = raw.ndim == 1
    if squeeze:
        raw = raw[None, :]
    if raw.ndim != 2:
        raise ValueError(f"Expected raw prediction shape [batch, output] or [output], got {raw.shape}")
    if not np.issubdtype(raw.dtype, np.floating):
        raw = raw.astype(np.float32)
    return raw, squeeze


def softmax_logits(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    temperature = float(temperature)
    if not np.isfinite(temperature) or temperature <= 0.0:
        raise ValueError(f"temperature must be finite and positive, got {temperature}")
    scaled = np.asarray(logits) / temperature
    shifted = scaled - np.max(scaled, axis=-1, keepdims=True)
    exponentials = np.exp(shifted)
    return exponentials / np.sum(exponentials, axis=-1, keepdims=True)


def decode_multipath_raw(
    raw_prediction: Any,
    anchors: Any,
    *,
    temperature: float = 1.0,
    covariance_scale: float = 1.0,
) -> GMMDecodeResult:
    """Decode MultiPath output using the historical deployment contract.

    Raw layout:
      K * T * [dx, dy, raw_std_1, raw_std_2, theta] + K logits

    Historical standard-deviation parameterization:
      std = exp(abs(raw_std))

    ``covariance_scale`` multiplies each complete 2x2 covariance matrix.  It is
    deliberately applied after the historical parameterization so a validation
    fitted post-hoc scale can be used without retraining.
    """

    raw, squeeze = _as_batch(raw_prediction)
    anchor_array = np.asarray(anchors, dtype=raw.dtype)
    if anchor_array.ndim != 3 or anchor_array.shape[-1] != 2:
        raise ValueError(f"Expected anchors [modes, timesteps, 2], got {anchor_array.shape}")
    covariance_scale = float(covariance_scale)
    if not np.isfinite(covariance_scale) or covariance_scale <= 0.0:
        raise ValueError(
            f"covariance_scale must be finite and positive, got {covariance_scale}"
        )

    num_modes, num_timesteps, _ = anchor_array.shape
    expected_output = num_modes * num_timesteps * 5 + num_modes
    if raw.shape[-1] != expected_output:
        raise ValueError(
            f"Raw output width {raw.shape[-1]} does not match "
            f"{num_modes} modes x {num_timesteps} timesteps ({expected_output})"
        )

    trajectory_parameters = raw[:, :-num_modes].reshape(
        raw.shape[0], num_modes, num_timesteps, 5
    )
    logits = raw[:, -num_modes:]
    probabilities = softmax_logits(logits, temperature=temperature)
    means = trajectory_parameters[..., :2] + anchor_array[None, ...]

    with np.errstate(over="ignore", invalid="ignore"):
        axis_stds = np.exp(np.abs(trajectory_parameters[..., 2:4]))
        variances = np.square(axis_stds)
        theta = trajectory_parameters[..., 4]
        cosine = np.cos(theta)
        sine = np.sin(theta)
        var_1 = variances[..., 0]
        var_2 = variances[..., 1]
        covariances = np.empty(
            (*trajectory_parameters.shape[:3], 2, 2), dtype=trajectory_parameters.dtype
        )
        covariances[..., 0, 0] = cosine * cosine * var_1 + sine * sine * var_2
        covariances[..., 1, 1] = sine * sine * var_1 + cosine * cosine * var_2
        off_diagonal = cosine * sine * (var_1 - var_2)
        covariances[..., 0, 1] = off_diagonal
        covariances[..., 1, 0] = off_diagonal
        covariances *= covariance_scale

    if squeeze:
        return GMMDecodeResult(
            probabilities=probabilities[0],
            means=means[0],
            covariances=covariances[0],
            logits=logits[0],
            raw_trajectory_parameters=trajectory_parameters[0],
            axis_standard_deviations=axis_stds[0],
        )
    return GMMDecodeResult(
        probabilities=probabilities,
        means=means,
        covariances=covariances,
        logits=logits,
        raw_trajectory_parameters=trajectory_parameters,
        axis_standard_deviations=axis_stds,
    )


def audit_covariances(covariances: Any, symmetry_tolerance: float = 1.0e-6) -> Dict[str, Any]:
    covariance_array = np.asarray(covariances)
    if covariance_array.shape[-2:] != (2, 2):
        raise ValueError(f"Expected trailing covariance shape [2, 2], got {covariance_array.shape}")
    flat = covariance_array.reshape(-1, 2, 2)
    finite = np.all(np.isfinite(flat), axis=(1, 2))
    symmetry_error = np.max(np.abs(flat - np.swapaxes(flat, 1, 2)), axis=(1, 2))
    symmetric = symmetry_error <= symmetry_tolerance

    determinants = np.full(len(flat), np.nan, dtype=np.float64)
    minimum_eigenvalues = np.full(len(flat), np.nan, dtype=np.float64)
    positive_definite = np.zeros(len(flat), dtype=bool)
    for index, covariance in enumerate(flat):
        if not finite[index] or not symmetric[index]:
            continue
        symmetric_covariance = 0.5 * (covariance + covariance.T)
        determinants[index] = float(np.linalg.det(symmetric_covariance))
        eigenvalues = np.linalg.eigvalsh(symmetric_covariance)
        minimum_eigenvalues[index] = float(np.min(eigenvalues))
        positive_definite[index] = bool(
            determinants[index] > 0.0 and minimum_eigenvalues[index] > 0.0
        )

    valid = finite & symmetric & positive_definite
    finite_symmetry_errors = symmetry_error[np.isfinite(symmetry_error)]
    finite_determinants = determinants[np.isfinite(determinants)]
    finite_minimum_eigenvalues = minimum_eigenvalues[np.isfinite(minimum_eigenvalues)]
    return {
        "total_matrices": int(len(flat)),
        "invalid_matrices": int(np.count_nonzero(~valid)),
        "invalid_rate": float(np.mean(~valid)) if len(flat) else None,
        "nonfinite_matrices": int(np.count_nonzero(~finite)),
        "nonsymmetric_matrices": int(np.count_nonzero(finite & ~symmetric)),
        "non_positive_definite_matrices": int(
            np.count_nonzero(finite & symmetric & ~positive_definite)
        ),
        "maximum_symmetry_error": (
            float(np.max(finite_symmetry_errors))
            if len(finite_symmetry_errors)
            else None
        ),
        "minimum_determinant": (
            float(np.min(finite_determinants)) if len(finite_determinants) else None
        ),
        "minimum_eigenvalue": (
            float(np.min(finite_minimum_eigenvalues))
            if len(finite_minimum_eigenvalues)
            else None
        ),
    }
