#!/usr/bin/env python3
"""
Offline top-down rollout video from ``scenario_result.pkl``.

Draws road corridors from intersection CSV segments (width + lane markings) and
styled top-down vehicles (shadow, body, windshield band, wheel hints). Road width
and dash spacing default from ``scenario_rollout_config.json`` (written on each
successful batch subrun from the scene JSON ``viz_topdown`` block), then CLI overrides.

No CARLA connection required — suitable for headless AutoDL after a successful run.

Usage (from ``Research-Project-IMLS/core``)::

    MPLBACKEND=Agg python scripts/render_rollout_video.py \\
        --pkl results/<stamp>/scenario_01_ego_init_01_smpc_var_risk/scenario_result.pkl \\
        --intersection_csv scripts/carla/scenarios/intersection_01.csv \\
        --out results/<stamp>/.../rollout_topdown.mp4
"""
from __future__ import annotations

import argparse
import json
import math
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
    r = np.array([[c, -s], [s, c]], dtype=np.float64)
    poly = (r @ corners_b.T).T + np.array([x, y], dtype=np.float64)
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


def _world_scale_per_pixel(bounds: Tuple[float, float, float, float], W: int, H: int, margin_px: int) -> float:
    xmin, xmax, ymin, ymax = bounds
    sx = (W - 2 * margin_px) / max(xmax - xmin, 1e-3)
    sy = (H - 2 * margin_px) / max(ymax - ymin, 1e-3)
    return float(min(sx, sy))


def _poly_world_to_pix(
    poly_w: np.ndarray,
    bounds: Tuple[float, float, float, float],
    W: int,
    H: int,
    margin_px: int,
) -> np.ndarray:
    out = []
    for px, py in poly_w:
        u, v = _world_to_pixel(float(px), float(py), bounds, W, H, margin_px)
        out.append([u, v])
    return np.array(out, dtype=np.int32)


def _segment_strip_world(sx: float, sy: float, gx: float, gy: float, half_width: float) -> np.ndarray:
    """Quad in world XY covering the segment [S,G] expanded by half_width perpendicular."""
    dx, dy = gx - sx, gy - sy
    ln = math.hypot(dx, dy)
    if ln < 1e-6:
        return np.array([[sx, sy], [sx, sy], [sx, sy], [sx, sy]], dtype=np.float32)
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux
    ox, oy = px * half_width, py * half_width
    return np.array(
        [
            [sx + ox, sy + oy],
            [gx + ox, gy + oy],
            [gx - ox, gy - oy],
            [sx - ox, sy - oy],
        ],
        dtype=np.float32,
    )


def _draw_road_corridor(
    frame: np.ndarray,
    xarr: np.ndarray,
    yarr: np.ndarray,
    bounds: Tuple[float, float, float, float],
    W: int,
    H: int,
    margin_px: int,
    half_width_m: float,
    asphalt: Tuple[int, int, int],
    edge_bgr: Tuple[int, int, int],
    center_bgr: Tuple[int, int, int],
    dash_len_m: float,
    dash_gap_m: float,
) -> None:
    sx, gx = float(xarr[0]), float(xarr[1])
    sy, gy = float(yarr[0]), float(yarr[1])
    strip = _segment_strip_world(sx, sy, gx, gy, half_width_m)
    pix = _poly_world_to_pix(strip, bounds, W, H, margin_px)
    cv2.fillConvexPoly(frame, pix, asphalt, lineType=cv2.LINE_AA)

    dx, dy = gx - sx, gy - sy
    ln = math.hypot(dx, dy)
    if ln < 1e-3:
        return
    ux, uy = dx / ln, dy / ln
    px, py = -uy, ux
    ox, oy = px * half_width_m, py * half_width_m
    left_a = _world_to_pixel(sx + ox, sy + oy, bounds, W, H, margin_px)
    left_b = _world_to_pixel(gx + ox, gy + oy, bounds, W, H, margin_px)
    right_a = _world_to_pixel(sx - ox, sy - oy, bounds, W, H, margin_px)
    right_b = _world_to_pixel(gx - ox, gy - oy, bounds, W, H, margin_px)
    cv2.line(frame, left_a, left_b, edge_bgr, 2, lineType=cv2.LINE_AA)
    cv2.line(frame, right_a, right_b, edge_bgr, 2, lineType=cv2.LINE_AA)

    period = max(dash_len_m + dash_gap_m, 0.5)
    t = 0.0
    while t < ln:
        t1 = min(t + dash_len_m, ln)
        cx0, cy0 = sx + ux * t, sy + uy * t
        cx1, cy1 = sx + ux * t1, sy + uy * t1
        p0 = _world_to_pixel(cx0, cy0, bounds, W, H, margin_px)
        p1 = _world_to_pixel(cx1, cy1, bounds, W, H, margin_px)
        cv2.line(frame, p0, p1, center_bgr, 3, lineType=cv2.LINE_AA)
        t += period


