
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import csv
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODELS_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = Path(__file__).resolve().parents[4]
if str(MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_DIR))
    sys.path.insert(0, str(MODELS_DIR / "experimental"))

from analyze_r3_corrected_formal import (  # noqa: E402
    FIXED_POLICIES,
    PREDICTORS,
    STYLES,
    _canonical_collision_stats,
    analyze,
    exact_sign_flip_p,
    holm_adjust,
    raw_evidence_sha256,
    scientific_analysis,
)


AMENDMENT = REPO_DIR / "docs/paper/generated/distinction_v1/09_analysis_contract/M0_R3_ANALYSIS_CONTRACT_v2.json"


def analysis_contract(replicates=200):
    payload = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    payload["inference"]["bootstrap"]["replicates"] = replicates
    return payload


def write_synthetic_analysis_contract(root, replicates=100):
    contract_dir = root / "analysis_contract"
    contract_dir.mkdir(parents=True, exist_ok=True)
    original_source = AMENDMENT.parent / "M0_R3_ANALYSIS_CONTRACT.json"
    original_path = contract_dir / original_source.name
    original_path.write_bytes(original_source.read_bytes())
    markdown_source = AMENDMENT.with_suffix(".md")
    markdown_path = contract_dir / markdown_source.name
    markdown_path.write_bytes(markdown_source.read_bytes())
    payload = analysis_contract(replicates=replicates)
    amendment_path = contract_dir / AMENDMENT.name
    amendment_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    marker = {
        "status": "pass",
        "amended_m0_v2": {
            "path": amendment_path.name,
            "sha256": hashlib.sha256(amendment_path.read_bytes()).hexdigest(),
        },
        "human_readable_amendment": {
            "path": markdown_path.name,
            "sha256": hashlib.sha256(markdown_path.read_bytes()).hexdigest(),
        },
    }
    (contract_dir / "M0_AMENDMENT_COMPLETE.json").write_text(json.dumps(marker), encoding="utf-8")
    return amendment_path


def run_contract():
    cells = [
        {
            "cell_id": f"{predictor}_{policy}_{style}",
            "predictor": predictor,
            "risk_policy": policy,
            "target_style": style,
        }
        for predictor in PREDICTORS
        for policy in (*FIXED_POLICIES, "adaptive")
        for style in STYLES
    ]
    return {
        "schema_version": "r3_corrected_formal_contract_v1",
        "status": "frozen",
        "result_generation": "distinction_corrected_v1",
        "implementation_version": "corrected_joint_modes_shared_amin_v1",
        "target_offset_m": 0.0,
        "ego_init_ids": [101, 102, 103, 104, 105],
        "expected_rollouts": 80,
        "cells": cells,
        "predictors": {
            "B1": {"calibration_parameters": {"temperature": 1.0, "covariance_scale": 1.0}},
            "B0": {"calibration": "identity_no_calibration_artifact"},
        },
    }


def synthetic_outcomes(positive=True):
    rows = []
    policy_duration = {
        "fixed_aggressive": 10.0,
        "fixed_medium": 9.5,
        "fixed_conservative": 9.0,
        "adaptive": 8.0 if positive else 10.5,
    }
    policy_separation = {
        "fixed_aggressive": 2.0,
        "fixed_medium": 2.1,
        "fixed_conservative": 2.2,
        "adaptive": 2.6 if positive else 1.8,
    }
    for predictor in PREDICTORS:
        predictor_duration = -0.1 if predictor == "B1" and positive else (0.1 if predictor == "B1" else 0.0)
        predictor_separation = 0.1 if predictor == "B1" and positive else (-0.1 if predictor == "B1" else 0.0)
        for policy in (*FIXED_POLICIES, "adaptive"):
            for style in STYLES:
                for init_id in range(101, 106):
                    rows.append(
                        {
                            "cell_id": f"{predictor}_{policy}_{style}",
                            "predictor": predictor,
                            "risk_policy": policy,
                            "target_style": style,
                            "ego_init_id": init_id,
                            "ego_route_completion_duration_s": policy_duration[policy] + predictor_duration,
                            "minimum_footprint_separation_m": policy_separation[policy] + predictor_separation,
                            "native_collision_any": 0,
                            "footprint_collision": 0,
                            "fixed_geometry_yield_failure": 0,
                            "completion_failure": 0,
                            "continuous_outcome_missing_reasons": "",
                            "binary_outcome_missing_reasons": "",
                        }
                    )
    return rows


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def prediction_sample(init_id, cell_id, policy, style):
    truth = [[float(step), 0.0] for step in range(10)]
    modes = [truth, [[float(step), 0.2] for step in range(10)], [[float(step), -0.2] for step in range(10)]]
    covariance = [[[[1.0, 0.0], [0.0, 1.0]] for _ in range(10)] for _ in range(3)]
    return {
        "sample_id": 0,
        "ego_init_id": init_id,
        "cell_id": cell_id,
        "ego_policy": policy,
        "target_style": "defensive_reactive" if style == "reactive" else "assertive_constant_speed",
        "future_xy_world": truth,
        "future_valid_mask": [True] * 10,
        "pred_mus_world": modes,
        "pred_sigmas_world": covariance,
        "mode_probabilities": [0.6, 0.25, 0.15],
        "target_reactive_diagnostics": {"active": False},
    }


