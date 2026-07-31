#!/usr/bin/env python3
"""Day 5 development audit and reactive-parameter freeze gate.

This audit is intentionally stricter than the Day 4 data-chain smoke.  It
requires the complete init01-05 2x2 development matrix, validates every logged
model input, measures reactive state-machine quality and safety at simulator
rate, and quantifies paired S1-vs-S0 target-trajectory separation.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np

from interaction_sequence import assert_logged_feature_equivalence
from prediction_input_contract import load_logged_raster, raster_array_sha256
from verify_prediction_input_contract import REQUIRED_V2_FIELDS


EXPECTED_CELLS = {
    "S0_FIXED": ("assertive_constant_speed", "fixed_medium"),
    "S0_ADAPTIVE": ("assertive_constant_speed", "adaptive_floor_weak"),
    "S1_FIXED": ("defensive_reactive", "fixed_medium"),
    "S1_ADAPTIVE": ("defensive_reactive", "adaptive_floor_weak"),
}
EXPECTED_INITS = set(range(1, 6))
ADAPTIVE_RISK_CONFIG = {
    "variant_name": "floor_weak",
    "approach_preclearance_floor": 1.66,
    "critical_preclearance_floor": 1.72,
    "near_preclearance_floor": 1.78,
}
FROZEN_REACTIVE_PARAMETER_KEYS = (
    "controller",
    "nominal_speed_mps",
    "caution_speed_mps",
    "minimum_speed_mps",
    "activation_distance_m",
    "release_clearance_m",
    "arrival_time_gap_s",
    "closest_approach_time_s",
    "closest_approach_distance_m",
    "release_hold_s",
    "max_accel_mps2",
    "max_decel_mps2",
    "conflict_geometry",
    "episode_semantics",
    "hazard_combination",
)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--frozen-config-json")
    parser.add_argument("--expected-git-commit")
    return parser.parse_args()


def read_jsonl(path):
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def as_bool(value):
    return str(value).strip().lower() in {"1", "true", "yes"}


def as_float(value, default=np.nan):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def canonical_hash(payload):
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_reactive_parameters(parameters):
    """Keep behavior-defining values; exclude rollout-specific geometry values."""

    return {
        key: parameters[key]
        for key in FROZEN_REACTIVE_PARAMETER_KEYS
        if key in parameters
    }


def count_transitions(values):
    values = np.asarray(values)
    return int(np.sum(values[1:] != values[:-1])) if len(values) >= 2 else 0


def load_full_rate_clearance(subrun_dir):
    pkl_path = subrun_dir / "scenario_result.pkl"
    with pkl_path.open("rb") as handle:
        result = pickle.load(handle)
    ego_keys = [key for key in result if key.startswith("ego_")]
    target_keys = [key for key in result if key.startswith("target_")]
    if len(ego_keys) != 1 or len(target_keys) != 1:
        raise ValueError(f"unexpected actors in {pkl_path}")
    ego = np.asarray(result[ego_keys[0]]["state_trajectory"], dtype=float)
    target = np.asarray(result[target_keys[0]]["state_trajectory"], dtype=float)
    count = min(len(ego), len(target))
    if count == 0:
        return None
    # scenario_result state rows are [timestamp, x_rhs, y_rhs, yaw, speed].
    return float(
        np.min(np.linalg.norm(ego[:count, 1:3] - target[:count, 1:3], axis=1))
    )


def step_metrics(step_csv):
    with step_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    time = np.asarray([as_float(row.get("sim_time_s")) for row in rows], dtype=float)
    speed = np.asarray([as_float(row.get("target0_speed")) for row in rows], dtype=float)
    x = np.asarray([as_float(row.get("target0_x")) for row in rows], dtype=float)
    y = np.asarray([as_float(row.get("target0_y_rhs")) for row in rows], dtype=float)
    throttle = np.asarray(
        [as_float(row.get("target0_throttle"), 0.0) for row in rows], dtype=float
    )
    brake = np.asarray(
        [as_float(row.get("target0_brake"), 0.0) for row in rows], dtype=float
    )
    active = np.asarray(
        [as_bool(row.get("target0_reactive_active")) for row in rows], dtype=bool
    )
    desired_speed = np.asarray(
        [as_float(row.get("target0_reactive_desired_speed_mps")) for row in rows],
        dtype=float,
    )
    triggers = sum(as_bool(row.get("target0_reactive_triggered_this_step")) for row in rows)
    releases = sum(as_bool(row.get("target0_reactive_released_this_step")) for row in rows)
    trigger_indices = [
        idx
        for idx, row in enumerate(rows)
        if as_bool(row.get("target0_reactive_triggered_this_step"))
    ]
    valid = np.isfinite(time) & np.isfinite(speed)
    acceleration = np.asarray([], dtype=float)
    jerk = np.asarray([], dtype=float)
    if np.sum(valid) >= 3:
        vt, vv = time[valid], speed[valid]
        dt = np.diff(vt)
        good = dt > 1.0e-6
        acceleration = np.diff(vv)[good] / dt[good]
        if len(acceleration) >= 2:
            accel_time = vt[1:][good]
            adt = np.diff(accel_time)
            good_jerk = adt > 1.0e-6
            jerk = np.diff(acceleration)[good_jerk] / adt[good_jerk]
    control_mode = np.where(brake > 0.05, -1, np.where(throttle > 0.05, 1, 0))
    compressed_control_mode = []
    for value in control_mode:
        value = int(value)
        if not compressed_control_mode or value != compressed_control_mode[-1]:
            compressed_control_mode.append(value)
    direct_control_reversals = sum(
        left * right == -1
        for left, right in zip(
            compressed_control_mode, compressed_control_mode[1:]
        )
    )
    finite_desired_speed = desired_speed[np.isfinite(desired_speed)]
    return {
        "rows": len(rows),
        "trigger_count": int(triggers),
        "release_count": int(releases),
        "active_steps": int(np.sum(active)),
        "active_fraction": float(np.mean(active)) if len(active) else 0.0,
        "active_state_transition_count": count_transitions(active),
        "desired_speed_transition_count": (
            count_transitions(np.round(finite_desired_speed, 6))
            if len(finite_desired_speed)
            else None
        ),
        "simultaneous_throttle_brake_steps": int(
            np.sum((throttle > 0.05) & (brake > 0.05))
        ),
        "control_mode_transition_count": count_transitions(control_mode),
        "direct_propulsion_braking_reversal_count": int(
            direct_control_reversals
        ),
        "trigger_onset_s": (
            float(time[trigger_indices[0]] - time[0]) if trigger_indices else None
        ),
        "minimum_speed_mps": float(np.nanmin(speed)) if len(speed) else None,
        "final_speed_mps": float(speed[-1]) if len(speed) else None,
        "minimum_active_speed_mps": (
            float(np.nanmin(speed[active])) if np.any(active) else None
        ),
        "maximum_abs_acceleration_mps2": (
            float(np.nanmax(np.abs(acceleration))) if len(acceleration) else None
        ),
        "p99_abs_jerk_mps3": (
            float(np.nanpercentile(np.abs(jerk), 99)) if len(jerk) else None
        ),
        "time": time,
        "speed": speed,
        "xy": np.column_stack([x, y]),
    }


def paired_separation(s0, s1):
    valid0 = np.isfinite(s0["time"]) & np.all(np.isfinite(s0["xy"]), axis=1)
    valid1 = np.isfinite(s1["time"]) & np.all(np.isfinite(s1["xy"]), axis=1)
    t0, xy0 = s0["time"][valid0], s0["xy"][valid0]
    t1, xy1 = s1["time"][valid1], s1["xy"][valid1]
    if len(t0) < 2 or len(t1) < 2:
        raise ValueError("insufficient paired target trajectory")
    # CARLA elapsed_seconds is global to the server and therefore differs
    # between sequential rollouts.  Pair trajectories by time since each
    # rollout's first logged control step, not by absolute simulator uptime.
    t0 = t0 - t0[0]
    t1 = t1 - t1[0]
    lo, hi = max(t0[0], t1[0]), min(t0[-1], t1[-1])
    mask = (t0 >= lo) & (t0 <= hi)
    t = t0[mask]
    if len(t) == 0:
        raise ValueError("paired target trajectories have no relative-time overlap")
    interpolated = np.column_stack(
        [np.interp(t, t1, xy1[:, axis]) for axis in range(2)]
    )
    distance = np.linalg.norm(xy0[mask] - interpolated, axis=1)
    return {
        "mean_target_position_separation_m": float(np.mean(distance)),
        "max_target_position_separation_m": float(np.max(distance)),
        "final_common_target_position_separation_m": float(distance[-1]),
        "common_steps": int(len(distance)),
        "maximum_speed_reduction_mps": float(
            np.nanmax(s0["speed"]) - np.nanmin(s1["speed"])
        ),
    }


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def main():
    args = parse_args()
    root = Path(args.results_dir).expanduser().resolve()
    manifests = sorted(root.glob("**/prediction_dataset/prediction_dataset_manifest.json"))
    errors = []
    rollouts = {}
    parameter_sets = []
    observed_collection_contracts = []
    contract_samples = 0

    for manifest_path in manifests:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metadata = manifest.get("dataset_metadata", {})
        cell = metadata.get("cell_id")
        init_id = int(metadata.get("ego_init_id"))
        key = (cell, init_id)
        if cell not in EXPECTED_CELLS or init_id not in EXPECTED_INITS:
            errors.append(f"{manifest_path}: unexpected cell/init {key}")
            continue
        if key in rollouts:
            errors.append(f"duplicate rollout {key}")
            continue
        expected_target, expected_ego = EXPECTED_CELLS[cell]
        observed_collection_contracts.append(
            {
                "dataset_version": metadata.get("dataset_version"),
                "protocol_id": metadata.get("protocol_id"),
                "git_commit": metadata.get("git_commit"),
                "feature_schema_id": manifest.get("feature_schema_id"),
                "model_weights": manifest.get("model_weights"),
                "model_anchors": manifest.get("model_anchors"),
                "prediction_logging_stride": manifest.get("stride"),
                "prediction_logging_horizon": manifest.get("horizon"),
                "prediction_logging_save_raster": manifest.get("save_raster"),
                "dt_s": manifest.get("dt"),
            }
        )
        if metadata.get("target_style") != expected_target:
            errors.append(f"{manifest_path}: target style mismatch")
        if metadata.get("ego_policy") != expected_ego:
            errors.append(f"{manifest_path}: ego policy mismatch")
        if args.expected_git_commit and metadata.get("git_commit") != args.expected_git_commit:
            errors.append(f"{manifest_path}: git commit mismatch")

        dataset_dir = manifest_path.parent
        labeled_path = dataset_dir / manifest["labeled_jsonl"]
        samples = list(read_jsonl(labeled_path))
        if not samples:
            errors.append(f"{labeled_path}: no samples")
        for sample in samples:
            contract_samples += 1
            missing = sorted(REQUIRED_V2_FIELDS - set(sample))
            if missing:
                errors.append(f"{labeled_path}: missing fields {missing}")
                continue
            try:
                assert_logged_feature_equivalence(sample)
                raster_path = dataset_dir / sample["raster_relpath"]
                observed = raster_array_sha256(load_logged_raster(str(raster_path)))
                if observed != sample.get("raster_uint8_sha256"):
                    errors.append(f"{raster_path}: raster hash mismatch")
            except Exception as exc:
                errors.append(f"{labeled_path}: {exc}")
        if cell.startswith("S1") and samples:
            parameter_sets.append(
                freeze_reactive_parameters(
                    samples[0].get("target_style_parameters", {})
                )
            )

        subrun_dir = dataset_dir.parent
        step = step_metrics(subrun_dir / "scenario_steps.csv")
        summary_path = subrun_dir / "scenario_run_summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary_extra = summary.get("extra", {})
        step["collision_event_count"] = int(
            summary_extra.get("collision_event_count", -1)
        )
        if step["collision_event_count"] < 0:
            errors.append(f"{summary_path}: native collision evidence missing")
        try:
            clearance = load_full_rate_clearance(subrun_dir)
        except Exception as exc:
            clearance = None
            errors.append(f"{subrun_dir}: clearance audit failed: {exc}")
        step["minimum_ego_target_centroid_clearance_m"] = clearance
        rollouts[key] = step

    expected_keys = {(cell, init_id) for cell in EXPECTED_CELLS for init_id in EXPECTED_INITS}
    missing = sorted(expected_keys - set(rollouts))
    if missing:
        errors.append(f"missing development rollouts: {missing}")

    reactive = [value for (cell, _), value in rollouts.items() if cell.startswith("S1")]
    trigger_coverage = (
        sum(item["trigger_count"] > 0 for item in reactive) / len(reactive)
        if reactive
        else 0.0
    )
    active_fractions = [item["active_fraction"] for item in reactive]
    triggered_reactive = [item for item in reactive if item["trigger_count"] > 0]
    trigger_onsets = [
        item["trigger_onset_s"]
        for item in triggered_reactive
        if item["trigger_onset_s"] is not None
    ]
    min_speeds = [item["minimum_speed_mps"] for item in reactive if item["minimum_speed_mps"] is not None]
    clearances = [
        item["minimum_ego_target_centroid_clearance_m"]
        for item in rollouts.values()
        if item["minimum_ego_target_centroid_clearance_m"] is not None
    ]
    paired = []
    for suffix in ("FIXED", "ADAPTIVE"):
        for init_id in sorted(EXPECTED_INITS):
            k0, k1 = (f"S0_{suffix}", init_id), (f"S1_{suffix}", init_id)
            if k0 in rollouts and k1 in rollouts:
                result = paired_separation(rollouts[k0], rollouts[k1])
                result.update({"ego_policy": suffix.lower(), "ego_init_id": init_id})
                paired.append(result)

    unique_parameter_hashes = {
        canonical_hash(value) for value in parameter_sets if value
    }
    unique_collection_contracts = {
        canonical_hash(value): value for value in observed_collection_contracts
    }
    gates = {
        "complete_20_rollout_matrix": len(rollouts) == 20 and not missing,
        "all_logged_inputs_equivalent": not any(
            "missing fields" in item
            or "raster hash" in item
            or "interaction" in item
            for item in errors
        ),
        "reactive_trigger_rollout_coverage_20_to_80_pct": 0.2 <= trigger_coverage <= 0.8,
        "reactive_active_fraction_5_to_35_pct": bool(active_fractions)
        and 0.05 <= float(np.mean(active_fractions)) <= 0.35,
        "single_trigger_per_reactive_rollout": all(
            item["trigger_count"] <= 1 and item["release_count"] <= 1
            for item in reactive
        ),
        "trigger_release_events_paired": all(
            item["trigger_count"] == item["release_count"] for item in reactive
        ),
        "reactive_command_has_single_down_up_cycle": all(
            item["active_state_transition_count"]
            == (2 if item["trigger_count"] else 0)
            and item["desired_speed_transition_count"]
            == (2 if item["trigger_count"] else 0)
            for item in reactive
        ),
        "target_control_never_overlaps_throttle_and_brake": bool(rollouts)
        and all(
            item["simultaneous_throttle_brake_steps"] == 0
            for item in rollouts.values()
        ),
        "target_control_has_no_direct_propulsion_braking_reversal": bool(rollouts)
        and all(
            item["direct_propulsion_braking_reversal_count"] == 0
            for item in rollouts.values()
        ),
        "reactive_trigger_not_immediate": bool(trigger_onsets)
        and min(trigger_onsets) >= 0.2,
        "reactive_trigger_timing_varies": len(trigger_onsets) >= 2
        and max(trigger_onsets) - min(trigger_onsets) >= 0.05,
        "no_reactive_rollout_always_active": bool(reactive)
        and max(active_fractions) <= 0.35,
        "target_never_stops_min_speed_gt_2_5_mps": bool(min_speeds)
        and min(min_speeds) > 2.5,
        "target_recovers_final_speed_ge_8_0_mps": bool(reactive)
        and all(
            item["final_speed_mps"] is not None and item["final_speed_mps"] >= 8.0
            for item in reactive
        ),
        "full_rate_centroid_clearance_gt_3_0_m": bool(clearances)
        and min(clearances) > 3.0,
        "native_carla_collision_event_count_zero": bool(rollouts)
        and all(item.get("collision_event_count") == 0 for item in rollouts.values()),
        "paired_s1_s0_separation_gt_0_5_m": bool(paired)
        and float(np.median([item["max_target_position_separation_m"] for item in paired]))
        > 0.5,
        "one_reactive_parameter_set": len(unique_parameter_hashes) == 1,
        "one_observed_collection_contract": len(unique_collection_contracts) == 1,
    }
    status = "pass" if all(gates.values()) and not errors else "fail"
    frozen_parameters = parameter_sets[0] if len(unique_parameter_hashes) == 1 else None
    report = {
        "audit_schema_version": "prediction_dataset_v2_day5_audit_v2",
        "status": status,
        "results_dir": str(root),
        "rollout_count": len(rollouts),
        "contract_sample_count": contract_samples,
        "reactive_summary": {
            "trigger_rollout_coverage": trigger_coverage,
            "mean_active_fraction": float(np.mean(active_fractions)) if active_fractions else None,
            "minimum_target_speed_mps": min(min_speeds) if min_speeds else None,
            "maximum_trigger_count_per_rollout": max(
                [item["trigger_count"] for item in reactive], default=None
            ),
            "trigger_onset_s": trigger_onsets,
            "trigger_onset_range_s": (
                max(trigger_onsets) - min(trigger_onsets)
                if len(trigger_onsets) >= 2
                else None
            ),
            "maximum_control_mode_transitions": max(
                [item["control_mode_transition_count"] for item in reactive],
                default=None,
            ),
            "simultaneous_throttle_brake_steps": sum(
                item["simultaneous_throttle_brake_steps"]
                for item in reactive
            ),
            "direct_propulsion_braking_reversals": sum(
                item["direct_propulsion_braking_reversal_count"]
                for item in reactive
            ),
            "kinematic_interpretation": (
                "Finite-difference acceleration and jerk include 20 Hz CARLA "
                "wheel-speed fluctuations shared by S0 and S1, so actuator "
                "mutual exclusion and state/desired-speed transitions are the "
                "primary anti-chattering evidence."
            ),
        },
        "safety_summary": {
            "native_carla_collision_event_count": sum(
                max(0, item.get("collision_event_count", 0))
                for item in rollouts.values()
            ),
            "minimum_full_rate_ego_target_centroid_clearance_m": (
                min(clearances) if clearances else None
            ),
            "interpretation": (
                "Native CARLA collision events are the primary gate; full-rate "
                "centroid clearance is a secondary proximity diagnostic."
            ),
        },
        "paired_s1_s0_separation": paired,
        "frozen_reactive_parameters": frozen_parameters,
        "frozen_reactive_parameters_sha256": (
            canonical_hash(frozen_parameters) if frozen_parameters else None
        ),
        "observed_collection_contract": (
            next(iter(unique_collection_contracts.values()))
            if len(unique_collection_contracts) == 1
            else None
        ),
        "gates": gates,
        "rollouts": {
            f"{cell}_init_{init_id:02d}": json_safe(
                {key: value for key, value in metrics.items() if key not in {"time", "speed", "xy"}}
            )
            for (cell, init_id), metrics in sorted(rollouts.items())
        },
        "errors": errors[:100],
    }
    output = Path(args.output_json).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if args.frozen_config_json and status == "pass":
        scripts_dir = Path(__file__).resolve().parent.parent
        carla_dir = scripts_dir / "carla"
        scenario_dir = carla_dir / "scenarios"
        init_paths = sorted(
            (scenario_dir / "inits" / "paper_intersection_50").glob(
                "ego_init_*.json"
            )
        )
        if len(init_paths) != 50:
            raise ValueError(f"Expected 50 formal init files, found {len(init_paths)}")
        source_artifacts = {
            "collection_runner": carla_dir / "run_give_way_prediction_dataset_v2.sh",
            "batch_runner": carla_dir / "run_all_scenarios.py",
            "scenario_runner": scenario_dir / "run_intersection_scenario.py",
            "scenario": scenario_dir / "scenario_uk_give_way.json",
            "intersection_geometry": scenario_dir / "intersection_01.csv",
            "tuning_config": scenario_dir
            / "tuning_configs"
            / "give_way_reduced_clear_path_release_v12_current_best.json",
            "reactive_target_agent": carla_dir
            / "policies"
            / "defensive_reactive_agent.py",
            "straight_line_target_agent": carla_dir
            / "policies"
            / "straight_line_agent.py",
            "agent_history_rasterizer": carla_dir
            / "rasterizer"
            / "agent_history.py",
            "prediction_deployment": scripts_dir
            / "models"
            / "deploy_multipath_model.py",
            "interaction_sequence": scripts_dir
            / "models"
            / "interaction_sequence.py",
            "prediction_input_contract": scripts_dir
            / "models"
            / "prediction_input_contract.py",
            "gmm_prediction": scripts_dir
            / "evaluation"
            / "gmm_prediction.py",
        }
        source_artifact_sha256 = {
            name: file_sha256(path) for name, path in source_artifacts.items()
        }
        formal_init_set = [
            {"filename": path.name, "sha256": file_sha256(path)}
            for path in init_paths
        ]
        collection_configuration = {
            "dataset_version": observed_collection_contracts[0][
                "dataset_version"
            ],
            "protocol_id": observed_collection_contracts[0]["protocol_id"],
            "development_git_commit": observed_collection_contracts[0]["git_commit"],
            "scenario": "scenario_uk_give_way.json",
            "map": "Town05",
            "formal_init_ids": [1, 50],
            "cells": EXPECTED_CELLS,
            "expected_rollouts": 200,
            "prediction_contract": next(
                iter(unique_collection_contracts.values())
            ),
            "adaptive_risk_config": ADAPTIVE_RISK_CONFIG,
            "reactive_parameters": frozen_parameters,
            "source_artifact_sha256": source_artifact_sha256,
            "formal_init_set_sha256": canonical_hash(formal_init_set),
        }
        frozen = {
            "freeze_schema_version": "give_way_v2_day5_collection_freeze_v1",
            "source_audit": str(output),
            "source_results_dir": str(root),
            "development_init_ids": sorted(EXPECTED_INITS),
            "reactive_parameters": frozen_parameters,
            "reactive_parameters_sha256": canonical_hash(frozen_parameters),
            "collection_configuration": collection_configuration,
            "formal_collection_matrix": {
                "init_ids": [1, 50],
                "cells": list(EXPECTED_CELLS),
                "expected_rollouts": 200,
            },
            "immutable_after_freeze": True,
        }
        frozen["collection_config_sha256"] = canonical_hash(
            collection_configuration
        )
        frozen_path = Path(args.frozen_config_json).expanduser().resolve()
        frozen_path.parent.mkdir(parents=True, exist_ok=True)
        frozen_path.write_text(json.dumps(frozen, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