def _actor_body_colors(role_key: str) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], Tuple[int, int, int]]:
    """Base BGR, lighter roof strip, windshield line."""
    if "ego" in role_key:
        return (42, 140, 58), (90, 200, 120), (200, 240, 210)
    if "target" in role_key:
        return (52, 52, 190), (100, 100, 230), (220, 210, 250)
    return (95, 95, 105), (130, 130, 145), (200, 200, 210)


def _draw_vehicle_styled(
    frame: np.ndarray,
    x: float,
    y: float,
    yaw: float,
    lf: float,
    lr: float,
    length: float,
    width: float,
    bounds: Tuple[float, float, float, float],
    W: int,
    H: int,
    margin_px: int,
    role_key: str,
) -> None:
    poly_w = _vehicle_polygon_cg(x, y, yaw, lf, lr, length, width)
    pix = _poly_world_to_pix(poly_w, bounds, W, H, margin_px)

    shadow = pix.copy().astype(np.int32)
    shadow[:, 0] += 4
    shadow[:, 1] += 5
    cv2.fillConvexPoly(frame, shadow.astype(np.int32), (38, 38, 42), lineType=cv2.LINE_AA)

    base, roof_hi, win_hi = _actor_body_colors(role_key)
    cv2.fillConvexPoly(frame, pix, base, lineType=cv2.LINE_AA)

    c, s = math.cos(yaw), math.sin(yaw)
    hl = 0.5 * length
    hw = 0.5 * width * 0.55
    for frac in (0.22, -0.18):
        cx = x + c * frac * hl - s * 0.0
        cy = y + s * frac * hl + c * 0.0
        p1w = np.array(
            [
                [cx + c * 0.35 * hl - s * hw, cy + s * 0.35 * hl + c * hw],
                [cx + c * 0.35 * hl + s * hw, cy + s * 0.35 * hl - c * hw],
                [cx - c * 0.12 * hl + s * hw, cy - s * 0.12 * hl - c * hw],
                [cx - c * 0.12 * hl - s * hw, cy - s * 0.12 * hl + c * hw],
            ],
            dtype=np.float32,
        )
        band = _poly_world_to_pix(p1w, bounds, W, H, margin_px)
        cv2.fillConvexPoly(frame, band, roof_hi, lineType=cv2.LINE_AA)

    fx = x + c * (0.85 * hl)
    fy = y + s * (0.85 * hl)
    lx = x + c * (0.55 * hl)
    ly = y + s * (0.55 * hl)
    p0 = _world_to_pixel(fx - s * hw * 0.9, fy + c * hw * 0.9, bounds, W, H, margin_px)
    p1 = _world_to_pixel(fx + s * hw * 0.9, fy - c * hw * 0.9, bounds, W, H, margin_px)
    cv2.line(frame, p0, p1, win_hi, 2, lineType=cv2.LINE_AA)
    p2 = _world_to_pixel(lx - s * hw * 0.5, ly + c * hw * 0.5, bounds, W, H, margin_px)
    cv2.line(frame, p0, p2, (25, 25, 30), 1, lineType=cv2.LINE_AA)

    mpp = _world_scale_per_pixel(bounds, W, H, margin_px)
    wrad = max(3, int(0.32 * mpp))
    for sx_off, sy_off in (
        (0.42 * hl, 0.62 * width * 0.5),
        (0.42 * hl, -0.62 * width * 0.5),
        (-0.48 * hl, 0.62 * width * 0.5),
        (-0.48 * hl, -0.62 * width * 0.5),
    ):
        wx = x + c * sx_off - s * sy_off
        wy = y + s * sx_off + c * sy_off
        cx, cy = _world_to_pixel(wx, wy, bounds, W, H, margin_px)
        cv2.circle(frame, (cx, cy), wrad, (22, 22, 24), -1, lineType=cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), max(1, wrad - 2), (55, 55, 60), 1, lineType=cv2.LINE_AA)

    cv2.polylines(frame, [pix], True, (18, 18, 22), 2, lineType=cv2.LINE_AA)


