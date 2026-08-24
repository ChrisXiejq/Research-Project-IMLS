"""Exogenous straight-target GMM used by the implicit-SMPC experiment.

The target prediction depends only on the target's measured position and
velocity.  It deliberately has no ego-state input, so the planner cannot rely
on a predicted cooperative response from the priority vehicle.  Speed modes
retain the multi-modal interface expected by the Nair et al. SMPC chance
constraints while representing one common straight route.
"""

from __future__ import annotations

from typing import Dict, Sequence, Tuple

import numpy as np


def route_line_conflict_geometry(
    ego_route_xy: Sequence[Sequence[float]],
    target_start_xy: Sequence[float],
    target_goal_xy: Sequence[float],
) -> Dict[str, object]:
    """Return fixed ego-route/target-line conflict geometry.

    The geometry is used for offline phase labelling.  A controller may also
    consume the conflict point/tangents only when an explicit optimisation-
    based conflict-zone filter is enabled; phase thresholds such as the 12 m
    arrival window are never returned here or supplied to the controller.
    """

    ego_route = np.asarray(ego_route_xy, dtype=float)
    target_start = np.asarray(target_start_xy, dtype=float).reshape(-1)
    target_goal = np.asarray(target_goal_xy, dtype=float).reshape(-1)
    if ego_route.ndim != 2 or ego_route.shape[0] < 2 or ego_route.shape[1] < 2:
        raise ValueError("ego_route_xy must have shape [N>=2, >=2]")
    if target_start.shape != (2,) or target_goal.shape != (2,):
        raise ValueError("target start and goal must each contain two values")
    if not (
        np.isfinite(ego_route[:, :2]).all()
        and np.isfinite(target_start).all()
        and np.isfinite(target_goal).all()
    ):
        raise ValueError("route conflict geometry inputs must be finite")

    target_delta = target_goal - target_start
    target_length = float(np.linalg.norm(target_delta))
    if target_length <= 1.0e-8:
        raise ValueError("target route must have non-zero length")
    target_tangent = target_delta / target_length
    ego_xy = ego_route[:, :2]
    target_progress = (ego_xy - target_start) @ target_tangent
    target_projection = (
        target_start + target_progress[:, None] * target_tangent[None, :]
    )
    separation = np.linalg.norm(ego_xy - target_projection, axis=1)
    ego_index = int(np.argmin(separation))
    ego_before = max(0, ego_index - 1)
    ego_after = min(ego_xy.shape[0] - 1, ego_index + 1)
    ego_delta = ego_xy[ego_after] - ego_xy[ego_before]
    ego_length = float(np.linalg.norm(ego_delta))
    if ego_length <= 1.0e-8:
        raise ValueError("ego route tangent is degenerate at the conflict point")
    ego_tangent = ego_delta / ego_length
    return {
        "source": "fixed_ego_reference_target_route_line",
        "controller_input": False,
        "ego_conflict_point_xy": ego_xy[ego_index].copy(),
        "target_conflict_point_xy": target_projection[ego_index].copy(),
        "ego_route_index": ego_index,
        "route_line_separation_m": float(separation[ego_index]),
        "ego_tangent_xy": ego_tangent.copy(),
        "target_tangent_xy": target_tangent.copy(),
    }


def build_exogenous_straight_gmm(
    position_xy: Sequence[float],
    velocity_xy: Sequence[float],
    *,
    horizon_steps: int,
    dt_s: float,
    speed_offsets_mps: Sequence[float],
    mode_probabilities: Sequence[float],
    initial_longitudinal_std_m: float,
    initial_lateral_std_m: float,
    longitudinal_std_growth_mps: float,
    lateral_std_growth_mps: float,
    fallback_heading_rad: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(probabilities, means, covariances)`` for a straight target.

    Means have shape ``[mode, time, xy]`` and covariances have shape
    ``[mode, time, xy, xy]``.  Uncertainty grows with time in the target's
    longitudinal/lateral frame and is rotated into world coordinates.
    """

    position = np.asarray(position_xy, dtype=float).reshape(-1)
    velocity = np.asarray(velocity_xy, dtype=float).reshape(-1)
    offsets = np.asarray(speed_offsets_mps, dtype=float).reshape(-1)
    probabilities = np.asarray(mode_probabilities, dtype=float).reshape(-1)

    if position.shape != (2,) or velocity.shape != (2,):
        raise ValueError("position_xy and velocity_xy must each contain two values")
    if not np.isfinite(position).all() or not np.isfinite(velocity).all():
        raise ValueError("position_xy and velocity_xy must be finite")
    if int(horizon_steps) < 2:
        raise ValueError("horizon_steps must be at least 2")
    if not np.isfinite(dt_s) or float(dt_s) <= 0.0:
        raise ValueError("dt_s must be positive and finite")
    if offsets.size == 0 or offsets.shape != probabilities.shape:
        raise ValueError("speed offsets and probabilities must have equal non-zero length")
    if not np.isfinite(offsets).all() or not np.isfinite(probabilities).all():
        raise ValueError("speed offsets and probabilities must be finite")
    if np.any(probabilities < 0.0) or not np.isclose(probabilities.sum(), 1.0):
        raise ValueError("mode probabilities must be non-negative and sum to one")

    std_values = (
        initial_longitudinal_std_m,
        initial_lateral_std_m,
        longitudinal_std_growth_mps,
        lateral_std_growth_mps,
    )
    if not all(np.isfinite(value) and float(value) >= 0.0 for value in std_values):
        raise ValueError("straight-target standard deviations and growth rates must be finite and non-negative")
    if initial_longitudinal_std_m == 0.0 or initial_lateral_std_m == 0.0:
        raise ValueError("initial straight-target standard deviations must be positive")

    measured_speed = float(np.linalg.norm(velocity))
    if measured_speed > 1.0e-6:
        tangent = velocity / measured_speed
    else:
        tangent = np.array(
            [np.cos(float(fallback_heading_rad)), np.sin(float(fallback_heading_rad))],
            dtype=float,
        )
    normal = np.array([-tangent[1], tangent[0]], dtype=float)
    rotation = np.column_stack((tangent, normal))

    times = float(dt_s) * np.arange(1, int(horizon_steps) + 1, dtype=float)
    mode_speeds = np.maximum(0.0, measured_speed + offsets)
    means = np.stack(
        [position + times[:, None] * speed * tangent for speed in mode_speeds],
        axis=0,
    )

    longitudinal_std = (
        float(initial_longitudinal_std_m)
        + float(longitudinal_std_growth_mps) * times
    )
    lateral_std = (
        float(initial_lateral_std_m)
        + float(lateral_std_growth_mps) * times
    )
    covariance_by_time = np.stack(
        [
            rotation
            @ np.diag([longitudinal_std[index] ** 2, lateral_std[index] ** 2])
            @ rotation.T
            for index in range(len(times))
        ],
        axis=0,
    )
    covariances = np.repeat(covariance_by_time[None, ...], offsets.size, axis=0)
    return probabilities, means, covariances
