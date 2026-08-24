"""Prediction-driven conflict-zone constraints for supervisor-free SMPC."""

from __future__ import annotations

import numpy as np


def conflict_zone_filter_bounds(
    target_means,
    target_covariances,
    *,
    target_conflict_point_xy,
    target_tangent_xy,
    ego_buffer_m,
    target_conflict_half_length_m,
    sigma_scale,
    inactive_bound_m,
    horizon_steps,
):
    """Map multimodal target occupancy to solver half-space bounds.

    A negative bound keeps the ego centre behind its conflict point. An
    inactive large bound removes the constraint after every target mode has
    cleared. The calculation contains no distance trigger, yield state, or
    applied-action override.
    """

    means = np.asarray(target_means, dtype=float)
    covariances = np.asarray(target_covariances, dtype=float)
    point = np.asarray(target_conflict_point_xy, dtype=float).reshape(-1)
    tangent = np.asarray(target_tangent_xy, dtype=float).reshape(-1)
    if means.ndim != 3 or means.shape[-1] != 2:
        raise ValueError("target_means must have shape [mode, time, 2]")
    if covariances.shape != means.shape[:2] + (2, 2):
        raise ValueError("target_covariances must have shape [mode, time, 2, 2]")
    if point.shape != (2,) or tangent.shape != (2,):
        raise ValueError("conflict point and tangent must each have shape (2,)")
    tangent_norm = float(np.linalg.norm(tangent))
    if tangent_norm <= 1.0e-8 or not np.isfinite(tangent_norm):
        raise ValueError("target tangent must be finite and non-zero")
    tangent = tangent / tangent_norm
    horizon = int(horizon_steps)
    if horizon <= 0 or means.shape[1] < horizon:
        raise ValueError("target predictions do not cover the requested horizon")
    scalars = (
        ego_buffer_m,
        target_conflict_half_length_m,
        sigma_scale,
        inactive_bound_m,
    )
    if not all(np.isfinite(value) and float(value) >= 0.0 for value in scalars):
        raise ValueError("conflict-zone filter scalars must be finite and non-negative")
    if float(inactive_bound_m) <= 0.0:
        raise ValueError("inactive_bound_m must be positive")

    means = means[:, :horizon, :]
    covariances = covariances[:, :horizon, :, :]
    signed_means = np.einsum("mti,i->mt", means - point, tangent)
    longitudinal_variances = np.einsum(
        "i,mtij,j->mt", tangent, covariances, tangent
    )
    longitudinal_std = np.sqrt(np.maximum(longitudinal_variances, 0.0))
    occupancy_radius = (
        float(target_conflict_half_length_m)
        + float(sigma_scale) * longitudinal_std
    )
    raw_occupancy = np.any(np.abs(signed_means) <= occupancy_radius, axis=0)
    raw_indices = np.flatnonzero(raw_occupancy)
    # The oncoming vehicle has priority.  If it may occupy the conflict zone
    # anywhere in the prediction horizon, the ego must remain behind the stop
    # half-space from the first prediction step through the last possible
    # occupancy.  Activating only at the occupancy instants permits the ego to
    # cross first and then asks a later linearised problem to retreat, which is
    # neither physically meaningful nor recursively feasible.
    active = np.zeros(horizon, dtype=bool)
    if raw_indices.size:
        active[: int(raw_indices[-1]) + 1] = True
    bounds = np.where(
        active,
        -float(ego_buffer_m),
        float(inactive_bound_m),
    )
    active_indices = np.flatnonzero(active)
    return bounds, {
        "enabled": True,
        "active_steps": active_indices.astype(int).tolist(),
        "active_count": int(active_indices.size),
        "earliest_active_step": (
            int(active_indices[0]) if active_indices.size else None
        ),
        "raw_occupancy_steps": raw_indices.astype(int).tolist(),
        "last_raw_occupancy_step": (
            int(raw_indices[-1]) if raw_indices.size else None
        ),
        "temporal_policy": "target_priority_prefix_closure",
        "ego_buffer_m": float(ego_buffer_m),
        "target_conflict_half_length_m": float(target_conflict_half_length_m),
        "sigma_scale": float(sigma_scale),
        "uses_all_modes": True,
    }
