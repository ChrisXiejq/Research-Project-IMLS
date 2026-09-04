#!/usr/bin/env python3

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
import math
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.analysis.analyze_supervisor_feedback_cost_feasibility import build


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


class SupervisorFeedbackCostFeasibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]
        cls.r3 = (
            cls.repo
            / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final"
            / "server_runs/r3_corrected_formal_v3"
        )

    def test_frozen_aggregate_build_is_deterministic_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path, second_path = Path(first), Path(second)
            args = (
                self.r3 / "r3_corrected_matrix_audit.json",
                self.r3 / "analysis/r3_rollout_outcomes.csv",
            )
            first_receipt = build(*args, first_path)
            second_receipt = build(*args, second_path)

            self.assertEqual(first_receipt, second_receipt)
            self.assertEqual(first_receipt["status"], "partial_raw_required")
            self.assertEqual(
                first_receipt["legacy_aggregate_evidence_status"],
                "preliminary_legacy_conflated",
            )
            self.assertFalse(first_receipt["final_evidence_ready"])
            self.assertEqual(first_receipt["observed_rollouts"], 80)
            self.assertEqual(first_receipt["legacy_total_debug_steps"], 17230)
            self.assertEqual(first_receipt["legacy_total_nonoptimal_steps"], 264)
            self.assertEqual(first_receipt["legacy_affected_rollouts"], 80)
            self.assertEqual(first_receipt["raw_step_classification_status"], "not_evaluated")
            self.assertEqual(first_receipt["corrected_attempted_latency_status"], "not_evaluated")
            self.assertEqual(first_receipt["corrected_attempted_acceptance_status"], "not_evaluated")
            self.assertEqual(first_receipt["raw_taxonomy_status"], "not_evaluated")
            self.assertEqual(first_receipt["deadline_evaluation_status"], "not_evaluated")
            summary = json.loads(
                (first_path / "analysis_summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["status"], "partial_raw_required")
            self.assertEqual(summary["independent_init_clusters"], 5)
            self.assertFalse(summary["final_evidence_ready"])

            costs = {
                row["risk_policy"]: row
                for row in read_csv(first_path / "policy_cost_summary.csv")
            }
            self.assertAlmostEqual(
                float(costs["adaptive"]["legacy_conflated_per_rollout_p95_s_mean"]),
                0.10424183418,
            )
            self.assertAlmostEqual(
                float(costs["fixed_medium"]["legacy_conflated_per_rollout_p95_s_mean"]),
                0.090227913,
            )
            self.assertEqual(
                costs["adaptive"]["legacy_rollouts_p95_above_control_period"], "20"
            )
            self.assertEqual(
                costs["adaptive"]["legacy_aggregate_status"],
                "preliminary_legacy_conflated",
            )
            self.assertEqual(costs["adaptive"]["corrected_attempted_solve_status"], "not_evaluated")
            self.assertAlmostEqual(
                float(costs["adaptive"]["smpc_planning_interval_s"]), 0.2
            )
            self.assertEqual(
                costs["adaptive"]["legacy_rollouts_p95_above_smpc_planning_interval"], "0"
            )
            self.assertEqual(costs["adaptive"]["legacy_rollouts_p95_above_frozen_gate"], "0")

            contrasts = {
                row["contrast"]: row
                for row in read_csv(first_path / "paired_cost_contrasts.csv")
            }
            medium = contrasts["adaptive_minus_fixed_medium"]
            self.assertAlmostEqual(float(medium["mean_effect"]), 0.01401392118)
            self.assertEqual(medium["positive_pairs"], "19")
            self.assertEqual(medium["independent_init_clusters"], "5")
            self.assertEqual(medium["two_sided_exact_sign_flip_p_descriptive"], "0.0625")

            deadlines = read_csv(first_path / "deadline_exceedance.csv")
            self.assertTrue(deadlines)
            self.assertEqual({row["evaluation_status"] for row in deadlines}, {"not_evaluated"})
            planning_deadlines = [
                row
                for row in deadlines
                if row["deadline_name"] == "smpc_planning_interval_s"
            ]
            self.assertEqual(len(planning_deadlines), 4)
            self.assertEqual(
                {round(float(row["deadline_s"]), 12) for row in planning_deadlines},
                {0.2},
            )
            self.assertTrue(
                all("ego_effective_vehicle_params_json.dt" in row["deadline_source"] for row in planning_deadlines)
            )
            self.assertEqual((first_path / "solver_failure_events.csv").read_text().count("\n"), 1)
            self.assertEqual((first_path / "solver_failure_taxonomy.csv").read_text().count("\n"), 1)
            self.assertEqual((first_path / "raw_step_classification.csv").read_text().count("\n"), 1)
            self.assertEqual((first_path / "raw_policy_solver_summary.csv").read_text().count("\n"), 1)
            policy_tex = (first_path / "supervisor_feedback_02_policy_cost.tex").read_text(
                encoding="utf-8"
            )
            self.assertIn("104.24", policy_tex)
            self.assertIn("90.23", policy_tex)
            self.assertIn("Preliminary legacy aggregate", policy_tex)
            self.assertIn("bypass/no-solve", policy_tex)
            self.assertIn(r"\label{tab:supervisor-feedback-policy-cost}", policy_tex)
            nonoptimal_tex = (
                first_path / "supervisor_feedback_02_solver_nonoptimal.tex"
            ).read_text(encoding="utf-8")
            self.assertIn("Preliminary legacy", nonoptimal_tex)
            self.assertIn("64 & 4274", nonoptimal_tex)
            self.assertIn("72 & 4279", nonoptimal_tex)
            unavailable_tex = (
                first_path / "supervisor_feedback_02_failure_taxonomy.tex"
            ).read_text(encoding="utf-8")
            self.assertIn("Not evaluated", unavailable_tex)
            self.assertIn("no return status, phase or fallback cause was inferred", unavailable_tex)

            manifest = json.loads(
                (first_path / "artifact_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["status"], "partial_raw_required")
            self.assertEqual(
                manifest["legacy_aggregate_artifact_status"],
                "preliminary_legacy_conflated",
            )
            self.assertFalse(manifest["final_evidence_ready"])
            for latex_name in (
                "supervisor_feedback_02_policy_cost.tex",
                "supervisor_feedback_02_solver_nonoptimal.tex",
                "supervisor_feedback_02_failure_taxonomy.tex",
                "supervisor_feedback_02_failure_downstream.tex",
                "supervisor_feedback_02_paired_cost_acceptance.tex",
            ):
                self.assertIn(latex_name, manifest["artifacts"])
                self.assertEqual(
                    manifest["artifacts"][latex_name]["sha256"],
                    file_sha256(first_path / latex_name),
                )

            for artifact in first_receipt["artifacts"]:
                self.assertEqual(
                    (first_path / artifact).read_bytes(),
                    (second_path / artifact).read_bytes(),
                )

    def _write_synthetic_inputs(self, root: Path) -> tuple[Path, Path, Path, Path]:
        matrix_path = root / "r3_corrected_matrix_audit.json"
        outcomes_path = root / "r3_rollout_outcomes.csv"
        raw_root = root / "raw"
        files_manifest_path = root / "snapshot.files.json"

        latencies = {
            "adaptive": 0.25,
            "fixed_aggressive": 0.02,
            "fixed_medium": 0.03,
            "fixed_conservative": 0.04,
        }
        evaluations = []
        outcome_rows = []
        manifest_rows = []
        for policy, latency in latencies.items():
            cell_id = f"B1_{policy}_assertive"
            scenario_suffix = "var_risk" if policy == "adaptive" else "fixed_risk"
            relative = (
                Path(cell_id)
                / f"scenario_uk_give_way_ego_init_101_smpc_{scenario_suffix}"
                / "smpc_debug_steps.jsonl"
            )
            debug_path = raw_root / relative
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            # This mirrors the corrected-R3 schema at collection commit 8ccecf8:
            # risk mode lives under ``risk``; closed-loop fallback has no ``mode``
            # convenience field; and final supervisor actions are recorded under
            # either ``yield_stop_supervisor.applied`` or ``recovery.applied``.
            direct_action = (
                {
                    "mode": (
                        "hard_stop_observed_target_control"
                        if policy == "adaptive"
                        else "preclearance_reference_only_guard"
                    ),
                    "a_des": -3.0,
                    "df_des": 0.02,
                    "v_des": 1.0,
                }
                if policy in {"adaptive", "fixed_conservative"}
                else None
            )
            recovery_action = (
                {
                    "mode": "post_yield_recovery",
                    "a_des": 0.4,
                    "df_des": 0.01,
                    "v_des": 2.0,
                }
                if policy == "fixed_aggressive"
                else None
            )
            failure_row = {
                "step": 17,
                "prediction_valid": [True],
                "solver_bypass": {"enabled": False, "reason": "not_applicable"},
                "solver_problem": {"problem_id": 2, "bypassed": False},
                "risk": {
                    "solver_risk_mode": (
                        "adaptive_variable" if policy == "adaptive" else "fixed_static"
                    ),
                    "solver_uses_adaptive_risk": policy == "adaptive",
                    "adaptive": {
                        "solver_applied": policy == "adaptive",
                        "solver_risk_mode": (
                            "adaptive_variable" if policy == "adaptive" else "fixed_static"
                        ),
                    },
                },
                "solver": {
                    "optimal": False,
                    "solve_time": math.nan,
                    "v_next": 7.6,
                    "u_control": {"shape": [2], "head": [-5.0, -0.01]},
                    "debug": {
                        "problem_id": 2,
                        "return_status": "Infeasible_Problem_Detected",
                        "exception_type": "RuntimeError",
                        "exception": "RuntimeError('synthetic infeasible solve')",
                        "success": False,
                        "iter_count": 7,
                        "stats": {
                            "return_status": "Infeasible_Problem_Detected",
                            "success": False,
                            "iter_count": 7,
                            "t_wall_solver": 0.51,
                        },
                        "fallback": {
                            "v_curr": 8.1,
                            "v_next_ref": 7.9,
                            "u_ref_val": [0.2, 0.01],
                            "a_brake": -5.0,
                            "u_control": [-5.2, -0.01],
                            "v_tp1": 7.6,
                        },
                    },
                },
                "reference": {
                    "status": {
                        "regenerated": False,
                        "restored_global_reference": True,
                        "forced_reference_linearization": True,
                        "skip_reason": "synthetic_transition",
                    }
                },
                "yield_stop_supervisor": {
                    "phase": "cautious_approach_observed_target",
                    "active": True,
                    "applied": direct_action,
                    "recovery": {
                        "enabled": True,
                        "active": recovery_action is not None,
                        "applied": recovery_action,
                    },
                },
                "applied": {
                    "is_opt": False,
                    "solve_time": math.nan,
                    "u0": [-3.0, 0.02],
                    "u_control": [-5.2, -0.01],
                    "v_des": 1.0,
                    "control_prev_after": [-3.0, 0.02],
                },
            }
            success_row = {
                "step": 18,
                "prediction_valid": [True],
                "solver_bypass": {"enabled": False, "reason": "not_applicable"},
                "solver_problem": {"problem_id": 2, "bypassed": False},
                "risk": {
                    "solver_risk_mode": (
                        "adaptive_variable" if policy == "adaptive" else "fixed_static"
                    )
                },
                "solver": {
                    "optimal": True,
                    "solve_time": latency,
                    "u_control": {"shape": [2], "head": [0.1, 0.0]},
                    "debug": {
                        "return_status": "Solve_Succeeded",
                        "success": True,
                        "iter_count": 4,
                    },
                },
                "reference": {"status": {}},
                "yield_stop_supervisor": {"applied": None, "recovery": {"applied": None}},
                "applied": {
                    "is_opt": True,
                    "solve_time": latency,
                    "u0": [0.1, 0.0],
                    "u_control": [0.1, 0.0],
                },
            }
            bypass_row = {
                "step": 16,
                "prediction_valid": [True],
                "risk": {
                    "solver_risk_mode": (
                        "adaptive_variable" if policy == "adaptive" else "fixed_static"
                    )
                },
                "solver_bypass": {
                    "enabled": True,
                    "reason": "active_rule_yield",
                },
                "solver_problem": {"problem_id": 2, "bypassed": True},
                "solver": {
                    "bypassed": True,
                    "optimal": True,
                    "solve_time": 0.0,
                    "reason": "active_rule_yield",
                },
                "reference": {"status": {}},
                "yield_stop_supervisor": {
                    "active": True,
                    "phase": "yield_hold",
                    "applied": direct_action,
                    "recovery": {"applied": None},
                },
                "applied": {
                    "is_opt": True,
                    "solve_time": 0.0,
                    "u0": [-1.0, 0.0],
                    "u_control": [0.0, 0.0],
                    "v_des": 1.0,
                },
            }
            prediction_invalid_attempt_row = {
                "step": 15,
                "prediction_valid": [False],
                "risk": {
                    "solver_risk_mode": (
                        "adaptive_variable" if policy == "adaptive" else "fixed_static"
                    )
                },
                "solver_bypass": {"enabled": False, "reason": "not_applicable"},
                "solver_problem": {"problem_id": 2, "bypassed": False},
                "solver": {
                    "optimal": True,
                    "solve_time": 0.123,
                    "debug": {"return_status": "Solve_Succeeded", "success": True},
                },
                "applied": {"is_opt": True, "solve_time": 0.123},
            }
            prediction_invalid_bypass_row = {
                **bypass_row,
                "step": 14,
                "prediction_valid": [False],
            }
            debug_path.write_text(
                json.dumps(prediction_invalid_bypass_row, sort_keys=True)
                + "\n"
                + json.dumps(prediction_invalid_attempt_row, sort_keys=True)
                + "\n"
                + json.dumps(bypass_row, sort_keys=True)
                + "\n"
                + json.dumps(failure_row, sort_keys=True)
                + "\n"
                + json.dumps(success_row, sort_keys=True)
                + "\n",
                encoding="utf-8",
            )
            manifest_rows.append(
                {
                    "path": relative.as_posix(),
                    "bytes": debug_path.stat().st_size,
                    "sha256": file_sha256(debug_path),
                }
            )
            evaluations.append(
                {
                    "cell_id": cell_id,
                    "predictor": "B1",
                    "risk_policy": policy,
                    "target_style": "assertive",
                    "rollouts": [
                        {
                            "ego_init_id": 101,
                            "debug_steps": 5,
                            "valid_prediction_steps": 3,
                            "p95_solve_time_s": 0.95 * latency,
                            "runtime_gate_limit_s": 0.5,
                            "runtime_gate_passed": True,
                        }
                    ],
                }
            )
            outcome_rows.append(
                {
                    "cell_id": cell_id,
                    "predictor": "B1",
                    "risk_policy": policy,
                    "target_style": "assertive",
                    "ego_init_id": 101,
                    "solver_failure_fraction": 0.2,
                    "carla_fps": 20,
                    "ego_effective_vehicle_params_json": json.dumps(
                        {"dt": 0.2}, sort_keys=True
                    ),
                    "completion_valid": 1,
                    "completion_failure": 0,
                    "ego_route_completion_duration_s": 12.0,
                    "fixed_geometry_yield_outcome_observed": 1,
                    "fixed_geometry_yield_failure": 0,
                    "minimum_footprint_separation_m": 1.25,
                    "footprint_collision": 0,
                    "native_collision_any": 0,
                    "native_collision_episode_count": 0,
                    "audit_scientific_outcomes_json": json.dumps(
                        {
                            "completion_reason": "completion_criteria_satisfied",
                            "completion_success": True,
                            "fixed_geometry_yield_outcome_reason": (
                                "target_cleared_before_ego_entry"
                            ),
                            "fixed_geometry_yield_success": True,
                            "footprint_collision": False,
                            "native_collision_contact_episodes": 0,
                        },
                        sort_keys=True,
                    ),
                }
            )

        matrix_path.write_text(
            json.dumps(
                {
                    "schema_version": "synthetic_r3_matrix_v1",
                    "status": "pass",
                    "integrity_status": "pass",
                    "implementation_version": "synthetic",
                    "observed_rollouts": 4,
                    "evaluations": evaluations,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        with outcomes_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(outcome_rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(outcome_rows)
        files_manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "synthetic_snapshot_files_v1",
                    "status": "pass",
                    "files": manifest_rows,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        return matrix_path, outcomes_path, raw_root, files_manifest_path

    def test_raw_taxonomy_and_deadlines_require_and_validate_exact_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix, outcomes, raw_root, files_manifest = self._write_synthetic_inputs(root)
            output = root / "output"
            receipt = build(
                matrix,
                outcomes,
                output,
                raw_root=raw_root,
                snapshot_files_manifest=files_manifest,
            )

            self.assertEqual(receipt["raw_taxonomy_status"], "pass")
            self.assertEqual(receipt["deadline_evaluation_status"], "evaluated")
            self.assertEqual(receipt["deadline_claim_status"], "pass")
            self.assertEqual(receipt["status"], "pass")
            self.assertTrue(receipt["final_evidence_ready"])
            self.assertEqual(receipt["raw_step_classification_status"], "pass")
            self.assertEqual(receipt["raw_step_identity_status"], "pass")
            self.assertEqual(receipt["corrected_attempted_latency_status"], "pass")
            self.assertEqual(receipt["corrected_attempted_acceptance_status"], "pass")
            self.assertEqual(
                receipt["failure_downstream_outcome_join_status"], "pass"
            )
            self.assertEqual(receipt["corrected_attempted_solve_steps"], 12)
            self.assertEqual(receipt["corrected_rule_bypass_no_solve_steps"], 8)
            self.assertEqual(receipt["raw_no_solver_telemetry_context_steps"], 0)
            self.assertEqual(receipt["raw_telemetry_integrity_status"], "pass")
            self.assertEqual(receipt["corrected_attempted_fallback_or_nonaccepted_steps"], 4)
            self.assertEqual(
                receipt[
                    "legacy_minus_corrected_fallback_or_nonaccepted_steps"
                ],
                0,
            )

            step_rows = read_csv(output / "raw_step_classification.csv")
            self.assertEqual(len(step_rows), 20)
            self.assertEqual(
                {row["classification"] for row in step_rows},
                {
                    "rule_bypass_no_solve",
                    "attempted_accepted",
                    "attempted_fallback_or_nonaccepted",
                },
            )
            bypass_rows = [
                row for row in step_rows
                if row["classification"] == "rule_bypass_no_solve"
            ]
            self.assertEqual(len(bypass_rows), 8)
            self.assertEqual({row["attempted_solve_time_s"] for row in bypass_rows}, {""})
            self.assertEqual({row["solver_attempted"] for row in bypass_rows}, {"0"})
            invalid_prediction_attempts = [
                row for row in step_rows
                if row["prediction_valid_any"] == "false"
                and row["step"] == "15"
            ]
            self.assertEqual(len(invalid_prediction_attempts), 4)
            self.assertEqual(
                {row["classification"] for row in invalid_prediction_attempts},
                {"attempted_accepted"},
            )
            self.assertEqual(
                {row["solver_attempted"] for row in invalid_prediction_attempts},
                {"1"},
            )

            raw_policy = {
                row["risk_policy"]: row
                for row in read_csv(output / "raw_policy_solver_summary.csv")
            }
            for policy, latency in {
                "adaptive": 0.25,
                "fixed_aggressive": 0.02,
                "fixed_medium": 0.03,
                "fixed_conservative": 0.04,
            }.items():
                row = raw_policy[policy]
                self.assertEqual(row["prediction_valid_context_steps"], "3")
                self.assertEqual(row["prediction_invalid_context_steps"], "2")
                self.assertEqual(row["no_solver_telemetry_context_steps"], "0")
                self.assertEqual(row["rule_bypass_no_solve_steps"], "2")
                self.assertEqual(row["attempted_solve_steps"], "3")
                self.assertEqual(
                    row["prediction_valid_attempted_solve_steps"], "2"
                )
                self.assertEqual(
                    row["prediction_invalid_attempted_solve_steps"], "1"
                )
                self.assertEqual(
                    row["prediction_valid_bypass_no_solve_steps"], "1"
                )
                self.assertEqual(
                    row["prediction_invalid_bypass_no_solve_steps"], "1"
                )
                self.assertEqual(row["attempted_accepted_steps"], "2")
                self.assertEqual(row["attempted_fallback_or_nonaccepted_steps"], "1")
                self.assertEqual(row["solver_execution_decisions"], "5")
                self.assertAlmostEqual(
                    float(row["bypass_fraction_of_solver_execution_decisions"]),
                    0.4,
                )
                self.assertEqual(row["finite_attempted_latency_steps"], "2")
                self.assertEqual(row["nonfinite_attempted_latency_steps"], "1")
                self.assertAlmostEqual(
                    float(row["controller_acceptance_rate_attempted_solve"]), 2.0 / 3.0
                )
                expected_times = sorted([0.123, latency])
                self.assertAlmostEqual(
                    float(row["attempted_latency_p50_s"]),
                    0.5 * (expected_times[0] + expected_times[1]),
                )
                self.assertAlmostEqual(
                    float(row["attempted_latency_p95_s"]),
                    0.05 * expected_times[0] + 0.95 * expected_times[1],
                )
                self.assertAlmostEqual(
                    float(row["attempted_latency_p99_s"]),
                    0.01 * expected_times[0] + 0.99 * expected_times[1],
                )
            self.assertEqual(
                len(read_csv(output / "raw_policy_init_solver_summary.csv")), 4
            )

            events = read_csv(output / "solver_failure_events.csv")
            self.assertEqual(len(events), 4)
            self.assertEqual(
                {row["return_status"] for row in events},
                {"Infeasible_Problem_Detected"},
            )
            self.assertEqual({row["solver_risk_mode_source"] for row in events}, {"risk.solver_risk_mode"})
            self.assertEqual(
                {row["solver_risk_mode"] for row in events},
                {"adaptive_variable", "fixed_static"},
            )
            self.assertEqual(
                {row["solver_control_source"] for row in events},
                {"solver.debug.fallback.u_control"},
            )
            self.assertEqual(
                {row["fallback_schema"] for row in events},
                {"closed_loop_brake_or_hold_fields"},
            )
            self.assertEqual({row["fallback_mode"] for row in events}, {"__not_recorded__"})
            self.assertEqual(
                {row["fallback_mode_source"] for row in events}, {"__not_recorded__"}
            )
            self.assertEqual(
                {row["supervisor_action_source"] for row in events},
                {
                    "yield_stop_supervisor.applied",
                    "yield_stop_supervisor.recovery.applied",
                    "__none_recorded__",
                },
            )
            self.assertEqual({row["final_control_telemetry_source"] for row in events}, {"applied.u0"})
            self.assertNotIn("final_control_overridden", events[0])
            self.assertEqual({row["fallback_a_brake"] for row in events}, {"-5.0"})
            self.assertEqual(
                {row["fallback_u_control_json"] for row in events}, {"[-5.2,-0.01]"}
            )
            self.assertEqual({row["prediction_valid_any"] for row in events}, {"true"})
            self.assertEqual(
                {row["exception_type"] for row in events}, {"RuntimeError"}
            )
            self.assertEqual(
                {row["rollout_completion_failure"] for row in events}, {"0"}
            )
            self.assertEqual(
                {row["rollout_yield_failure"] for row in events}, {"0"}
            )
            self.assertEqual(
                {row["rollout_minimum_footprint_separation_m"] for row in events},
                {"1.25"},
            )
            self.assertEqual(
                {row["rollout_native_collision_any"] for row in events}, {"0"}
            )

            affected = read_csv(
                output / "solver_failure_affected_rollout_outcomes.csv"
            )
            self.assertEqual(len(affected), 4)
            self.assertEqual(
                {row["attempted_fallback_or_nonaccepted_steps"] for row in affected},
                {"1"},
            )
            self.assertEqual({row["completion_failure"] for row in affected}, {"0"})
            self.assertEqual({row["yield_failure"] for row in affected}, {"0"})
            self.assertEqual({row["footprint_collision"] for row in affected}, {"0"})
            self.assertEqual({row["native_collision_any"] for row in affected}, {"0"})

            deadline_rows = read_csv(output / "deadline_exceedance.csv")
            control = {
                row["risk_policy"]: row
                for row in deadline_rows
                if row["deadline_name"] == "simulator_control_period_s"
            }
            self.assertEqual(control["adaptive"]["deadline_exceedance_steps"], "2")
            self.assertEqual(control["fixed_medium"]["deadline_exceedance_steps"], "1")
            self.assertEqual(control["adaptive"]["finite_attempted_solve_steps"], "2")
            self.assertEqual(
                control["adaptive"]["nonfinite_attempted_solve_steps_excluded"], "1"
            )
            planning = {
                row["risk_policy"]: row
                for row in deadline_rows
                if row["deadline_name"] == "smpc_planning_interval_s"
            }
            frozen_gate = {
                row["risk_policy"]: row
                for row in deadline_rows
                if row["deadline_name"] == "frozen_runtime_gate_s"
            }
            self.assertAlmostEqual(float(planning["adaptive"]["deadline_s"]), 0.2)
            self.assertIn(
                "ego_effective_vehicle_params_json.dt",
                planning["adaptive"]["deadline_source"],
            )
            self.assertEqual(planning["adaptive"]["deadline_exceedance_steps"], "1")
            self.assertEqual(planning["fixed_medium"]["deadline_exceedance_steps"], "0")
            self.assertEqual(frozen_gate["adaptive"]["deadline_exceedance_steps"], "0")

            raw_validation = read_csv(output / "raw_rollout_validation.csv")
            self.assertEqual(len(raw_validation), 4)
            self.assertEqual(
                {row["legacy_aggregate_validation_status"] for row in raw_validation},
                {"pass_reproduced_but_conflated"},
            )
            self.assertEqual({row["rule_bypass_no_solve_steps"] for row in raw_validation}, {"2"})
            self.assertEqual({row["attempted_solve_steps"] for row in raw_validation}, {"3"})
            adaptive_rollout = next(
                row for row in raw_validation if row["risk_policy"] == "adaptive"
            )
            self.assertAlmostEqual(
                float(adaptive_rollout["legacy_raw_p95_solve_time_s"]), 0.2375
            )
            self.assertAlmostEqual(
                float(adaptive_rollout["attempted_latency_p95_s"]), 0.24365
            )

            corrected_effects = read_csv(output / "corrected_attempted_cost_effects.csv")
            self.assertEqual(len(corrected_effects), 3)
            medium_effect = next(
                row for row in corrected_effects
                if row["contrast"] == "adaptive_minus_fixed_medium"
            )
            self.assertAlmostEqual(
                float(medium_effect["adaptive_minus_control_attempted_p95_solve_time_s"]),
                0.1253,
            )
            manifest = json.loads((output / "artifact_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "pass")
            self.assertTrue(manifest["final_evidence_ready"])
            self.assertEqual(manifest["raw_debug_hash_validation"]["status"], "pass")
            self.assertEqual(manifest["raw_debug_hash_validation"]["validated_files"], 4)
            policy_tex = (
                output / "supervisor_feedback_02_policy_cost.tex"
            ).read_text(encoding="utf-8")
            self.assertIn("CasADi solver wall time", policy_tex)
            self.assertIn("not end-to-end", policy_tex)
            acceptance_tex = (
                output / "supervisor_feedback_02_solver_nonoptimal.tex"
            ).read_text(encoding="utf-8")
            self.assertIn("controller acceptance", acceptance_tex)
            self.assertIn("SUBOPTIMAL", acceptance_tex)
            self.assertIn("Bypass/no-solve", acceptance_tex)
            taxonomy_tex = (
                output / "supervisor_feedback_02_failure_taxonomy.tex"
            ).read_text(encoding="utf-8")
            self.assertIn(r"Infeasible\_Problem\_Detected", taxonomy_tex)
            self.assertIn(r"cautious\_approach\_observed\_target", taxonomy_tex)
            self.assertIn(r"closed\_loop\_brake\_or\_hold\_fields", taxonomy_tex)
            self.assertIn(r"yield\_stop\_supervisor.applied", taxonomy_tex)
            self.assertNotIn("Not evaluated", taxonomy_tex)
            downstream_tex = (
                output / "supervisor_feedback_02_failure_downstream.tex"
            ).read_text(encoding="utf-8")
            self.assertIn("descriptive association", downstream_tex)
            self.assertIn("1.250", downstream_tex)
            self.assertNotIn("Not evaluated", downstream_tex)
            paired_tex = (
                output / "supervisor_feedback_02_paired_cost_acceptance.tex"
            ).read_text(encoding="utf-8")
            self.assertIn("Recorded solve P95", paired_tex)
            self.assertIn("Fallback/nonacceptance", paired_tex)
            self.assertIn("Fixed aggressive", paired_tex)
            self.assertIn("Fixed medium", paired_tex)
            self.assertIn("Fixed conservative", paired_tex)
            self.assertIn("Init $n$", paired_tex)
            self.assertIn("not a feasibility certificate", paired_tex)
            self.assertNotIn("Not evaluated", paired_tex)

            with self.assertRaisesRegex(ValueError, "manifest is required"):
                build(
                    matrix,
                    outcomes,
                    root / "unhashed-output",
                    raw_root=raw_root,
                )

            # A supplied but incomplete raw directory must fail, not silently become a
            # partial taxonomy or a not-evaluated result.
            first_debug = next(raw_root.rglob("smpc_debug_steps.jsonl"))
            first_debug.unlink()
            with self.assertRaisesRegex(ValueError, "incomplete"):
                build(
                    matrix,
                    outcomes,
                    root / "incomplete-output",
                    raw_root=raw_root,
                    snapshot_files_manifest=files_manifest,
                )

    def test_duplicate_or_nonmonotonic_raw_steps_fail_closed(self) -> None:
        for mode, expected in (
            ("duplicate", "Duplicate raw step IDs"),
            ("nonmonotonic", "not strictly increasing"),
        ):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                matrix, outcomes, raw_root, files_manifest = self._write_synthetic_inputs(
                    root
                )
                debug_path = next(raw_root.rglob("smpc_debug_steps.jsonl"))
                rows = [
                    json.loads(line)
                    for line in debug_path.read_text(encoding="utf-8").splitlines()
                ]
                if mode == "duplicate":
                    rows[1]["step"] = rows[0]["step"]
                else:
                    rows[1], rows[2] = rows[2], rows[1]
                debug_path.write_text(
                    "\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n",
                    encoding="utf-8",
                )
                manifest = json.loads(files_manifest.read_text(encoding="utf-8"))
                relative = debug_path.relative_to(raw_root).as_posix()
                record = next(
                    row for row in manifest["files"] if row["path"] == relative
                )
                record["bytes"] = debug_path.stat().st_size
                record["sha256"] = file_sha256(debug_path)
                files_manifest.write_text(
                    json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(ValueError, expected):
                    build(
                        matrix,
                        outcomes,
                        root / "invalid-step-output",
                        raw_root=raw_root,
                        snapshot_files_manifest=files_manifest,
                    )

    def test_telemetry_absent_context_closes_final_integrity_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            matrix, outcomes, raw_root, files_manifest = self._write_synthetic_inputs(root)
            debug_path = next(raw_root.rglob("smpc_debug_steps.jsonl"))
            debug_rows = debug_path.read_text(encoding="utf-8").splitlines()
            debug_rows[0] = json.dumps(
                {
                    "step": 14,
                    "prediction_valid": [False],
                    # All solver/problem/applied/bypass execution telemetry is
                    # deliberately absent.  Canonical corrected R3 must never
                    # silently exclude this row from a final denominator.
                },
                sort_keys=True,
            )
            debug_path.write_text("\n".join(debug_rows) + "\n", encoding="utf-8")

            files_manifest_payload = json.loads(
                files_manifest.read_text(encoding="utf-8")
            )
            relative = debug_path.relative_to(raw_root).as_posix()
            manifest_row = next(
                row
                for row in files_manifest_payload["files"]
                if row["path"] == relative
            )
            manifest_row["bytes"] = debug_path.stat().st_size
            manifest_row["sha256"] = file_sha256(debug_path)
            files_manifest.write_text(
                json.dumps(files_manifest_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            output = root / "telemetry-integrity-output"
            receipt = build(
                matrix,
                outcomes,
                output,
                raw_root=raw_root,
                snapshot_files_manifest=files_manifest,
            )
            self.assertEqual(receipt["status"], "fail_raw_telemetry_integrity")
            self.assertFalse(receipt["final_evidence_ready"])
            self.assertEqual(
                receipt["raw_telemetry_integrity_status"],
                "fail_nonzero_no_solver_telemetry_context",
            )
            self.assertEqual(receipt["raw_no_solver_telemetry_context_steps"], 1)
            self.assertEqual(receipt["raw_step_classification_status"], "pass")
            self.assertEqual(
                receipt["raw_taxonomy_status"], "fail_raw_telemetry_integrity"
            )
            raw_policy_rows = read_csv(output / "raw_policy_solver_summary.csv")
            self.assertEqual(len(raw_policy_rows), 4)
            self.assertEqual(
                sum(
                    int(row["no_solver_telemetry_context_steps"])
                    for row in raw_policy_rows
                ),
                1,
            )
            report = (output / "SUPERVISOR_FEEDBACK_02_REPORT.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("Raw telemetry integrity failed", report)
            self.assertNotIn("no_prediction", report)


if __name__ == "__main__":
    unittest.main()
