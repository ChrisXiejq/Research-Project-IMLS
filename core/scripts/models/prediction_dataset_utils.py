#!/usr/bin/env python3
from __future__ import annotations

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