def build_end_to_end_fixture(root, *, censor_one=True):
    root.mkdir(parents=True, exist_ok=True)
    contract = run_contract()
    (root / "r3_run_contract.json").write_text(json.dumps(contract), encoding="utf-8")
    audit_evaluations = []
    for cell in contract["cells"]:
        cell_dir = root / cell["cell_id"]
        cell_dir.mkdir(parents=True)
        gate_rows = []
        df_rows = []
        risk_rows = []
        audit_rollouts = []
        for init_id in contract["ego_init_ids"]:
            scenario = f"scenario_uk_give_way_ego_init_{init_id}_smpc"
            scenario_dir = cell_dir / scenario
            prediction_dir = scenario_dir / "prediction_dataset"
            prediction_dir.mkdir(parents=True)
            is_censored = censor_one and cell["cell_id"] == "B1_adaptive_reactive" and init_id == 105
            base_step = {
                "fixed_aggressive": 200,
                "fixed_medium": 190,
                "fixed_conservative": 180,
                "adaptive": 210,
            }[cell["risk_policy"]]
            # Deliberately make B1/adaptive scientifically worse. Analysis and
            # collection-stop status must still pass when telemetry is complete.
            completion_step = base_step + (2 if cell["predictor"] == "B1" else 0)
            fps = 20.0
            completion_duration = completion_step / fps
            start = 1000.0 + init_id
            summary = {
                "ran_successfully": True,
                "carla_fps": fps,
                "extra": {"collision_event_count": 0, "collision_events": []},
            }
            (scenario_dir / "scenario_run_summary.json").write_text(json.dumps(summary), encoding="utf-8")
            if not is_censored:
                marker = {
                    "step": completion_step,
                    "completion": {"completed_by_goal_dist": True, "lateral_ok": True, "heading_ok": True},
                }
                (scenario_dir / "smpc_completion.json").write_text(json.dumps(marker), encoding="utf-8")
            sample = prediction_sample(init_id, cell["cell_id"], cell["risk_policy"], cell["target_style"])
            (prediction_dir / "prediction_dataset_labeled.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
            auxiliary = {
                "scenario_rollout_config.json": "{}\n",
                "smpc_debug_setup.json": "{}\n",
                "prediction_deployment_manifest.json": "{}\n",
                "prediction_dataset/prediction_dataset_config.json": "{}\n",
                "prediction_dataset/prediction_dataset_manifest.json": "{}\n",
                "prediction_dataset/prediction_dataset_raw.jsonl": "{}\n",
                "smpc_debug_steps.jsonl": "{}\n",
                "scenario_result.pkl": "synthetic-pickle-evidence",
                "scenario_steps.csv": "step\n0\n",
            }
            for relative, content in auxiliary.items():
                path = scenario_dir / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            gate_rows.append(
                {
                    "scenario_dir": str(scenario_dir),
                    "completion_valid": not is_censored,
                    "solver_failure_frac": 0.0,
                    "pair_safety": [{"min_footprint_separation_m": 2.0, "footprint_collision": False}],
                    "fixed_geometry_yield_rules": [
                        {
                            "geometry_source": "controller_route_projection",
                            "ego_enter_time_s": start + 4.0,
                            "ego_exit_time_s": start + 5.0,
                            "target_enter_time_s": start + 2.0,
                            "target_exit_time_s": start + 3.0,
                            "target_clears_before_ego_enters": True,
                        }
                    ],
                }
            )
            # The trajectory duration is exactly one logged tick shorter. It
            # must be accepted as a check, never used as the primary duration.
            df_rows.append(
                {
                    "initial": init_id,
                    "completion_time": completion_duration - 1.0 / fps,
                    "completion_valid": str(not is_censored),
                }
            )
            risk_value = 1.5 + (0.01 * (init_id - 101) if cell["risk_policy"] == "adaptive" else 0.0)
            risk_rows.append(
                {
                    "initial": init_id,
                    "n_steps": max(completion_step - 1, 1),
                    "sim_time_start_s": start,
                    "sim_time_end_s": start + completion_duration - 1.0 / fps,
                    "solver_failure_frac": 0.0,
                    "supervisor_active_frac": 0.0,
                    "risk_tightening_mean": risk_value,
                    "solver_uses_adaptive_risk_frac": 1.0 if cell["risk_policy"] == "adaptive" else 0.0,
                }
            )
            audit_rollouts.append(
                {
                    "scenario": scenario,
                    "ego_init_id": init_id,
                    "integrity_status": "pass",
                    "integrity_failures": [],
                    "native_collision_callback_count": 0,
                    "native_collision_taxonomy": {
                        "schema_version": "canonical_actor_pair_collision_v1",
                        "episode_definition": "unordered_actor_pair_frame_contiguous",
                        "callback_event_count": 0,
                        "validated_callback_event_count": 0,
                        "contact_episode_count": 0,
                        "categories": {
                            category: {"callback_events": 0, "contact_episodes": 0}
                            for category in (
                                "ego_target",
                                "ego_infrastructure",
                                "target_infrastructure",
                                "ego_static_vehicle",
                                "target_static_vehicle",
                                "other",
                            )
                        },
                        "episodes": [],
                    },
                    "scientific_outcomes": {
                        "native_collision_contact_episodes": 0,
                        "native_collision_categories": [],
                        "scenario_context_validity_warning_categories": [],
                        "footprint_collision": False,
                        "fixed_geometry_yield_success": True,
                        "fixed_geometry_yield_outcome_reason": "observed",
                        "completion_success": not is_censored,
                        "completion_source": "smpc_completion_json" if not is_censored else "iteration_cap",
                        "completion_reason": "observed",
                        "runtime_gate_passed": True,
                        "reactive_active_samples": 0,
                        "adaptive_tightening_variation_observed": cell["risk_policy"] == "adaptive",
                        "footprint_margin_sensitivity": {
                            str(margin): {
                                "footprint_collision": False,
                                "min_footprint_separation_m": 2.5 - 2.0 * margin,
                                "geometry_sources": ["carla_bounding_box", "carla_bounding_box"],
                                "dimensions_m": [4.5, 2.0, 4.8, 2.1],
                                "bbox_pose_offsets_rhs": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                            }
                            for margin in (0.0, 0.25, 0.35, 0.5)
                        },
                    },
                    "spawned_actor_telemetry": {
                        "actor_count": 2,
                        "role_counts": {"ego": 1, "target": 1},
                        "actors": [
                            {
                                "actor_key": "ego_3",
                                "actor_id": 3,
                                "actor_type": "vehicle.synthetic.ego",
                                "actor_role_name": "ego",
                                "experiment_role": "ego",
                                "requested_blueprint": "vehicle.synthetic.ego",
                                "bounding_box": {
                                    "extent_m": {"x": 2.25, "y": 1.0, "z": 0.75},
                                    "dimensions_m": {"length": 4.5, "width": 2.0, "height": 1.5},
                                    "local_center_m": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "local_rotation_deg": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                                },
                                "effective_vehicle_params": {"length": 4.5, "width": 2.0},
                            },
                            {
                                "actor_key": "target_2",
                                "actor_id": 2,
                                "actor_type": "vehicle.synthetic.target",
                                "actor_role_name": "target",
                                "experiment_role": "target",
                                "requested_blueprint": "vehicle.synthetic.target",
                                "bounding_box": {
                                    "extent_m": {"x": 2.4, "y": 1.05, "z": 0.75},
                                    "dimensions_m": {"length": 4.8, "width": 2.1, "height": 1.5},
                                    "local_center_m": {"x": 0.0, "y": 0.0, "z": 0.0},
                                    "local_rotation_deg": {"roll": 0.0, "pitch": 0.0, "yaw": 0.0},
                                },
                                "effective_vehicle_params": {"length": 4.8, "width": 2.1},
                            },
                        ],
                    },
                    "control_variables": {
                        "map": "Town05",
                        "carla_fps": fps,
                        "max_iters": 600,
                        "ego_init_id": init_id,
                        "frozen_init_values": {},
                        "effective_ego_init_values": {},
                        "target_nominal_conditions": {},
                        "first_states_txyyawspeed": {
                            "ego": [start, 0.0, 0.0, 0.0, 0.0],
                            "target": [start, 10.0, 0.0, 0.0, 9.0],
                        },
                        "scenario_source_sha256": "1" * 64,
                        "tuning_source_sha256": "2" * 64,
                        "init_source_sha256": "3" * 64,
                    },
                    "risk_manipulation": {
                        "audited_steps": completion_step,
                        "solver_applied_adaptive_steps": completion_step if cell["risk_policy"] == "adaptive" else 0,
                        "tightening_min": risk_value,
                        "tightening_max": risk_value + (0.01 if cell["risk_policy"] == "adaptive" else 0.0),
                        "unique_1e9": 2 if cell["risk_policy"] == "adaptive" else 1,
                        "target_prob_min": 0.9,
                        "target_prob_max": 0.9,
                        "adaptive_variation_observed": cell["risk_policy"] == "adaptive",
                    },
                    "runtime_gate_passed": True,
                    "learned_mode_collapse_steps": 0,
                    "learned_mode_collapse_fraction": 0.0,
                }
            )
            critical_relatives = [
                "scenario_run_summary.json",
                "scenario_rollout_config.json",
                "smpc_debug_setup.json",
                "prediction_deployment_manifest.json",
                "prediction_dataset/prediction_dataset_config.json",
                "prediction_dataset/prediction_dataset_manifest.json",
                "prediction_dataset/prediction_dataset_raw.jsonl",
                "prediction_dataset/prediction_dataset_labeled.jsonl",
                "smpc_debug_steps.jsonl",
                "scenario_result.pkl",
                "scenario_steps.csv",
            ]
            if (scenario_dir / "smpc_completion.json").is_file():
                critical_relatives.append("smpc_completion.json")
            critical = {
                relative: {
                    "bytes": (scenario_dir / relative).stat().st_size,
                    "sha256": hashlib.sha256((scenario_dir / relative).read_bytes()).hexdigest(),
                }
                for relative in critical_relatives
            }
            attempt_dir = cell_dir / "_attempts"
            attempt_dir.mkdir(exist_ok=True)
            attempt_record = attempt_dir / f"init_{init_id}_attempt_1.json"
            attempt_ledger = attempt_dir / f"init_{init_id}_ledger.json"
            attempt_record.write_text('{"status":"accepted"}\n', encoding="utf-8")
            attempt_ledger.write_text('{"accepted_attempt":1}\n', encoding="utf-8")
            receipt = {
                "schema_version": "r3_rollout_complete_v2",
                "status": "pass",
                "cell_id": cell["cell_id"],
                "ego_init_id": init_id,
                "accepted_attempt": 1,
                "recovered_after_interruption": False,
                "scenario_dir": scenario,
                "raw_evidence_sha256": raw_evidence_sha256(scenario_dir),
                "scenario_summary_sha256": critical["scenario_run_summary.json"]["sha256"],
                "attempt_record": str(attempt_record.relative_to(cell_dir)),
                "attempt_record_sha256": hashlib.sha256(attempt_record.read_bytes()).hexdigest(),
                "attempt_ledger": str(attempt_ledger.relative_to(cell_dir)),
                "attempt_ledger_sha256_at_receipt": hashlib.sha256(attempt_ledger.read_bytes()).hexdigest(),
                "critical_artifacts": critical,
                "optional_artifact_presence": {"smpc_completion.json": not is_censored},
                "accepted_at_utc": "2026-08-08T00:00:00+00:00",
            }
            receipt_path = cell_dir / f"R3_ROLLOUT_{init_id}_COMPLETE.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            audit_rollouts[-1]["attempt_provenance"] = {
                "receipt_path": str(receipt_path.relative_to(root)),
                "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
                "accepted_attempt": 1,
                "recovered_after_interruption": False,
                "raw_evidence_sha256": receipt["raw_evidence_sha256"],
                "attempt_record": receipt["attempt_record"],
                "attempt_record_sha256": receipt["attempt_record_sha256"],
                "attempt_classification": "accepted",
                "attempt_ledger": receipt["attempt_ledger"],
                "attempt_ledger_sha256": receipt["attempt_ledger_sha256_at_receipt"],
                "attempts_started": 1,
                "accepted_attempts": 1,
            }
        (cell_dir / "postcarla_trajectory_gate.json").write_text(
            json.dumps({"evaluations": gate_rows}), encoding="utf-8"
        )
        write_csv(cell_dir / "df_full.csv", df_rows)
        write_csv(cell_dir / "risk_by_conflict_distance_summary.csv", risk_rows)
        audit_evaluations.append({**cell, "rollouts": audit_rollouts})
    audit = {
        "status": "pass",
        "observed_rollouts": 80,
        "passing_integrity_rollouts": 80,
        "evaluations": audit_evaluations,
    }
    (root / "r3_corrected_matrix_audit.json").write_text(json.dumps(audit), encoding="utf-8")
    return contract


