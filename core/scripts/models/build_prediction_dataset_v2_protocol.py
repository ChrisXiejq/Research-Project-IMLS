#!/usr/bin/env python3
"""Generate and validate the frozen give-way interaction dataset V2 protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


DATASET_VERSION = "give_way_interaction_prediction_v2.0"
PROTOCOL_ID = "town05_give_way_2x2_200_rollouts_v1"
HISTORY_TIMES_S = [-1.0, -0.8, -0.6, -0.4, -0.2, 0.0]
TOKEN_FEATURES = [
    {
        "index": 0,
        "name": "time_offset_s",
        "unit": "s",
        "definition": "token timestamp relative to the prediction time",
    },
    {
        "index": 1,
        "name": "ego_rel_x_m",
        "unit": "m",
        "definition": "ego position minus current target position in the current target-local longitudinal axis",
    },
    {
        "index": 2,
        "name": "ego_rel_y_m",
        "unit": "m",
        "definition": "ego position minus current target position in the current target-local lateral axis",
    },
    {
        "index": 3,
        "name": "target_rel_x_m",
        "unit": "m",
        "definition": "historical target position minus current target position in the current target-local longitudinal axis",
    },
    {
        "index": 4,
        "name": "target_rel_y_m",
        "unit": "m",
        "definition": "historical target position minus current target position in the current target-local lateral axis",
    },
    {"index": 5, "name": "ego_speed_mps", "unit": "m/s", "definition": "ego speed magnitude"},
    {"index": 6, "name": "target_speed_mps", "unit": "m/s", "definition": "target speed magnitude"},
    {
        "index": 7,
        "name": "relative_longitudinal_speed_mps",
        "unit": "m/s",
        "definition": "ego velocity minus target velocity projected onto the current target-local longitudinal axis",
    },
    {
        "index": 8,
        "name": "relative_lateral_speed_mps",
        "unit": "m/s",
        "definition": "ego velocity minus target velocity projected onto the current target-local lateral axis",
    },
    {
        "index": 9,
        "name": "sin_relative_yaw",
        "unit": "1",
        "definition": "sine of ego yaw minus target yaw",
    },
    {
        "index": 10,
        "name": "cos_relative_yaw",
        "unit": "1",
        "definition": "cosine of ego yaw minus target yaw",
    },
    {
        "index": 11,
        "name": "ego_target_distance_m",
        "unit": "m",
        "definition": "Euclidean ego-target centroid distance",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def split_for_init(init_id: int) -> str:
    if 1 <= init_id <= 40:
        return "train"
    if 41 <= init_id <= 45:
        return "validation"
    if 46 <= init_id <= 50:
        return "test"
    raise ValueError(init_id)


def feature_schema() -> Dict[str, Any]:
    return {
        "schema_id": "give_way_interaction_sequence_v2",
        "dataset_version": DATASET_VERSION,
        "frozen": True,
        "coordinate_frame": {
            "name": "current_target_local_rhs",
            "origin": "target centroid at prediction time",
            "x_axis": "target forward direction at prediction time",
            "y_axis": "target left direction at prediction time",
            "transform_rule": "all historical positions and velocities are transformed using the current target pose",
        },
        "history_times_s": HISTORY_TIMES_S,
        "sequence_shape": [len(HISTORY_TIMES_S), len(TOKEN_FEATURES)],
        "mask_shape": [len(HISTORY_TIMES_S)],
        "raster_contract": {
            "raster_contract_id": "semantic_raster_cv2_bytes_resnet_caffe_v2",
            "online_source": "SemBoxRasterizer in-memory uint8 array",
            "storage_round_trip": "cv2.imwrite PNG then cv2.imread(IMREAD_COLOR)",
            "channel_rule": "preserve rasterizer byte order; never decode the logged PNG with an RGB-assuming decoder",
            "preprocessing": "shared prediction_input_contract.preprocess_resnet_raster",
            "required_equivalence": [
                "pixel max absolute difference = 0",
                "preprocessed tensor max absolute difference = 0",
            ],
        },
        "state_sampling": {
            "source": "CARLA ActorSnapshot pose and velocity histories",
            "velocity_axes": "CARLA velocity converted to RHS as [vx, -vy]",
            "alignment_tolerance_s": 0.1,
            "invalid_rule": "if either ego or target state is unavailable, mask=0 and all 12 values are zero",
        },
        "mask_semantics": {
            "1": "ego and target states are both available and time-aligned within 0.1 s",
            "0": "missing token; feature values are zero-filled and must be ignored by masked layers",
        },
        "token_features": TOKEN_FEATURES,
        "normalization": {
            "method": "per-feature z-score",
            "fit_on": "train split only (init 01-40 across all four cells)",
            "masked_tokens_excluded": True,
            "minimum_std": 1e-6,
            "persist_with_checkpoint": ["mean", "std", "feature_names", "history_times_s", "schema_id"],
        },
        "forbidden_predictor_inputs": [
            "target_style",
            "ego_policy",
            "cell_id",
            "split",
            "ego_init_id",
        ],
        "required_sample_metadata": [
            "dataset_version",
            "protocol_id",
            "git_commit",
            "scenario",
            "map",
            "ego_init_id",
            "ego_policy",
            "target_style",
            "target_style_parameters",
            "target_speed_mps",
            "target_start_offset_m",
            "prediction_horizon_steps",
            "dt_s",
            "history_times_s",
            "feature_schema_id",
            "source_subrun",
            "sample_id",
            "raster_relpath",
            "raster_contract_id",
            "raster_uint8_sha256",
            "cell_id",
        ],
        "required_training_fields": [
            "interaction_history_world",
            "interaction_sequence",
            "interaction_sequence_mask",
            "past_states_local",
            "target_to_world_R",
            "target_to_world_t",
            "future_xy_world",
            "future_valid_mask",
        ],
        "online_offline_contract": (
            "Day 4 must call one shared feature builder for logged samples and online inference; "
            "an equivalence test is required before formal collection."
        ),
    }


def collection_cells() -> List[Dict[str, Any]]:
    return [
        {
            "cell_id": "S0_FIXED",
            "target_style": "assertive_constant_speed",
            "ego_policy": "fixed_medium",
            "purpose": "non-reactive negative control under fixed-risk data distribution",
        },
        {
            "cell_id": "S0_ADAPTIVE",
            "target_style": "assertive_constant_speed",
            "ego_policy": "adaptive_floor_weak",
            "purpose": "non-reactive negative control under adaptive-risk data distribution",
        },
        {
            "cell_id": "S1_FIXED",
            "target_style": "defensive_reactive",
            "ego_policy": "fixed_medium",
            "purpose": "interaction-positive data under fixed-risk data distribution",
        },
        {
            "cell_id": "S1_ADAPTIVE",
            "target_style": "defensive_reactive",
            "ego_policy": "adaptive_floor_weak",
            "purpose": "interaction-positive data under adaptive-risk data distribution",
        },
    ]


def collection_manifest() -> Dict[str, Any]:
    cells = collection_cells()
    rollouts: List[Dict[str, Any]] = []
    for init_id in range(1, 51):
        for cell in cells:
            rollouts.append(
                {
                    "rollout_id": f"{PROTOCOL_ID}_init_{init_id:02d}_{cell['cell_id'].lower()}",
                    "ego_init_id": init_id,
                    "split": split_for_init(init_id),
                    "cell_id": cell["cell_id"],
                    "target_style": cell["target_style"],
                    "ego_policy": cell["ego_policy"],
                    "status": "planned",
                }
            )
    return {
        "dataset_version": DATASET_VERSION,
        "protocol_id": PROTOCOL_ID,
        "frozen": True,
        "formal_collection_day": 6,
        "scenario": "scenario_uk_give_way.json",
        "map": "Town05",
        "fixed_environment": {
            "weather": "ClearNoon",
            "fps": 20,
            "side_of_road": "right",
            "traffic_control": "unsignalised",
            "priority_rule": "turning_gives_way_to_oncoming_straight",
            "target_vehicle_type": "vehicle.mercedes-benz.coupe",
            "target_route": {
                "intersection_start_node_idx": 2,
                "intersection_goal_node_idx": 2,
                "start_left_offset_m": 1.5,
                "goal_left_offset_m": 1.5,
                "start_longitudinal_offset_m": 0.0,
                "goal_longitudinal_offset_m": 25.0,
            },
            "ego_vehicle_type": "vehicle.mercedes-benz.coupe",
            "ego_route": {
                "intersection_start_node_idx": 0,
                "intersection_goal_node_idx": 3,
                "start_left_offset_m": 2.75,
                "goal_left_offset_m": 1.85,
                "goal_longitudinal_offset_m": 20.0,
                "per_init_overrides": ["start_longitudinal_offset", "init_speed"],
            },
            "target_nominal_and_initial_speed_mps": 9.0,
            "target_start_offset_m": 0.0,
            "prediction_horizon_steps": 10,
            "dt_s": 0.2,
            "history_times_s": HISTORY_TIMES_S,
            "feature_schema_id": "give_way_interaction_sequence_v2",
        },
        "factors": {
            "target_style": ["assertive_constant_speed", "defensive_reactive"],
            "ego_policy": ["fixed_medium", "adaptive_floor_weak"],
            "ego_init_id": {"start": 1, "end": 50},
        },
        "cells": cells,
        "split_rule": {
            "group_key": "ego_init_id",
            "train": list(range(1, 41)),
            "validation": list(range(41, 46)),
            "test": list(range(46, 51)),
            "constraint": "all four rollouts sharing an ego_init_id must remain in the same split",
        },
        "expected_counts": {
            "total_rollouts": 200,
            "per_cell": 50,
            "train": 160,
            "validation": 20,
            "test": 20,
        },
        "target_style_parameters": {
            "assertive_constant_speed": {
                "controller": "existing frozen straight-line target controller",
                "nominal_speed_mps": 9.0,
            },
            "defensive_reactive": {
                "controller": "DefensiveReactiveAgent",
                "nominal_speed_mps": 9.0,
                "caution_speed_mps": 4.5,
                "minimum_speed_mps": 2.5,
                "activation_distance_m": 10.0,
                "release_clearance_m": 5.0,
                "arrival_time_gap_s": 0.5,
                "closest_approach_time_s": 4.0,
                "closest_approach_distance_m": 6.0,
                "release_hold_s": 0.8,
                "max_accel_mps2": 1.5,
                "max_decel_mps2": -2.0,
                "conflict_geometry": "ego_reference_route_target_motion_line",
                "episode_semantics": "single_trigger_latched_release",
                "hazard_combination": "ttc_conflict_and_closest_approach",
                "required_properties": [
                    "ego-state-dependent trigger",
                    "TTC and conflict-proximity inputs",
                    "single trigger with latched release",
                    "non-zero minimum speed before conflict",
                    "recovery to 9.0 m/s after target clearance",
                ],
                "parameter_status": "frozen after Day 5 init01-05 development audit",
                "development_git_commit": "6b71ccc",
                "reactive_parameters_sha256": "188ea5a1e3a34cde06eed16e779a252058476c5ab3d3dfda3a870000d92e77d5",
                "collection_config_sha256": "80fe23a6ca65fb4c56e52bebbaa4d596c2f381604021689c7d0c8285f3cc32c8",
                "freeze_evidence": "docs/paper/generated/day5/day5_final_6b71ccc_audit.json",
            },
        },
        "ego_policy_parameters": {
            "fixed_medium": {
                "planner_policy": "smpc_fixed_risk",
                "risk_profile": "fixed_frontier_medium",
            },
            "adaptive_floor_weak": {
                "planner_policy": "smpc_var_risk",
                "risk_profile": "adaptive_interaction_severity",
                "variant_name": "floor_weak",
            },
        },
        "rollouts": rollouts,
    }


def validate_manifest(manifest: Dict[str, Any]) -> None:
    rollouts = manifest["rollouts"]
    if len(rollouts) != 200:
        raise ValueError(f"Expected 200 rollouts, found {len(rollouts)}")
    rollout_ids = [item["rollout_id"] for item in rollouts]
    if len(set(rollout_ids)) != len(rollout_ids):
        raise ValueError("Duplicate rollout IDs")
    counts: Dict[str, int] = {}
    for item in rollouts:
        counts[item["split"]] = counts.get(item["split"], 0) + 1
        if item["split"] != split_for_init(item["ego_init_id"]):
            raise ValueError(f"Split mismatch: {item}")
    expected = manifest["expected_counts"]
    for split in ("train", "validation", "test"):
        if counts.get(split) != expected[split]:
            raise ValueError(f"{split}: expected {expected[split]}, found {counts.get(split)}")
    for init_id in range(1, 51):
        init_rows = [item for item in rollouts if item["ego_init_id"] == init_id]
        if len(init_rows) != 4 or len({item["cell_id"] for item in init_rows}) != 4:
            raise ValueError(f"Init {init_id:02d} does not contain exactly four cells")
        if len({item["split"] for item in init_rows}) != 1:
            raise ValueError(f"Init {init_id:02d} crosses splits")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    schema = feature_schema()
    manifest = collection_manifest()
    validate_manifest(manifest)

    schema_path = output_dir / "give_way_interaction_sequence_v2.schema.json"
    manifest_path = output_dir / "give_way_interaction_v2_collection_manifest.json"
    schema_path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "dataset_version": DATASET_VERSION,
                "feature_schema": str(schema_path),
                "collection_manifest": str(manifest_path),
                "rollouts": len(manifest["rollouts"]),
                "status": "pass",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