def _viz_topdown_params_for_pkl(
    pkl_path: str,
    *,
    road_half_width_m: Optional[float] = None,
    dash_len_m: Optional[float] = None,
    dash_gap_m: Optional[float] = None,
) -> Tuple[float, float, float]:
    """Load ``scenario_rollout_config.json`` beside the pkl, then apply CLI overrides."""
    defaults = {"road_half_width_m": 4.0, "dash_len_m": 4.0, "dash_gap_m": 3.5}
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(pkl_path)), "scenario_rollout_config.json")
    merged = dict(defaults)
    if os.path.isfile(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            snap = json.load(f)
        vt = snap.get("viz_topdown") or {}
        for k in defaults:
            if k in vt:
                merged[k] = float(vt[k])
    if road_half_width_m is not None:
        merged["road_half_width_m"] = float(road_half_width_m)
    if dash_len_m is not None:
        merged["dash_len_m"] = float(dash_len_m)
    if dash_gap_m is not None:
        merged["dash_gap_m"] = float(dash_gap_m)
    return merged["road_half_width_m"], merged["dash_len_m"], merged["dash_gap_m"]


def render_topdown_mp4(
    pkl_path: str,
    intersection_csv: Optional[str],
    out_mp4: str,
    *,
    fps: float = 15.0,
    width: int = 1280,
    height: int = 720,
    margin_px: int = 40,
    road_half_width_m: Optional[float] = None,
    dash_len_m: Optional[float] = None,
    dash_gap_m: Optional[float] = None,
) -> str:
    if not os.path.isfile(pkl_path):
        raise FileNotFoundError(pkl_path)

    rhw, dlen, dgap = _viz_topdown_params_for_pkl(
        pkl_path,
        road_half_width_m=road_half_width_m,
        dash_len_m=dash_len_m,
        dash_gap_m=dash_gap_m,
    )

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

    xs: List[float] = []
    ys: List[float] = []
    for _, st, _, _ in trajs:
        xs.extend(st[:, 1].tolist())
        ys.extend(st[:, 2].tolist())
    polylines = _load_intersection_polylines(intersection_csv) if intersection_csv else []
    for xarr, yarr in polylines:
        xs.extend(xarr.tolist())
        ys.extend(yarr.tolist())
        dx = float(xarr[1] - xarr[0])
        dy = float(yarr[1] - yarr[0])
        ln = math.hypot(dx, dy)
        if ln > 1e-6:
            px, py = -dy / ln * rhw, dx / ln * rhw
            for sx, sy in ((float(xarr[0]), float(yarr[0])), (float(xarr[1]), float(yarr[1]))):
                xs.extend([sx + px, sx - px])
                ys.extend([sy + py, sy - py])
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    pad = max(10.0, 0.1 * max(xmax - xmin, ymax - ymin, 1.0))
    bounds = (xmin - pad, xmax + pad, ymin - pad, ymax + pad)

    os.makedirs(os.path.dirname(out_mp4) or ".", exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    vw = cv2.VideoWriter(out_mp4, fourcc, float(fps), (width, height))
    if not vw.isOpened():
        raise RuntimeError(f"Could not open VideoWriter for {out_mp4}")

    asphalt = (62, 62, 66)
    curb = (245, 245, 248)
    yellow_center = (0, 210, 255)

    for fi in range(n_frames):
        frame = np.zeros((height, width, 3), dtype=np.uint8)
        frame[:, :] = (214, 212, 208)

        for xarr, yarr in polylines:
            _draw_road_corridor(
                frame,
                xarr,
                yarr,
                bounds,
                width,
                height,
                margin_px,
                rhw,
                asphalt,
                curb,
                yellow_center,
                dlen,
                dgap,
            )

        order = sorted(range(len(trajs)), key=lambda i: 1 if "ego" in trajs[i][0] else 0)
        for idx in order:
            key, st, lf, lr = trajs[idx]
            row = st[min(fi, st.shape[0] - 1)]
            x, y, yaw = float(row[1]), float(row[2]), float(row[3])
            L, Wb = _bbox_for_actor(lf, lr)
            _draw_vehicle_styled(
                frame,
                x,
                y,
                yaw,
                lf,
                lr,
                L,
                Wb,
                bounds,
                width,
                height,
                margin_px,
                key,
            )

        t_sim = float(trajs[0][1][min(fi, trajs[0][1].shape[0] - 1), 0])
        cv2.rectangle(frame, (0, 0), (width, 46), (240, 238, 235), -1)
        cv2.putText(
            frame,
            f"frame {fi + 1}/{n_frames}   t = {t_sim:.2f} s",
            (16, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            (40, 40, 45),
            2,
            lineType=cv2.LINE_AA,
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
    ap.add_argument(
        "--road_half_width_m",
        type=float,
        default=None,
        help="Override half road width (m). If omitted, use scenario_rollout_config.json next to --pkl, else built-in default.",
    )
    ap.add_argument(
        "--dash_len_m",
        type=float,
        default=None,
        help="Override center-line dash length (m); omitted = from rollout config / default.",
    )
    ap.add_argument(
        "--dash_gap_m",
        type=float,
        default=None,
        help="Override gap between dashes (m); omitted = from rollout config / default.",
    )
    args = ap.parse_args()

    out = args.out or os.path.join(os.path.dirname(os.path.abspath(args.pkl)), "rollout_topdown.mp4")
    path = render_topdown_mp4(
        args.pkl,
        args.intersection_csv,
        out,
        fps=args.fps,
        width=args.width,
        height=args.height,
        road_half_width_m=args.road_half_width_m,
        dash_len_m=args.dash_len_m,
        dash_gap_m=args.dash_gap_m,
    )
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
