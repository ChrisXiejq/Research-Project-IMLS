"""
Export lane polygons from the *currently loaded* CARLA map for rollout debugging.

Writes ``map_viz_snapshot.json`` next to ``scenario_result.pkl`` (same coordinate frame
as logged trajectories: CARLA world X/Y, yaw unchanged).
"""
from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def bounds_from_results_dict(results_dict: Dict[str, Any], pad_m: float) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for payload in results_dict.values():
        st = np.asarray(payload.get("state_trajectory"))
        if st.size == 0 or st.ndim != 2 or st.shape[1] < 3:
            continue
        xs.extend(st[:, 1].astype(float).tolist())
        ys.extend(st[:, 2].astype(float).tolist())
    if not xs:
        raise ValueError("no trajectory points for map export bounds")
    return (min(xs) - pad_m, max(xs) + pad_m, min(ys) - pad_m, max(ys) + pad_m)


def lane_polygons_in_bounds(
    topology: Any,
    bounds: Tuple[float, float, float, float],
    precision: float,
) -> List[np.ndarray]:
    """Lane strips as closed polygons in CARLA world X/Y (same as ``state_trajectory``)."""
    from rasterizer.semantic_rasterizer import extract_waypoints_from_topology

    xmin, xmax, ymin, ymax = bounds
    polys: List[np.ndarray] = []
    for wp_chain in extract_waypoints_from_topology(topology, precision=precision):
        if len(wp_chain) < 2:
            continue
        center = np.array([[w.transform.location.x, w.transform.location.y] for w in wp_chain], dtype=np.float64)
        widths = np.array([float(w.lane_width) for w in wp_chain], dtype=np.float64)
        yaw_deg = np.array([float(w.transform.rotation.yaw) for w in wp_chain], dtype=np.float64)
        yaw = np.radians(yaw_deg)
        hw = widths * 0.5
        left = center + np.column_stack(
            [np.cos(yaw + math.pi / 2.0) * hw, np.sin(yaw + math.pi / 2.0) * hw]
        )
        right = center + np.column_stack(
            [np.cos(yaw - math.pi / 2.0) * hw, np.sin(yaw - math.pi / 2.0) * hw]
        )
        poly = np.vstack([left, right[::-1]])
        pxmin, pymin = float(np.min(poly[:, 0])), float(np.min(poly[:, 1]))
        pxmax, pymax = float(np.max(poly[:, 0])), float(np.max(poly[:, 1]))
        if pxmax < xmin or pxmin > xmax or pymax < ymin or pymin > ymax:
            continue
        polys.append(poly.astype(np.float32))
    return polys


def try_export_map_viz_snapshot(
    carla_world: Any,
    results_dict: Dict[str, Any],
    savedir: str,
    *,
    pad_m: float = 30.0,
    precision: float = 1.2,
) -> Optional[str]:
    """
    Serialize lane polygons overlapping the trajectory bounding box (+ pad).

    Returns path to ``map_viz_snapshot.json`` or ``None`` if nothing written.
    """
    bounds = bounds_from_results_dict(results_dict, pad_m)
    topo = carla_world.get_map().get_topology()
    polys = lane_polygons_in_bounds(topo, bounds, precision=precision)
    if not polys:
        return None
    payload = {
        "coord_frame": "carla_world_xy",
        "map_name": str(carla_world.get_map().name),
        "bounds": [bounds[0], bounds[1], bounds[2], bounds[3]],
        "lane_polygons": [p.tolist() for p in polys],
    }
    os.makedirs(savedir, exist_ok=True)
    path = os.path.join(savedir, "map_viz_snapshot.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    return path
