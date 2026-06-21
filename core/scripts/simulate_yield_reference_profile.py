#!/usr/bin/env python3
"""Simulate the rule-aware yield-line reference speed profile.

This is a CARLA-free local check for the pre-solve reference shaping used by
``SMPCAgent`` during ``hold_yield_line``. It compares the old hard cap
(``v_ref = yield_stop_speed`` everywhere) with the smoother braking-distance
profile. The optimisation reference uses ``yield_reference_min_speed`` as its
minimum speed; the lower ``yield_stop_speed`` is still used by the final
near-stop control override.

    v_cap(d) = sqrt(v_ref_min^2 + 2 * |a_ref| * d_remaining)

where ``d_remaining`` is the path distance remaining to the yield line.
"""

import argparse
import csv
import math
from typing import Iterable, List, Optional


def _parse_distances(raw: str) -> List[float]:
    values = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        value = float(item)
        if value < 0.0:
            raise argparse.ArgumentTypeError("path distances must be non-negative")
        values.append(value)
    if not values:
        raise argparse.ArgumentTypeError("at least one path distance is required")
    if values[0] != 0.0:
        values.insert(0, 0.0)
    if any(b < a for a, b in zip(values, values[1:])):
        raise argparse.ArgumentTypeError("path distances must be sorted ascending")
    return values


def _generated_distances(distance_to_stop: float, horizon_steps: int, ds: float) -> List[float]:
    return [min(i * ds, distance_to_stop) for i in range(max(horizon_steps, 1) + 1)]


def simulate_profile(
    distance_to_stop: float,
    current_speed: float,
    nominal_speed: float,
    yield_stop_speed: float,
    yield_reference_min_speed: float,
    yield_reference_decel: float,
    path_distances: Iterable[float],
):
    max_decel = max(abs(yield_reference_decel), 1e-9)
    rows = []
    previous_profile_speed: Optional[float] = None
    previous_path_s: Optional[float] = None
    for idx, path_s in enumerate(path_distances):
        remaining = max(distance_to_stop - path_s, 0.0)
        smooth_cap = math.sqrt(yield_reference_min_speed ** 2 + 2.0 * max_decel * remaining)
        smooth_cap = max(smooth_cap, yield_reference_min_speed)
        old_hard_cap_speed = yield_stop_speed
        smooth_ref_speed = min(nominal_speed, smooth_cap)
        speed_drop_from_current = max(current_speed - smooth_ref_speed, 0.0)
        implied_decel = None
        if previous_profile_speed is not None and previous_path_s is not None:
            ds = max(path_s - previous_path_s, 1e-9)
            implied_decel = (smooth_ref_speed ** 2 - previous_profile_speed ** 2) / (2.0 * ds)
        rows.append({
            "idx": idx,
            "path_s_m": path_s,
            "remaining_to_stop_m": remaining,
            "old_hard_cap_mps": old_hard_cap_speed,
            "smooth_cap_mps": smooth_cap,
            "smooth_ref_mps": smooth_ref_speed,
            "drop_from_current_mps": speed_drop_from_current,
            "implied_decel_mps2": implied_decel,
        })
        previous_profile_speed = smooth_ref_speed
        previous_path_s = path_s
    return rows


def profile_is_smooth(rows, yield_reference_decel: float, tolerance: float = 1e-6):
    speeds = [row["smooth_ref_mps"] for row in rows]
    monotonic = all(b <= a + tolerance for a, b in zip(speeds, speeds[1:]))
    max_decel = abs(yield_reference_decel)
    decel_ok = True
    for row in rows[1:]:
        implied = row["implied_decel_mps2"]
        if implied is not None and implied < -(max_decel + 1e-5):
            decel_ok = False
            break
    return monotonic and decel_ok, monotonic, decel_ok


