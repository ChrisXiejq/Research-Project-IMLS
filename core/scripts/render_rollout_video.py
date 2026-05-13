#!/usr/bin/env python3
"""
Offline top-down rollout video from ``scenario_result.pkl``.

Draws intersection approach segments from the scenario CSV (street context) and
oriented vehicle boxes from logged states (ego / target / static). No CARLA
connection required — suitable for headless AutoDL after a successful run.

Usage (from ``Research-Project-IMLS/core``)::

    MPLBACKEND=Agg python scripts/render_rollout_video.py \\
        --pkl results/<stamp>/scenario_01_ego_init_01_smpc_var_risk/scenario_result.pkl \\
        --intersection_csv scripts/carla/scenarios/intersection_01.csv \\
        --out results/<stamp>/.../rollout_topdown.mp4
"""
from __future__ import annotations

import argparse
import os
import pickle
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np


def _load_intersection_polylines(csv_path: str) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Each CSV row: start_x, start_y, start_yaw_deg, goal_x, goal_y, goal_yaw_deg -> one segment."""
    polylines: List[Tuple[np.ndarray, np.ndarray]] = []
    if not csv_path or not os.path.isfile(csv_path):
        return polylines
    with open(csv_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [float(x) for x in line.replace(" ", "").split(",")]
            if len(parts) < 6:
                continue
            sx, sy, _, gx, gy, _ = parts[:6]
            polylines.append((np.array([sx, gx], dtype=float), np.array([sy, gy], dtype=float)))
    return polylines


def _bbox_for_actor(l_f: float, l_r: float) -> Tuple[float, float]:
    """Rough footprint (length, width) in meters for top-down box."""
    length = max(3.2, float(l_f) + float(l_r) + 2.4)
    width = 1.9
    return length, width


def _vehicle_polygon_cg(x: float, y: float, yaw: float, l_f: float, l_r: float, length: float, width: float) -> np.ndarray:
    """Oriented rectangle centered at CG (x,y), yaw radians, +x forward."""
    hl = 0.5 * length
    hw = 0.5 * width
    corners_b = np.array([[hl, hw], [hl, -hw], [-hl, -hw], [-hl, hw]], dtype=np.float64)
    c, s = np.cos(yaw), np.sin(yaw)
    R = np.array([[c, -s], [s, c]], dtype=np.float64)
    poly = (R @ corners_b.T).T + np.array([x, y], dtype=np.float64)
    return poly.astype(np.float32)


def _world_to_pixel(
    wx: float,
    wy: float,
    bounds: Tuple[float, float, float, float],
    W: int,
    H: int,
    margin_px: int,
) -> Tuple[int, int]:
    xmin, xmax, ymin, ymax = bounds
    sx = (W - 2 * margin_px) / max(xmax - xmin, 1e-3)
    sy = (H - 2 * margin_px) / max(ymax - ymin, 1e-3)
    s = min(sx, sy)
    px = int(margin_px + (wx - xmin) * s)
    py = int(H - margin_px - (wy - ymin) * s)
    return px, py


def _actor_color_bgr(role_key: str) -> Tuple[int, int, int]:
    if "ego" in role_key:
        return (0, 200, 0)
    if "target" in role_key:
        return (0, 0, 220)
    return (180, 180, 180)


def render_topdown_mp4(
    pkl_path: str,
    intersection_csv: Optional[str],
    out_mp4: str,
    *,
    fps: float = 15.0,
    width: int = 1280,
    height: int = 720,
    margin_px: int = 40,
) -> str:
    if not os.path.isfile(pkl_path):
        raise FileNotFoundError(pkl_path)

    with open(pkl_path, "rb") as f:
        bundle: Dict[str, dict] = pickle.load(f)

    actors: List[Tuple[str, dict]] = sorted(bundle.items(), key=lambda kv: (0 if "ego" in kv[0] else 1, kv[0]))

    trajs: List[Tuple[str, np.ndarray, float, float]] = []
    for key, payload in actors:
        st = np.asarray(payload.get("state_trajectory"))
        if st.size == 0 or st.ndim != 2 or st.shape[1] < 5:
            continue
        lf = float(payload.get("l_f", 1.35))
        lr = float(payload.get("l_r", 1.35))
        trajs.append((key, st, lf, lr))

    if not trajs:
        raise ValueError(f"No usable trajectories in {pkl_path}")

    n_frames = max(t[1].shape[0] for t in trajs)

    # Bounds from trajectories + intersection polylines
    xs: List[float] = []
    ys: List[float] = []
    for _, st, _, _ in trajs:
        xs.extend(st[:, 1].tolist())
        ys.extend(st[:, 2].tolist())
    polylines = _load_intersection_polylines(intersection_csv) if intersection_csv else []
    for xarr, yarr in polylines:
        xs.extend(xarr.tolist())
        ys.extend(yarr.tolist())
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    pad = max(8.0, 0.08 * max(xmax - xmin, ymax - ymin, 1.0))
    bounds = (xmin - pad, xmax + pad, ymin - pad, ymax + pad)

    os.makedirs(os.path.dirname(out_mp4) or ".", exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(out_mp4, fourcc, float(fps), (width, height))
    if not vw.isOpened():
        raise RuntimeError(f"Could not open VideoWriter for {out_mp4}")

    for fi in range(n_frames):
        frame = np.ones((height, width, 3), dtype=np.uint8) * 255

        # Roads
        for xarr, yarr in polylines:
            pts = []
            for wx, wy in zip(xarr.tolist(), yarr.tolist()):
                px, py = _world_to_pixel(wx, wy, bounds, width, height, margin_px)
                pts.append((px, py))
            if len(pts) >= 2:
                cv2.polylines(frame, [np.array(pts, dtype=np.int32)], False, (40, 40, 40), 3, lineType=cv2.LINE_AA)

        # Vehicles (ego drawn last)
        order = sorted(range(len(trajs)), key=lambda i: 1 if "ego" in trajs[i][0] else 0)
        for idx in order:
            key, st, lf, lr = trajs[idx]
            row = st[min(fi, st.shape[0] - 1)]
            x, y, yaw = float(row[1]), float(row[2]), float(row[3])
            L, Wb = _bbox_for_actor(lf, lr)
            poly = _vehicle_polygon_cg(x, y, yaw, lf, lr, L, Wb)
            pix = np.array(
                [_world_to_pixel(float(px), float(py), bounds, width, height, margin_px) for px, py in poly],
                dtype=np.int32,
            )
            cv2.fillConvexPoly(frame, pix, _actor_color_bgr(key), lineType=cv2.LINE_AA)
            cv2.polylines(frame, [pix], True, (20, 20, 20), 1, lineType=cv2.LINE_AA)

        t_sim = float(trajs[0][1][min(fi, trajs[0][1].shape[0] - 1), 0])
        cv2.putText(
            frame,
            f"frame {fi+1}/{n_frames}  t={t_sim:.2f}s",
            (20, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (30, 30, 30),
            2,
            cv2.LINE_AA,
        )
        vw.write(frame)

    vw.release()
    return out_mp4


def main():
    ap = argparse.ArgumentParser(description="Render top-down MP4 from scenario_result.pkl (offline).")
    ap.add_argument("--pkl", required=True, help="Path to scenario_result.pkl")
    ap.add_argument("--intersection_csv", default=None, help="intersection_01.csv (same format as scenarios/)")
    ap.add_argument("--out", default=None, help="Output .mp4 path (default: next to pkl as rollout_topdown.mp4)")
    ap.add_argument("--fps", type=float, default=15.0)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    args = ap.parse_args()

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.pkl)), "rollout_topdown.mp4")
    path = render_topdown_mp4(
        args.pkl,
        args.intersection_csv,
        out,
        fps=args.fps,
        width=args.width,
        height=args.height,
    )
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
