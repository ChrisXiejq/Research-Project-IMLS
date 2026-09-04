#!/usr/bin/env python3
"""Shared V2 ego-target interaction sequence construction.

Online inference and offline dataset loading both call
``build_interaction_sequence`` on the same serialisable aligned world states.
No treatment/policy labels are used as predictor inputs.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

import numpy as np


FEATURE_SCHEMA_ID = "give_way_interaction_sequence_v2"
HISTORY_TIMES_S = (-1.0, -0.8, -0.6, -0.4, -0.2, 0.0)
FEATURE_NAMES = (
    "time_offset_s",
    "ego_rel_x_m",
    "ego_rel_y_m",
    "target_rel_x_m",
    "target_rel_y_m",
    "ego_speed_mps",
    "target_speed_mps",
    "relative_longitudinal_speed_mps",
    "relative_lateral_speed_mps",
    "sin_relative_yaw",
    "cos_relative_yaw",
    "ego_target_distance_m",
)
ALIGNMENT_TOLERANCE_S = 0.1


@dataclass(frozen=True)
class InteractionSequence:
    values: np.ndarray
    mask: np.ndarray


def _finite_float(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Expected a finite numeric value, got {value!r}")
    return result


def _normalise_actor_state(state: Dict[str, Any]) -> Dict[str, float]:
    return {
        "x": _finite_float(state["x"]),
        "y_rhs": _finite_float(state["y_rhs"]),
        "yaw_rad_rhs": _finite_float(state["yaw_rad_rhs"]),
        "vx_rhs": _finite_float(state["vx_rhs"]),
        "vy_rhs": _finite_float(state["vy_rhs"]),
    }


def build_interaction_sequence(
    aligned_history_world: Sequence[Dict[str, Any]],
    *,
    history_times_s: Sequence[float] = HISTORY_TIMES_S,
    alignment_tolerance_s: float = ALIGNMENT_TOLERANCE_S,
) -> InteractionSequence:
    """Build the frozen 6x12 target-local sequence from aligned world states."""

    expected_times = np.asarray(history_times_s, dtype=np.float64)
    if len(expected_times) != 6:
        raise ValueError(f"V2 requires six history tokens, got {len(expected_times)}")
    if len(aligned_history_world) != len(expected_times):
        raise ValueError(
            f"Expected {len(expected_times)} aligned states, got {len(aligned_history_world)}"
        )

    current = aligned_history_world[-1]
    if not bool(current.get("valid", False)):
        return InteractionSequence(
            values=np.zeros((len(expected_times), len(FEATURE_NAMES)), dtype=np.float32),
            mask=np.zeros((len(expected_times),), dtype=np.float32),
        )
    current_target = _normalise_actor_state(current["target"])
    target_origin = np.asarray(
        [current_target["x"], current_target["y_rhs"]], dtype=np.float64
    )
    yaw = current_target["yaw_rad_rhs"]
    target_to_world = np.asarray(
        [[math.cos(yaw), -math.sin(yaw)], [math.sin(yaw), math.cos(yaw)]],
        dtype=np.float64,
    )

    values = np.zeros((len(expected_times), len(FEATURE_NAMES)), dtype=np.float32)
    mask = np.zeros((len(expected_times),), dtype=np.float32)
    for index, (expected_time, token) in enumerate(zip(expected_times, aligned_history_world)):
        actual_time = float(token.get("time_offset_s", expected_time))
        if (
            not bool(token.get("valid", False))
            or abs(actual_time - expected_time) > alignment_tolerance_s + 1.0e-9
        ):
            continue
        try:
            ego = _normalise_actor_state(token["ego"])
            target = _normalise_actor_state(token["target"])
        except (KeyError, TypeError, ValueError):
            continue

        ego_xy = np.asarray([ego["x"], ego["y_rhs"]], dtype=np.float64)
        target_xy = np.asarray([target["x"], target["y_rhs"]], dtype=np.float64)
        ego_velocity = np.asarray([ego["vx_rhs"], ego["vy_rhs"]], dtype=np.float64)
        target_velocity = np.asarray(
            [target["vx_rhs"], target["vy_rhs"]], dtype=np.float64
        )
        ego_local = (ego_xy - target_origin) @ target_to_world
        target_local = (target_xy - target_origin) @ target_to_world
        relative_velocity_local = (ego_velocity - target_velocity) @ target_to_world
        relative_yaw = ego["yaw_rad_rhs"] - target["yaw_rad_rhs"]
        separation = ego_xy - target_xy
        values[index] = np.asarray(
            [
                expected_time,
                ego_local[0],
                ego_local[1],
                target_local[0],
                target_local[1],
                np.linalg.norm(ego_velocity),
                np.linalg.norm(target_velocity),
                relative_velocity_local[0],
                relative_velocity_local[1],
                math.sin(relative_yaw),
                math.cos(relative_yaw),
                np.linalg.norm(separation),
            ],
            dtype=np.float32,
        )
        mask[index] = 1.0
    return InteractionSequence(values=values, mask=mask)


def interaction_sequence_from_sample(sample: Dict[str, Any]) -> InteractionSequence:
    """Rebuild a sample feature when raw history is present, otherwise validate it."""

    raw_history = sample.get("interaction_history_world")
    if raw_history is not None:
        return build_interaction_sequence(
            raw_history,
            history_times_s=sample.get("history_times_s", HISTORY_TIMES_S),
        )
    values = np.asarray(sample["interaction_sequence"], dtype=np.float32)
    mask = np.asarray(sample["interaction_sequence_mask"], dtype=np.float32)
    if values.shape != (len(HISTORY_TIMES_S), len(FEATURE_NAMES)):
        raise ValueError(f"Invalid interaction sequence shape: {values.shape}")
    if mask.shape != (len(HISTORY_TIMES_S),):
        raise ValueError(f"Invalid interaction mask shape: {mask.shape}")
    if not np.all(np.isin(mask, [0.0, 1.0])):
        raise ValueError("Interaction mask must contain only 0/1")
    if np.any(values[mask == 0.0] != 0.0):
        raise ValueError("Masked interaction tokens must be zero-filled")
    return InteractionSequence(values=values, mask=mask)


def aligned_history_from_agent_history(
    agent_history: Any,
    ego_agent_id: int,
    target_agent_id: int,
    *,
    history_times_s: Iterable[float] = HISTORY_TIMES_S,
    alignment_tolerance_s: float = ALIGNMENT_TOLERANCE_S,
) -> List[Dict[str, Any]]:
    """Extract serialisable aligned ego/target states from CARLA AgentHistory."""

    negative_times = [float(value) for value in history_times_s]
    lookbacks = [abs(value) for value in negative_times]
    snapshots = agent_history.query(
        history_secs=lookbacks,
        closeness_eps=alignment_tolerance_s,
    )
    aligned: List[Dict[str, Any]] = []
    for time_offset, lookback in zip(negative_times, lookbacks):
        scene = snapshots.get(np.round(lookback, 2), {})
        vehicles = {
            int(item["id"]): item for item in scene.get("vehicles", [])
        }
        ego_entry = vehicles.get(int(ego_agent_id))
        target_entry = vehicles.get(int(target_agent_id))
        valid = ego_entry is not None and target_entry is not None
        token: Dict[str, Any] = {
            "time_offset_s": time_offset,
            "valid": bool(valid),
            "ego": None,
            "target": None,
        }
        if valid:
            token["ego"] = _serialisable_snapshot_state(ego_entry)
            token["target"] = _serialisable_snapshot_state(target_entry)
        aligned.append(token)
    return aligned


def _serialisable_snapshot_state(entry: Dict[str, Any]) -> Dict[str, float]:
    centroid = entry["centroid"]
    velocity = entry["velocity"]
    return {
        "x": float(centroid[0]),
        "y_rhs": float(centroid[1]),
        "yaw_rad_rhs": float(entry["yaw"]),
        "vx_rhs": float(velocity[0]),
        "vy_rhs": float(velocity[1]),
    }


def assert_logged_feature_equivalence(
    sample: Dict[str, Any],
    *,
    atol: float = 1.0e-6,
) -> Dict[str, float]:
    """Check stored sequence/mask against reconstruction from raw history."""

    if sample.get("interaction_history_world") is None:
        raise ValueError("Sample lacks interaction_history_world")
    rebuilt = interaction_sequence_from_sample(sample)
    stored_values = np.asarray(sample["interaction_sequence"], dtype=np.float32)
    stored_mask = np.asarray(sample["interaction_sequence_mask"], dtype=np.float32)
    value_error = float(np.max(np.abs(stored_values - rebuilt.values)))
    mask_error = float(np.max(np.abs(stored_mask - rebuilt.mask)))
    if value_error > atol or mask_error != 0.0:
        raise AssertionError(
            f"Interaction feature mismatch: value_error={value_error}, mask_error={mask_error}"
        )
    return {
        "sequence_max_abs_difference": value_error,
        "mask_max_abs_difference": mask_error,
    }
