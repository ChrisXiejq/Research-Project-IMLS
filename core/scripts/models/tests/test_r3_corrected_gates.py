#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import json
import pickle
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODELS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = MODELS_DIR.parent
CARLA_DIR = SCRIPTS_DIR / "carla"
sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(MODELS_DIR / "experimental"))
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(CARLA_DIR))

from audit_r3_corrected_matrix import (
    CORRECTED,
    MODE_MAP,
    R3_RAW_REQUIRED_FILES,
    _expected_collision_category,
    _risk_manipulation_for_row,
    collision_episode_taxonomy,
    control_variable_audit,
    debug_audit,
    raw_evidence_sha256,
    rollout_receipt_audit,
    sha256,
)
from postcarla_trajectory_gate import (
    _actor_geometry,
    _bbox_world_pose,
    _completion_outcome,
    _fixed_conflict_points_from_debug,
    _fixed_geometry_yield_rule,
    _pair_safety,
)
from run_all_scenarios import (
    _safe_prediction_asset_argument,
    _source_file_provenance,
    _write_scenario_rollout_config,
)


class R3CorrectedGateTest(unittest.TestCase):
    def test_route_geometry_is_stable_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [
                {
                    "yield_stop_supervisor": {
                        "conflict_point": [10.0, 0.0],
                        "target_conflict_point": [10.0, 0.1],
                    }
                },
                {
                    "yield_stop_supervisor": {
                        "conflict_point": [10.0, 0.0],
                        "target_conflict_point": [10.0, 0.1],
                    }
                },
            ]
            (root / "smpc_debug_steps.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            points = _fixed_conflict_points_from_debug(str(root))
            self.assertEqual(points, ((10.0, 0.0), (10.0, 0.1)))
            ego = {"state_trajectory": np.asarray([[0.0, 0.0, 0.0, 0.0], [2.0, 10.0, 0.0, 0.0]])}
            target = {"state_trajectory": np.asarray([[0.0, 10.0, -10.0, 0.0], [1.0, 10.0, 0.1, 0.0], [2.0, 10.0, 10.0, 0.0]])}
            rule = _fixed_geometry_yield_rule("target_2", ego, target, points, 1.0, 0.2)
            self.assertEqual(rule.geometry_source, "controller_route_projection")
            self.assertTrue(rule.target_clears_before_ego_enters)

    def test_route_geometry_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "smpc_debug_steps.jsonl").write_text(
                json.dumps({"yield_stop_supervisor": {"conflict_point": [1, 2], "target_conflict_point": [3, 4]}})
                + "\n"
                + json.dumps({"yield_stop_supervisor": {"conflict_point": [2, 2], "target_conflict_point": [3, 4]}})
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                _fixed_conflict_points_from_debug(str(root))

    def test_corrected_debug_audit_requires_three_distinct_consumed_modes(self) -> None:
        summary = {"finite_frac": 1.0, "nan_count": 0}
        joint_modes = []
        for mode in range(3):
            joint_modes.append(
                {
                    "joint_mode_index": mode,
                    "per_vehicle": [
                        {
                            "vehicle_index": 0,
                            "spatial_mode_index": mode,
                            "mean_sha256": f"{mode + 1:064x}",
                            "covariance_sha256": f"{mode + 11:064x}",
                        }
                    ],
                }
            )
        row = {
            "prediction_valid": [True],
            "prediction": {
                "mode_probs": summary,
                "mus": summary,
                "sigmas": summary,
                "mode_consumption": {
                    "implementation_version": CORRECTED,
                    "mapping": MODE_MAP,
                    "joint_modes": joint_modes,
                },
            },
            "yield_stop_supervisor": {},
            "solver": {"optimal": True},
            "solver_problem": {},
            "applied": {
                "u0": [0.0, 0.0],
                "u_control": [0.0, 0.0],
                "v_des": [1.0],
                "control_prev_after": [0.0, 0.0],
                "solve_time": 0.05,
            },
        }
        failures, stats = debug_audit([row], 0.5)
        self.assertEqual(failures, [])
        self.assertEqual(stats["distinct_consumed_mode_steps"], 1)
        row["prediction"]["mode_consumption"]["joint_modes"][2]["per_vehicle"][0]["mean_sha256"] = f"{1:064x}"
        failures, stats = debug_audit([row], 0.5)
        self.assertEqual(failures, [])
        self.assertEqual(stats["learned_mode_collapse_steps"], 1)
        self.assertEqual(stats["learned_mode_collapse_fraction"], 1.0)

    def test_collision_callbacks_are_deduplicated_into_contact_episodes(self) -> None:
        actors = {
            10: {
                "actor_id": 10,
                "actor_type": "vehicle.ego",
                "actor_role_name": "ego",
                "experiment_role": "ego",
            },
            20: {
                "actor_id": 20,
                "actor_type": "vehicle.target",
                "actor_role_name": "target",
                "experiment_role": "target",
            },
        }

        def event(frame: int, monitored: int, counterpart: int) -> dict:
            monitored_role = actors[monitored]["experiment_role"]
            counterpart_role = actors[counterpart]["experiment_role"]
            pair = [10, 20]
            role_pair = ["ego", "target"]
            return {
                "frame": frame,
                "simulation_time_s": frame * 0.05,
                "monitored_actor_id": monitored,
                "monitored_actor_type": actors[monitored]["actor_type"],
                "monitored_actor_role_name": monitored_role,
                "monitored_experiment_role": monitored_role,
                "monitored_semantic_role": monitored_role,
                "counterpart_actor_id": counterpart,
                "counterpart_actor_type": actors[counterpart]["actor_type"],
                "counterpart_actor_role_name": counterpart_role,
                "counterpart_semantic_role": counterpart_role,
                "canonical_actor_id_pair": pair,
                "canonical_actor_pair_key": "10:20",
                "canonical_semantic_role_pair": role_pair,
                "canonical_semantic_role_pair_key": "ego:target",
                "collision_category": "ego_target",
                "normal_impulse_magnitude": 5.0,
            }

        failures, taxonomy = collision_episode_taxonomy(
            [
                event(100, 10, 20),
                event(100, 20, 10),  # mirrored callback, same physical contact
                event(101, 10, 20),  # continuous next-frame contact
                event(103, 10, 20),  # one empty frame => a new episode
            ],
            actors,
        )
        self.assertEqual(failures, [])
        self.assertEqual(taxonomy["callback_event_count"], 4)
        self.assertEqual(taxonomy["contact_episode_count"], 2)
        self.assertEqual(
            taxonomy["categories"]["ego_target"],
            {"callback_events": 4, "contact_episodes": 2},
        )
        self.assertEqual(
            _expected_collision_category("target", "static_vehicle"),
            "target_static_vehicle",
        )

    def test_risk_manipulation_checks_actual_solver_values(self) -> None:
        fixed = {
            "risk": {
                "solver_current_tight": 1.2815515655446004,
                "solver_current_target_prob": 0.9,
                "solver_uses_adaptive_risk": False,
                "solver_risk_mode": "fixed_static",
                "adaptive": {"solver_applied": False},
            }
        }
        failures, stats = _risk_manipulation_for_row(fixed, "fixed_aggressive")
        self.assertEqual(failures, [])
        self.assertAlmostEqual(stats["tightening"], 1.2815515655446004)
        fixed["risk"]["solver_current_tight"] = 1.64
        failures, _ = _risk_manipulation_for_row(fixed, "fixed_aggressive")
        self.assertIn("fixed_tightening_not_operating_point", failures)

        adaptive = {
            "risk": {
                "solver_current_tight": 1.72,
                "solver_current_target_prob": 0.9572837792086719,
                "solver_uses_adaptive_risk": True,
                "solver_risk_mode": "adaptive_variable",
                "adaptive": {
                    "enabled": True,
                    "solver_applied": True,
                    "tightening": 1.72,
                    "target_prob": 0.9572837792086719,
                },
            }
        }
        failures, _ = _risk_manipulation_for_row(adaptive, "adaptive")
        self.assertEqual(failures, [])

    def test_actual_bbox_local_pose_is_used_for_offline_multi_margin_replay(self) -> None:
        geometry_payload = {
            "actor_geometry": {
                "bounding_box": {
                    "dimensions_m": {"length": 4.0, "width": 2.0, "height": 1.5},
                    "local_center_m": {"x": 1.0, "y": 2.0, "z": 0.0},
                    "local_rotation_deg": {"roll": 0.0, "pitch": 0.0, "yaw": 90.0},
                }
            }
        }
        geometry = _actor_geometry("ego_0", geometry_payload, None, None)
        center, yaw = _bbox_world_pose(
            np.asarray([0.0, 10.0, 20.0, np.pi / 2]), geometry
        )
        self.assertTrue(np.allclose(center, [12.0, 21.0]))
        self.assertAlmostEqual(yaw, 0.0)
        self.assertEqual(geometry["source"], "scenario_result_carla_bounding_box")

        def actor_payload(x: float) -> dict:
            return {
                "actor_geometry": {
                    "bounding_box": {
                        "dimensions_m": {"length": 4.0, "width": 2.0, "height": 1.5},
                        "local_center_m": {"x": 0.25, "y": 0.0, "z": 0.0},
                        "local_rotation_deg": {"roll": 0.0, "pitch": 0.0, "yaw": 5.0},
                    }
                },
                "state_trajectory": np.asarray(
                    [[0.0, x, 0.0, 0.0], [1.0, x, 0.0, 0.0]]
                ),
            }

        ego = actor_payload(0.0)
        target = actor_payload(6.0)
        nominal = _pair_safety("ego_0", ego, "target_1", target, None, 0.0)
        inflated = _pair_safety("ego_0", ego, "target_1", target, None, 0.5)
        self.assertEqual(nominal.ego_geometry_source, "scenario_result_carla_bounding_box")
        self.assertGreater(
            nominal.min_footprint_separation_m,
            inflated.min_footprint_separation_m,
        )
        self.assertEqual(nominal.footprint_margin_m, 0.0)
        self.assertEqual(inflated.footprint_margin_m, 0.5)

    def test_successful_iteration_cap_is_scientific_noncompletion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "scenario_result.pkl").write_bytes(b"preserved-trajectory-evidence")
            outcome, source, reason = _completion_outcome(
                str(root),
                {
                    "ran_successfully": True,
                    "stats": {"ego_0": {"state_rows": 600}},
                },
            )
            self.assertIs(outcome, False)
            self.assertEqual(source, "successful_rollout_without_completion_marker")
            self.assertIn("without_ego_completion", reason)

    def test_fixed_geometry_nonentry_is_structured_scientific_unknown(self) -> None:
        ego = {
            "state_trajectory": np.asarray(
                [[0.0, 0.0, 0.0, 0.0], [1.0, 1.0, 0.0, 0.0]]
            )
        }
        target = {
            "state_trajectory": np.asarray(
                [[0.0, 0.0, 10.0, 0.0], [1.0, 1.0, 10.0, 0.0]]
            )
        }
        rule = _fixed_geometry_yield_rule(
            "target_1", ego, target, ((100.0, 100.0), (100.0, 100.0)), 1.0, 0.2
        )
        self.assertIsNone(rule.target_clears_before_ego_enters)
        self.assertEqual(
            rule.outcome_reason,
            "ego_and_target_never_entered_conflict_zones",
        )

    def test_rollout_config_v2_preserves_effective_and_source_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "ego_init_101.json"
            source.write_text('{"init_speed":9.1}\n', encoding="utf-8")
            provenance = _source_file_provenance(str(source))
            self.assertEqual(len(provenance["sha256"]), 64)
            scenario = {
                "scenario_description": {"traffic_control": "unsignalised"},
                "carla_params": {"map_str": "Town05", "fps": 20},
                "prediction_params": {},
                "vehicle_params": [],
            }
            effective = [{"role": "ego", "init_speed": 9.1}]
            execution = {
                "schema_version": "carla_rollout_execution_provenance_v1",
                "ego_init_source": provenance,
            }
            _write_scenario_rollout_config(
                str(root),
                scenario,
                effective_vehicle_params=effective,
                execution_provenance=execution,
            )
            payload = json.loads(
                (root / "scenario_rollout_config.json").read_text(encoding="utf-8")
            )
            self.assertEqual(payload["schema_version"], "scenario_rollout_config_v2")
            self.assertEqual(payload["effective_runtime_vehicle_params"], effective)
            self.assertEqual(payload["execution_provenance"], execution)
            with self.assertRaises(ValueError):
                _safe_prediction_asset_argument("https://example.invalid/model")

    def test_control_variable_audit_binds_init_scenario_and_first_state(self) -> None:
        reactive = {
            "caution_speed_mps": 4.5,
            "minimum_speed_mps": 2.5,
            "activation_distance_m": 10.0,
            "release_clearance_m": 5.0,
            "arrival_time_gap_s": 0.5,
            "closest_approach_time_s": 4.0,
            "closest_approach_distance_m": 3.0,
            "release_hold_s": 0.5,
        }
        runtime_reactive = {
            "reactive_caution_speed": 4.5,
            "reactive_minimum_speed": 2.5,
            "reactive_activation_distance": 10.0,
            "reactive_release_clearance": 5.0,
            "reactive_arrival_time_gap": 0.5,
            "reactive_closest_approach_time": 4.0,
            "reactive_closest_approach_distance": 3.0,
            "reactive_release_hold": 0.5,
        }
        frozen_init = {"init_speed": 9.1, "start_longitudinal_offset": 0.7}
        scenario_sha = "a" * 64
        tuning_sha = "b" * 64
        contract = {
            "init_sha256": {"101": "c" * 64},
            "scenario_contract": {"sha256": scenario_sha},
            "tuning_sha256": tuning_sha,
            "target_speed_mps": 9.0,
            "target_offset_m": 0.0,
            "adaptive_parameters": {
                "variant_name": "floor_weak",
                "approach_preclearance_floor": 1.66,
                "critical_preclearance_floor": 1.72,
                "near_preclearance_floor": 1.78,
            },
            "reactive_parameters": reactive,
            "prediction_protocol_id": "r3_corrected_formal_v2",
            "git_commit": "d" * 40,
        }
        static_a = {"role": "static"}
        static_b = {"role": "static"}
        target = {
            "role": "target",
            "init_speed": 9.0,
            "nominal_speed": 9.0,
            "start_longitudinal_offset": 0.0,
            "intersection_start_node_idx": 2,
            "intersection_goal_node_idx": 2,
            "start_left_offset": 1.5,
            "goal_left_offset": 1.5,
            "goal_longitudinal_offset": 25.0,
            "target_style": "assertive_constant_speed",
            "policy_type": "straight",
            "traffic_role": "priority_oncoming_straight",
            "obey_traffic_lights": False,
            **runtime_reactive,
        }
        ego = {
            "role": "ego",
            "init_speed": 9.1,
            "start_longitudinal_offset": 0.7,
            "nominal_speed": 6.0,
            "intersection_start_node_idx": 0,
            "intersection_goal_node_idx": 3,
            "start_left_offset": 2.75,
            "goal_left_offset": 1.85,
            "goal_longitudinal_offset": 20.0,
            "policy_type": "smpc",
            "smpc_config": "fixed_risk",
            "risk_profile": "fixed_frontier_aggressive",
            "adaptive_risk_config": None,
        }
        effective = [static_a, static_b, target, ego]
        config = {
            "schema_version": "scenario_rollout_config_v2",
            "scenario_description": {
                "traffic_control": "unsignalised",
                "side_of_road": "right",
                "priority_rule": "left turn should give way",
            },
            "carla_params": {
                "map_str": "Town05",
                "fps": 20,
                "side_of_road": "right",
                "traffic_control": "unsignalised",
                "priority_rule": "turning_gives_way_to_oncoming_straight",
                "intersection_csv_loc": "intersection_01.csv",
            },
            "effective_runtime_vehicle_params": effective,
            "execution_provenance": {
                "schema_version": "carla_rollout_execution_provenance_v1",
                "ego_init_source": {
                    "sha256": "c" * 64,
                    "parsed_values": frozen_init,
                },
                "scenario_source": {"sha256": scenario_sha},
                "tuning_source": {"sha256": tuning_sha},
                "tuning_applied": True,
                "ego_policy_config": "smpc_fixed_risk",
                "risk_profile": "fixed_frontier_aggressive",
                "adaptive_risk_config": {},
                "target_style": "assertive_constant_speed",
                "reactive_config": reactive,
                "prediction": {
                    "protocol_id": "r3_corrected_formal_v2",
                    "cell_id": "B1_fixed_aggressive_assertive",
                    "ego_policy_label": "fixed_aggressive",
                    "git_commit": "d" * 40,
                    "logging_enabled": True,
                    "logging_stride": 1,
                    "logging_horizon": 10,
                    "model_weights_argument": "B1",
                    "model_anchors_argument": "anchors.npy",
                    "model_calibration_argument": "calibration.json",
                },
            },
        }
        actor_stats = {
            "actors": [
                {"effective_vehicle_params": value} for value in effective
            ]
        }
        summary = {
            "carla_fps": 20,
            "max_iters": 600,
            "extra": {"map": "/Game/Carla/Maps/Town05"},
        }
        with tempfile.TemporaryDirectory() as temporary:
            scenario_dir = Path(temporary)
            result = {
                "ego_3": {
                    "state_trajectory": np.asarray(
                        [[1.0, 10.0, 2.0, 0.0, 9.0]]
                    )
                },
                "target_2": {
                    "state_trajectory": np.asarray(
                        [[1.0, 40.0, 3.0, 0.0, 9.0]]
                    )
                },
            }
            with (scenario_dir / "scenario_result.pkl").open("wb") as handle:
                pickle.dump(result, handle)
            failures, stats = control_variable_audit(
                scenario_dir,
                summary,
                config,
                actor_stats,
                {
                    "cell_id": "B1_fixed_aggressive_assertive",
                    "predictor": "B1",
                    "risk_policy": "fixed_aggressive",
                    "target_style": "assertive",
                },
                101,
                contract,
                frozen_init,
            )
        self.assertEqual(failures, [])
        self.assertEqual(stats["first_states_txyyawspeed"]["ego"][4], 9.0)

    def test_rollout_receipt_binds_unique_accepted_attempt_and_raw_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cell = Path(temporary) / "B1_fixed_medium_assertive"
            scenario = cell / "scenario_uk_give_way_ego_init_101_smpc_fixed_risk"
            scenario.mkdir(parents=True)
            for relative in R3_RAW_REQUIRED_FILES:
                path = scenario / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((relative + "\n").encode())
            raw_hash = raw_evidence_sha256(scenario)
            attempt_dir = cell / "_attempts/init_101/attempt_001"
            attempt_dir.mkdir(parents=True)
            record = {
                "schema_version": "r3_attempt_record_v2",
                "attempt": 1,
                "cell_id": cell.name,
                "ego_init_id": 101,
                "accepted": True,
                "classification": "accepted",
                "raw_evidence_sha256_before_promotion": raw_hash,
            }
            record_path = attempt_dir / "attempt_record.json"
            record_path.write_text(json.dumps(record), encoding="utf-8")
            ledger = {
                "schema_version": "r3_attempt_ledger_v2",
                "status": "accepted",
                "cell_id": cell.name,
                "ego_init_id": 101,
                "attempts_started": 1,
                "accepted_attempts": 1,
                "attempts": [
                    {"attempt": 1, "state": "accepted", "record": record}
                ],
            }
            ledger_path = cell / "_attempts/init_101/attempt_ledger.json"
            ledger_path.write_text(json.dumps(ledger), encoding="utf-8")
            critical = {
                relative: {
                    "bytes": (scenario / relative).stat().st_size,
                    "sha256": sha256(scenario / relative),
                }
                for relative in R3_RAW_REQUIRED_FILES
            }
            receipt = {
                "schema_version": "r3_rollout_complete_v2",
                "status": "pass",
                "cell_id": cell.name,
                "ego_init_id": 101,
                "accepted_attempt": 1,
                "recovered_after_interruption": False,
                "scenario_dir": scenario.name,
                "raw_evidence_sha256": raw_hash,
                "scenario_summary_sha256": sha256(
                    scenario / "scenario_run_summary.json"
                ),
                "attempt_record": record_path.relative_to(cell).as_posix(),
                "attempt_record_sha256": sha256(record_path),
                "attempt_ledger": ledger_path.relative_to(cell).as_posix(),
                "attempt_ledger_sha256_at_receipt": sha256(ledger_path),
                "critical_artifacts": critical,
                "optional_artifact_presence": {"smpc_completion.json": False},
            }
            receipt_path = cell / "R3_ROLLOUT_101_COMPLETE.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            failures, stats = rollout_receipt_audit(
                cell, cell.name, 101, scenario
            )
            self.assertEqual(failures, [])
            self.assertEqual(stats["accepted_attempts"], 1)
            (scenario / "scenario_steps.csv").write_text("tampered", encoding="utf-8")
            failures, _ = rollout_receipt_audit(cell, cell.name, 101, scenario)
            self.assertIn("rollout_receipt_raw_evidence_hash", failures)


if __name__ == "__main__":
    unittest.main()