def write_csv(path: str, rows) -> None:
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def print_table(rows, yield_reference_decel: float) -> None:
    print("Yield-line reference speed profile simulation")
    print("=" * 72)
    print(
        "idx  path_s  remain  hard_cap  smooth_cap  smooth_ref  implied_decel"
    )
    for row in rows:
        implied = row["implied_decel_mps2"]
        implied_text = "n/a" if implied is None else f"{implied: .3f}"
        print(
            f"{row['idx']:>3d}  "
            f"{row['path_s_m']:>6.2f}  "
            f"{row['remaining_to_stop_m']:>6.2f}  "
            f"{row['old_hard_cap_mps']:>8.2f}  "
            f"{row['smooth_cap_mps']:>10.2f}  "
            f"{row['smooth_ref_mps']:>10.2f}  "
            f"{implied_text:>13}"
        )
    ok, monotonic, decel_ok = profile_is_smooth(rows, yield_reference_decel)
    print()
    print(f"Monotonic non-increasing speed: {monotonic}")
    print(f"Implied deceleration within |a_ref| <= {abs(yield_reference_decel):.2f} m/s^2: {decel_ok}")
    print(f"Profile smoothness check: {'PASS' if ok else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate the braking-distance reference speed profile used in hold_yield_line."
    )
    parser.add_argument("--distance-to-stop", type=float, default=4.51,
                        help="Current path distance to yield stop line in metres.")
    parser.add_argument("--current-speed", type=float, default=5.31,
                        help="Current ego speed in m/s, used for context in CSV output.")
    parser.add_argument("--nominal-speed", type=float, default=6.0,
                        help="Nominal reference speed before applying the braking-distance cap.")
    parser.add_argument("--yield-stop-speed", type=float, default=0.2,
                        help="Near-stop control target speed at the yield line.")
    parser.add_argument("--yield-reference-min-speed", type=float, default=0.8,
                        help="Minimum pre-solve optimisation reference speed during hold_yield_line.")
    parser.add_argument("--yield-reference-decel", type=float, default=-3.0,
                        help="Reference-profile deceleration in m/s^2. Must be negative.")
    parser.add_argument("--horizon-steps", type=int, default=10,
                        help="Number of reference intervals to simulate when --path-distances is omitted.")
    parser.add_argument("--ds", type=float, default=0.5,
                        help="Path-distance spacing in metres when --path-distances is omitted.")
    parser.add_argument("--path-distances", type=_parse_distances, default=None,
                        help="Comma-separated path distances from the current ego pose, e.g. 0,0.7,1.5,2.1.")
    parser.add_argument("--csv", default=None,
                        help="Optional CSV output path.")
    args = parser.parse_args()

    if args.distance_to_stop < 0.0:
        parser.error("--distance-to-stop must be non-negative")
    if args.current_speed < 0.0:
        parser.error("--current-speed must be non-negative")
    if args.nominal_speed < 0.0:
        parser.error("--nominal-speed must be non-negative")
    if args.yield_stop_speed < 0.0:
        parser.error("--yield-stop-speed must be non-negative")
    if args.yield_reference_min_speed < args.yield_stop_speed:
        parser.error("--yield-reference-min-speed must be >= --yield-stop-speed")
    if args.yield_reference_decel >= 0.0:
        parser.error("--yield-reference-decel must be negative")
    if args.ds <= 0.0:
        parser.error("--ds must be positive")

    distances = args.path_distances
    if distances is None:
        distances = _generated_distances(args.distance_to_stop, args.horizon_steps, args.ds)
    rows = simulate_profile(
        distance_to_stop=args.distance_to_stop,
        current_speed=args.current_speed,
        nominal_speed=args.nominal_speed,
        yield_stop_speed=args.yield_stop_speed,
        yield_reference_min_speed=args.yield_reference_min_speed,
        yield_reference_decel=args.yield_reference_decel,
        path_distances=distances,
    )
    print_table(rows, args.yield_reference_decel)
    if args.csv:
        write_csv(args.csv, rows)
        print(f"\nCSV written: {args.csv}")
    ok, _, _ = profile_is_smooth(rows, args.yield_reference_decel)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
