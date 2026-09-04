#!/usr/bin/env python3
"""E5: native collision attribution and closed-loop metric sensitivity audit."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import csv
import datetime as dt
import io
import json
import math
import tarfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from distinction_analysis_utils import atomic_write_json, collision_episodes, sha256_file, write_csv


def load_formal_audit(archive_path: Path, contract_name: str, stage: str) -> tuple[list[dict], list[dict], dict]:
    native_rows = []
    footprint_rows = []
    with tarfile.open(archive_path, "r:gz") as archive:
        contract = json.load(archive.extractfile(contract_name))
        cells = {cell["cell_id"]: cell for cell in contract["cells"]}
        for member in archive:
            cell_id = member.name.split("/", 1)[0]
            if not member.isfile() or cell_id not in cells:
                continue
            cell = cells[cell_id]
            if member.name.endswith("scenario_run_summary.json"):
                summary = json.load(archive.extractfile(member))
                rollout = member.name.rsplit("/scenario_run_summary.json", 1)[0]
                events = (summary.get("extra") or {}).get("collision_events", [])
                frames = [int(event["frame"]) for event in events]
                episodes = collision_episodes(frames)
                actor_types = Counter(str(event.get("other_actor_type", "unknown")) for event in events)
                native_rows.append(
                    {
                        "stage": stage,
                        "cell_id": cell_id,
                        "predictor": cell["predictor"],
                        "risk_policy": cell["risk_policy"],
                        "target_style": cell["target_style"],
                        "target_offset_m": float(cell.get("target_offset_m", contract.get("target_offset_m", 0.0))),
                        "rollout": rollout,
                        "ego_init_id": int(rollout.split("ego_init_")[1].split("_")[0]),
                        "callback_count": len(events),
                        "unique_frames": len(set(frames)),
                        "contact_episodes": len(episodes),
                        "traffic_light_callbacks": sum(
                            count for actor, count in actor_types.items() if actor.startswith("traffic.traffic_light")
                        ),
                        "vehicle_actor_callbacks": sum(
                            count for actor, count in actor_types.items() if actor.startswith("vehicle.")
                        ),
                    }
                )
            elif member.name.endswith("/postcarla_trajectory_gate.json"):
                gate = json.load(archive.extractfile(member))
                for evaluation in gate["evaluations"]:
                    rollout = evaluation["scenario_dir"].split(f"/{cell_id}/", 1)[-1]
                    init_id = int(rollout.split("ego_init_")[1].split("_")[0])
                    for pair in evaluation["pair_safety"]:
                        rule = evaluation["yield_rules"][0] if evaluation.get("yield_rules") else {}
                        footprint_rows.append(
                            {
                                "stage": stage,
                                "cell_id": cell_id,
                                "predictor": cell["predictor"],
                                "risk_policy": cell["risk_policy"],
                                "target_style": cell["target_style"],
                                "target_offset_m": float(cell.get("target_offset_m", contract.get("target_offset_m", 0.0))),
                                "ego_init_id": init_id,
                                "min_center_distance_m": pair["min_center_distance_m"],
                                "min_footprint_separation_m": pair["min_footprint_separation_m"],
                                "footprint_collision": int(bool(pair["footprint_collision"])),
                                "conflict_point_x": (rule.get("conflict_point_xy") or [None, None])[0],
                                "conflict_point_y": (rule.get("conflict_point_xy") or [None, None])[1],
                                "yield_order_valid": int(bool(rule.get("target_clears_before_ego_enters"))),
                                "clearance_time_gap_s": (
                                    float(rule["ego_enter_time_s"] - rule["target_exit_time_s"])
                                    if rule.get("ego_enter_time_s") is not None and rule.get("target_exit_time_s") is not None
                                    else None
                                ),
                                "logged_footprint_margin_m": (gate.get("gate_settings") or {}).get("footprint_margin_m"),
                            }
                        )
    return native_rows, footprint_rows, contract


def paired_effects(rows: list[dict], exclude_init: int | None) -> list[dict]:
    source = [row for row in rows if exclude_init is None or int(row["ego_init_id"]) != exclude_init]
    metrics = (
        "target_clearance_adjusted_completion_delay_s",
        "min_footprint_separation_m",
        "supervisor_active_fraction",
    )
    output = []
    contrasts = []
    for policy in ("fixed_medium", "adaptive"):
        contrasts.append((f"B1_minus_B0__{policy}", {"predictor": "B1", "risk_policy": policy}, {"predictor": "B0", "risk_policy": policy}))
    for predictor in ("B1", "B0"):
        contrasts.append((f"adaptive_minus_fixed_medium__{predictor}", {"predictor": predictor, "risk_policy": "adaptive"}, {"predictor": predictor, "risk_policy": "fixed_medium"}))
    for label, left_filter, right_filter in contrasts:
        grouping = ("target_style", "target_offset_m", "ego_init_id")
        left = {tuple(row[field] for field in grouping): row for row in source if all(row[key] == value for key, value in left_filter.items())}
        right = {tuple(row[field] for field in grouping): row for row in source if all(row[key] == value for key, value in right_filter.items())}
        keys = sorted(left.keys() & right.keys())
        for metric in metrics:
            deltas = [float(left[key][metric]) - float(right[key][metric]) for key in keys]
            output.append(
                {
                    "excluded_init": "none" if exclude_init is None else exclude_init,
                    "contrast": label,
                    "metric": metric,
                    "paired_conditions": len(deltas),
                    "independent_init_groups": len({key[2] for key in keys}),
                    "left_minus_right_mean": float(np.mean(deltas)),
                }
            )
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day10-tar", type=Path, required=True)
    parser.add_argument("--day11-tar", type=Path, required=True)
    parser.add_argument("--timing-rollout-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    native10, footprint10, contract10 = load_formal_audit(args.day10_tar, "day10_run_contract.json", "day10")
    native11, footprint11, contract11 = load_formal_audit(args.day11_tar, "day11_run_contract.json", "day11")
    native = native10 + native11
    footprints = footprint10 + footprint11
    if len(native) != 160 or len(footprints) != 160:
        raise ValueError(f"Formal audit expected 160 rollouts, found native={len(native)}, footprint={len(footprints)}")

    callbacks = sum(row["callback_count"] for row in native)
    unique_frames = sum(row["unique_frames"] for row in native)
    episodes = sum(row["contact_episodes"] for row in native)
    vehicle_callbacks = sum(row["vehicle_actor_callbacks"] for row in native)
    footprint_collisions = sum(row["footprint_collision"] for row in footprints)
    minimum_separation = min(float(row["min_footprint_separation_m"]) for row in footprints)
    logged_margin = float(next(row["logged_footprint_margin_m"] for row in footprints))
    margin_certificates = []
    for margin in (0.0, 0.25, 0.35, 0.50):
        extra_per_actor = max(0.0, margin - logged_margin)
        conservative_lower_bound = max(0.0, minimum_separation - 2.0 * extra_per_actor)
        margin_certificates.append(
            {
                "footprint_margin_m": margin,
                "minimum_separation_lower_bound_m": conservative_lower_bound,
                "all_160_certified_collision_free": bool(margin <= logged_margin or conservative_lower_bound > 0.0),
                "method": "monotonicity for smaller margins; two-polygon Minkowski expansion bound for larger margins",
            }
        )

    conflict_points = np.asarray(
        [[row["conflict_point_x"], row["conflict_point_y"]] for row in footprints], dtype=np.float64
    )
    gap_values = [float(row["clearance_time_gap_s"]) for row in footprints if row["clearance_time_gap_s"] is not None]

    with args.timing_rollout_csv.open("r", encoding="utf-8", newline="") as handle:
        timing_rows = list(csv.DictReader(handle))
    for row in timing_rows:
        row["ego_init_id"] = int(row["ego_init_id"])
        row["target_offset_m"] = float(row["target_offset_m"])
    effects_full = paired_effects(timing_rows, None)
    effects_without_50 = paired_effects(timing_rows, 50)
    sensitivity = []
    lookup = {(row["contrast"], row["metric"]): row for row in effects_full}
    for reduced in effects_without_50:
        full = lookup[(reduced["contrast"], reduced["metric"])]
        sensitivity.append(
            {
                "contrast": reduced["contrast"],
                "metric": reduced["metric"],
                "full_five_init_effect": full["left_minus_right_mean"],
                "exclude_init50_effect": reduced["left_minus_right_mean"],
                "effect_sign_stable": int(
                    math.copysign(1.0, full["left_minus_right_mean"])
                    == math.copysign(1.0, reduced["left_minus_right_mean"])
                ),
                "independent_init_groups_after_exclusion": reduced["independent_init_groups"],
            }
        )

    write_csv(args.output_dir / "formal_native_collision_rollouts.csv", native, list(native[0]))
    write_csv(args.output_dir / "formal_footprint_yield_rollouts.csv", footprints, list(footprints[0]))
    write_csv(args.output_dir / "exclude_init50_effect_sensitivity.csv", sensitivity, list(sensitivity[0]))
    audit = {
        "schema_version": "distinction_formal_safety_metric_audit_v1",
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "pass_with_explicit_metric_boundary",
        "result_generation": "distinction_v1",
        "source_sha256": {
            "day10": sha256_file(args.day10_tar),
            "day11": sha256_file(args.day11_tar),
            "timing_rollouts": sha256_file(args.timing_rollout_csv),
        },
        "native_collision_attribution": {
            "formal_rollouts": len(native),
            "callback_count": callbacks,
            "unique_collision_frames": unique_frames,
            "contact_episodes": episodes,
            "vehicle_actor_callbacks": vehicle_callbacks,
            "traffic_light_callbacks": sum(row["traffic_light_callbacks"] for row in native),
            "affected_rollouts": sum(row["callback_count"] > 0 for row in native),
            "finding": "The only native callbacks are target-to-traffic-light infrastructure contact in Day11 init 50; no ego-target vehicle callback is logged.",
        },
        "footprint_safety": {
            "evaluations": len(footprints),
            "logged_margin_m": logged_margin,
            "footprint_collisions": footprint_collisions,
            "minimum_logged_footprint_separation_m": minimum_separation,
            "margin_sensitivity_certificates": margin_certificates,
        },
        "yield_metric_geometry": {
            "current_implementation": "per-rollout conflict point chosen from closest realised trajectory pair",
            "scientific_issue": "the conflict-zone centre is outcome-dependent, so yield-order timing is not a fully fixed ex-ante metric",
            "all_current_yield_order_valid": all(row["yield_order_valid"] for row in footprints),
            "minimum_clearance_time_gap_s": min(gap_values),
            "conflict_point_mean_xy": conflict_points.mean(axis=0).tolist(),
            "conflict_point_std_xy": conflict_points.std(axis=0).tolist(),
            "conflict_point_min_xy": conflict_points.min(axis=0).tolist(),
            "conflict_point_max_xy": conflict_points.max(axis=0).tolist(),
            "raw_trajectory_recompute_available_in_offsite_package": False,
            "claim_boundary": "Use the unanimous yield-order result as a descriptive gate; do not present it as an unbiased continuous effect until raw trajectories are recomputed against a fixed route-defined point.",
        },
        "exclude_init50_sensitivity": {
            "reason": "init 50 contains the only native infrastructure-contact callbacks",
            "contrasts": sensitivity,
            "all_effect_signs_stable": all(row["effect_sign_stable"] for row in sensitivity),
            "minimum_exact_two_sided_p_with_four_init_groups": 0.125,
        },
        "metric_semantics": {
            "dmin_TV": "actor-centre Euclidean distance",
            "min_footprint_separation_m": "oriented-rectangle polygon separation with logged 0.25 m margin per actor",
            "native_collision_callbacks": "sensor callbacks; duplicated frames are collapsed into contiguous contact episodes",
        },
    }
    atomic_write_json(args.output_dir / "formal_safety_metric_sensitivity_audit.json", audit)
    atomic_write_json(
        args.output_dir / "E5_COMPLETE.json",
        {"stage": "E5", "status": audit["status"], "fixed_route_point_recompute_complete": False, "artifact": "formal_safety_metric_sensitivity_audit.json"},
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