class R3FormalAnalysisTests(unittest.TestCase):
    def test_exact_sign_flip_and_holm_small_sample_boundary(self):
        self.assertAlmostEqual(exact_sign_flip_p([1.0] * 5), 0.0625)
        self.assertAlmostEqual(exact_sign_flip_p([1.0] * 4), 0.125)
        self.assertAlmostEqual(exact_sign_flip_p([0.0] * 5), 1.0)
        rows = [{"family": "H3", "exact_sign_flip_p_raw": 0.0625} for _ in range(8)]
        holm_adjust(rows, ("family",), declared_size=8)
        self.assertEqual({row["holm_adjusted_p"] for row in rows}, {0.5})

    def test_canonical_collision_pair_episodes_do_not_double_count_mirrored_callbacks(self):
        taxonomy = {
            "native_collision_taxonomy": {
                "schema_version": "canonical_actor_pair_collision_v1",
                "episode_definition": "unordered_actor_pair_frame_contiguous",
                "callback_event_count": 2,
                "validated_callback_event_count": 2,
                "contact_episode_count": 1,
                "categories": {
                    category: {
                        "callback_events": 2 if category == "ego_target" else 0,
                        "contact_episodes": 1 if category == "ego_target" else 0,
                    }
                    for category in (
                        "ego_target",
                        "ego_infrastructure",
                        "target_infrastructure",
                        "ego_static_vehicle",
                        "target_static_vehicle",
                        "other",
                    )
                },
                "episodes": [
                    {
                        "canonical_actor_pair_key": "2:3",
                        "canonical_semantic_role_pair_key": "ego:target",
                        "collision_category": "ego_target",
                        "start_frame": 10,
                        "end_frame": 10,
                        "callback_count": 2,
                    }
                ],
            }
        }
        stats, issues = _canonical_collision_stats(taxonomy)
        self.assertEqual(issues, [])
        self.assertEqual(stats["native_collision_callback_count"], 2)
        self.assertEqual(stats["native_collision_episode_count"], 1)
        self.assertEqual(stats["native_collision_any"], 1)
        zero, zero_issues = _canonical_collision_stats(
            {
                "native_collision_taxonomy": {
                    "schema_version": "canonical_actor_pair_collision_v1",
                    "episode_definition": {"identity": "unordered_actor_pair"},
                    "callback_event_count": 0,
                    "validated_callback_event_count": 0,
                    "contact_episode_count": 0,
                    "categories": {},
                    "episodes": [],
                }
            }
        )
        self.assertEqual(zero_issues, [])
        self.assertEqual(zero["native_collision_any"], 0)

    def test_h3_h4_emit_five_init_effects_and_strict_dominance(self):
        science = scientific_analysis(synthetic_outcomes(positive=True), run_contract(), analysis_contract())
        self.assertEqual(len(science["h3_effects"]), 80)
        self.assertEqual(len(science["h4_effects"]), 120)
        self.assertTrue(all(row["complete_clusters"] == 5 for row in science["h3_contrasts"]))
        self.assertTrue(all(abs(row["exact_sign_flip_p_raw"] - 0.0625) < 1e-12 for row in science["h3_contrasts"]))
        self.assertTrue(all(abs(row["holm_adjusted_p"] - 0.5) < 1e-12 for row in science["h3_contrasts"]))
        self.assertEqual(science["h3_status"], "supported_directionally_at_nominal_timing")
        self.assertEqual(science["h4_status"], "supported_as_universal_dominance")
        self.assertTrue(all(row["dominance_status"] == "dominates" for row in science["h4_dominance"]))

    def test_event_clock_censoring_and_negative_science_do_not_force_more_carla(self):
        with tempfile.TemporaryDirectory(prefix="r3_formal_negative_") as temporary:
            root = Path(temporary)
            results = root / "r3"
            output = root / "analysis"
            contract_path = write_synthetic_analysis_contract(root)
            build_end_to_end_fixture(results, censor_one=True)
            receipt = analyze(results, results / "r3_run_contract.json", contract_path, output)
            self.assertEqual(receipt["status"], "pass")
            self.assertEqual(receipt["h3_scientific_support_status"], "not_supported_as_universal_claim")
            self.assertEqual(receipt["h4_scientific_support_status"], "not_supported_as_universal_dominance")
            self.assertTrue(receipt["study_stop_gate_passed"])
            self.assertFalse(receipt["additional_large_scale_carla_required"])
            self.assertEqual(receipt["formal_table_row_counts"]["r3_footprint_margin_outcomes.csv"], 320)
            self.assertEqual(
                receipt["formal_table_row_counts"]["r3_h4_footprint_margin_dominance_sensitivity.csv"], 48
            )
            self.assertEqual(receipt["formal_table_row_counts"]["r3_collision_category_summary.csv"], 96)

            with (output / "r3_rollout_outcomes.csv").open(encoding="utf-8") as handle:
                outcomes = list(csv.DictReader(handle))
            observed = next(
                row
                for row in outcomes
                if row["cell_id"] == "B0_fixed_aggressive_assertive" and row["ego_init_id"] == "101"
            )
            self.assertAlmostEqual(float(observed["ego_route_completion_duration_s"]), 10.0)
            self.assertAlmostEqual(float(observed["df_logged_trajectory_duration_s"]), 9.95)
            censored = next(
                row
                for row in outcomes
                if row["cell_id"] == "B1_adaptive_reactive" and row["ego_init_id"] == "105"
            )
            self.assertEqual(censored["ego_route_completion_duration_s"], "")
            self.assertIn("completion_not_valid", censored["continuous_outcome_missing_reasons"])

            stop = json.loads((output / "R3_STUDY_STOP_GATE.json").read_text(encoding="utf-8"))
            self.assertEqual(stop["status"], "pass")
            self.assertTrue(stop["basis"]["all_outcomes_observed_or_prespecified_undefined"])
            self.assertTrue(
                stop["scientific_results_do_not_change_stop_decision"]["negative_null_or_mixed_H3_H4"]
            )

    def test_unclassified_integrity_missingness_keeps_stop_gate_open(self):
        with tempfile.TemporaryDirectory(prefix="r3_formal_missing_") as temporary:
            root = Path(temporary)
            results = root / "r3"
            output = root / "analysis"
            contract_path = write_synthetic_analysis_contract(root)
            build_end_to_end_fixture(results, censor_one=False)
            (results / "B0_fixed_medium_assertive" / "df_full.csv").unlink()
            receipt = analyze(results, results / "r3_run_contract.json", contract_path, output)
            self.assertEqual(receipt["status"], "fail")
            self.assertFalse(receipt["study_stop_gate_passed"])
            self.assertTrue(receipt["additional_large_scale_carla_required"])

    def test_optional_completion_artifact_mutation_is_detected_after_audit(self):
        with tempfile.TemporaryDirectory(prefix="r3_formal_mutation_") as temporary:
            root = Path(temporary)
            results = root / "r3"
            output = root / "analysis"
            contract_path = write_synthetic_analysis_contract(root, replicates=20)
            build_end_to_end_fixture(results, censor_one=False)
            completion = (
                results
                / "B0_fixed_aggressive_assertive"
                / "scenario_uk_give_way_ego_init_101_smpc"
                / "smpc_completion.json"
            )
            completion.write_text(completion.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            receipt = analyze(results, results / "r3_run_contract.json", contract_path, output)
            self.assertEqual(receipt["status"], "fail")
            self.assertTrue(
                any("rollout_receipt_optional_artifact_hash:smpc_completion.json" in issue for issue in receipt["integrity_issues"])
            )
            self.assertTrue(
                any("rollout_receipt_raw_evidence_hash" in issue for issue in receipt["integrity_issues"])
            )


if __name__ == "__main__":
    unittest.main()
