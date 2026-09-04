#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

"""Utilities for CARLA MultiPath prediction datasets.

The dataset is produced by CARLA rollouts with prediction logging enabled.  Raw
labels are stored in world coordinates, while MultiPath trains in the target
local frame, so this module centralises the coordinate conversion and fixed
split convention.
"""

import json
import math
import os
import re
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


SPLIT_RULE = "train ego_init_01-40, val ego_init_41-45, test ego_init_46-50"


def read_jsonl(path: str) -> Iterator[Dict]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: str, rows: Iterable[Dict]) -> int:
    count = 0
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
            count += 1
    return count


def result_dir_from_merged_dir(merged_dir: str) -> str:
    return os.path.abspath(os.path.join(merged_dir, os.pardir))


def infer_init_id(name: str) -> Optional[int]:
    match = re.search(r"ego_init_(\d+)", name)
    return int(match.group(1)) if match else None


def split_for_init(init_id: int) -> str:
    if 1 <= init_id <= 40:
        return "train"
    if 41 <= init_id <= 45:
        return "val"
    if 46 <= init_id <= 50:
        return "test"
    raise ValueError(f"Unsupported init id for fixed split: {init_id}")


def split_for_subrun(subrun: str) -> str:
    init_id = infer_init_id(subrun)
    if init_id is None:
        raise ValueError(f"Cannot infer ego_init id from subrun name: {subrun}")
    return split_for_init(init_id)


def resolve_raster_path(sample: Dict, result_dir: Optional[str] = None) -> Optional[str]:
    candidates = []
    if sample.get("raster_abspath"):
        candidates.append(sample["raster_abspath"])
    if result_dir and sample.get("raster_relpath_from_result"):
        candidates.append(os.path.join(result_dir, sample["raster_relpath_from_result"]))
    if sample.get("source_prediction_dataset_dir") and sample.get("raster_relpath"):
        candidates.append(os.path.join(sample["source_prediction_dataset_dir"], sample["raster_relpath"]))
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return os.path.abspath(candidate)
    return os.path.abspath(candidates[0]) if candidates else None


def valid_future_indices(sample: Dict, horizon: int = 10) -> List[int]:
    mask = sample.get("future_valid_mask") or []
    future = sample.get("future_xy_world") or []
    valid = []
    for idx, ok in enumerate(mask[:horizon]):
        if ok and idx < len(future) and future[idx] and future[idx][0] is not None:
            valid.append(idx)
    return valid


def has_full_horizon(sample: Dict, horizon: int = 10) -> bool:
    return len(valid_future_indices(sample, horizon=horizon)) == horizon


def world_future_to_local(sample: Dict, horizon: int = 10) -> np.ndarray:
    """Convert future world XY labels to the target local frame.

    During online prediction, GMM local predictions are transformed with:
      world_xy = R_target_to_world @ local_xy + t_target_to_world
    so training labels use the inverse transform.
    """

    import numpy as np

    valid = valid_future_indices(sample, horizon=horizon)
    if len(valid) != horizon:
        raise ValueError("Sample does not contain a full valid future horizon")

    future_world = np.asarray(sample["future_xy_world"][:horizon], dtype=np.float32)
    rotation = np.asarray(sample["target_to_world_R"], dtype=np.float32)
    translation = np.asarray(sample["target_to_world_t"], dtype=np.float32).reshape(1, 2)
    return (future_world - translation) @ rotation


def _state_value(state: Dict, key: str, default: float = 0.0) -> float:
    try:
        value = state.get(key, default)
        return float(value) if value is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def interaction_context_from_sample(sample: Dict) -> np.ndarray:
    """Return a compact ego-target interaction context in target-local axes.

    The current deployed MultiPath model only receives a raster and target
    history.  The interaction-aware adapter uses this low-dimensional side
    channel to expose the ego vehicle state without changing the planner-facing
    GMM output contract.
    """

    import numpy as np

    ego = sample.get("ego_state") or {}
    target = sample.get("target_state") or {}
    rotation = np.asarray(sample.get("target_to_world_R", np.eye(2)), dtype=np.float32)

    ego_xy = np.asarray([
        _state_value(ego, "x"),
        _state_value(ego, "y_rhs"),
    ], dtype=np.float32)
    target_xy = np.asarray([
        _state_value(target, "x"),
        _state_value(target, "y_rhs"),
    ], dtype=np.float32)
    rel_local = (ego_xy - target_xy).reshape(1, 2) @ rotation
    rel_x = float(rel_local[0, 0])
    rel_y = float(rel_local[0, 1])
    ego_speed = _state_value(ego, "speed")
    target_speed = _state_value(target, "speed")
    yaw_delta = math.radians(_state_value(ego, "yaw_deg") - _state_value(target, "yaw_deg"))
    distance = math.sqrt(rel_x * rel_x + rel_y * rel_y)

    return np.asarray(
        [
            rel_x,
            rel_y,
            ego_speed,
            target_speed,
            ego_speed - target_speed,
            math.sin(yaw_delta),
            math.cos(yaw_delta),
            distance,
        ],
        dtype=np.float32,
    )


def displacement_errors(pred: List, future_xy: List, mask: List, horizon: int = 10) -> Tuple[List[float], List[float]]:
    import numpy as np

    valid = [i for i in valid_future_indices({"future_xy_world": future_xy, "future_valid_mask": mask}, horizon=horizon)]
    if not valid:
        return [], []
    pred_arr = np.asarray(pred, dtype=np.float32)
    future_arr = np.asarray(future_xy, dtype=np.float32)
    ades = []
    fdes = []
    for mode in pred_arr:
        errs = [float(np.linalg.norm(mode[i] - future_arr[i])) for i in valid]
        ades.append(float(np.mean(errs)))
        fdes.append(float(errs[-1]))
    return ades, fdes


def percentile(values: List[float], percent: float) -> float:
    import numpy as np

    if not values:
        return float("nan")
    return float(np.percentile(np.asarray(values, dtype=np.float32), percent))


def mean(values: List[float]) -> float:
    import numpy as np

    return float(np.mean(np.asarray(values, dtype=np.float32))) if values else float("nan")


def finite_or_none(value: float):
    return float(value) if math.isfinite(float(value)) else None
