"""Regression tests for the prospective SF4 behavioural-authority study."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import pickle
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[4]
MODELS = ROOT / "core" / "scripts" / "models"
CARLA_POLICIES = ROOT / "core" / "scripts" / "carla" / "policies"
sys.path.insert(0, str(MODELS))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


attempts = load("r3_attempt_manager", MODELS / "r3_attempt_manager.py")
analysis = load("sf4_analysis_tested", MODELS / "analyze_sf4_supervisor_behavioural_authority.py")
prepare = load("sf4_prepare_tested", MODELS / "prepare_sf4_supervisor_behavioural_authority.py")
init_generator = load(
    "sf4_init_generator_tested",
    MODELS / "generate_sf4_supervisor_authority_inits.py",
)
action_filter = load("sf4_filter_tested", CARLA_POLICIES / "supervisor_action_filter.py")
packager = load("sf4_packager_tested", MODELS / "package_sf4_compact_evidence.py")
full_packager = load("sf4_full_packager_tested", MODELS / "package_sf4_full_raw_snapshot.py")
smoke_validator = load(
    "sf4_smoke_validator_tested",
    MODELS / "validate_sf4_supervisor_authority_smoke.py",
)


class ActionBoundaryTests(unittest.TestCase):
    def test_solver_scalar_channels_normalise_singleton_representation_only(self):
        values = (
            0.25,
            [0.25],
            [[0.25]],
            np.asarray([0.25]),
            np.asarray([[0.25]]),
        )
        canonical = [
            action_filter.canonical_scalar_channel(value, name="acc_prev")
            for value in values
        ]
        self.assertEqual(canonical, [0.25] * len(values))
        self.assertEqual(
            len({action_filter.stable_value_sha256(value) for value in canonical}),
            1,
        )
        for invalid in ([0.25, 0.5], [], float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                action_filter.canonical_scalar_channel(invalid, name="acc_prev")

    def test_apply_and_monitor_only_differ_only_at_factual_command(self):
        common = dict(
            nominal_u=(1.0, 0.1), nominal_v_des=4.0,
            candidate_u=(-2.0, 0.2), candidate_v_des=1.0,
        )
        apply = action_filter.arbitrate_post_solver_action(mode="apply", **common)
        monitor = action_filter.arbitrate_post_solver_action(mode="monitor_only", **common)
        self.assertEqual(apply.actual_u, apply.candidate_u)
        self.assertEqual(monitor.actual_u, monitor.nominal_u)
        self.assertTrue(apply.intervention_requested)
        self.assertTrue(apply.intervention_applied)
        self.assertFalse(monitor.intervention_applied)
        self.assertEqual(apply.candidate_u, monitor.candidate_u)

    def test_monitor_only_integration_retains_state_and_candidate_but_sends_nominal(self):
        state = {
            "active": True,
            "phase": "released_recovery",
            "target_cleared_conflict": True,
            "release_clock_step": 77,
            "applied": {"reason": "caution", "a_des": -2.0},
            "recovery": {
                "active": True,
                "step": 4,
                "applied": {"reason": "recovery", "a_des": 0.4},
            },
        }
        common = dict(
            nominal_u=(1.0, 0.1), nominal_v_des=4.0,
            candidate_u=(-2.0, 0.2), candidate_v_des=1.0,
            supervisor_state=state,
        )
        apply_decision, apply_state, apply_record = (
            action_filter.integrate_post_solver_action_filter(mode="apply", **common)
        )
        monitor_decision, monitor_state, monitor_record = (
            action_filter.integrate_post_solver_action_filter(
                mode="monitor_only", **common
            )
        )
        # The state machine ran in both arms and its phase/release/recovery
        # clocks survive the production boundary unchanged.
        for key in ("active", "phase", "target_cleared_conflict", "release_clock_step"):
            self.assertEqual(apply_state[key], monitor_state[key])
            self.assertEqual(monitor_state[key], state[key])
        self.assertEqual(apply_state["recovery"]["step"], monitor_state["recovery"]["step"])
        self.assertTrue(monitor_state["recovery"]["active"])
        # Candidate evidence is retained, while only the factual command and
        # action-labelled diagnostic namespace change in monitor-only.
        self.assertEqual(
            monitor_record["supervisor_candidate_command"],
            apply_record["supervisor_candidate_command"],
        )
        self.assertEqual(
            monitor_record["supervisor_candidate_details"], state["applied"]
        )
        self.assertEqual(
            monitor_record["recovery_candidate_details"],
            state["recovery"]["applied"],
        )
        self.assertEqual(monitor_state["shadow_applied"], state["applied"])
        self.assertEqual(
            monitor_state["recovery"]["shadow_applied"],
            state["recovery"]["applied"],
        )
        self.assertIsNone(monitor_state["applied"])
        self.assertIsNone(monitor_state["recovery"]["applied"])
        self.assertEqual(monitor_decision.actual_u, monitor_decision.nominal_u)
        self.assertEqual(apply_decision.actual_u, apply_decision.candidate_u)
        self.assertEqual(state["applied"]["a_des"], -2.0)  # pure: input not mutated

    def test_invalid_action_mode_fails_closed(self):
        with self.assertRaises(ValueError):
            action_filter.normalize_action_filter_mode("disabled")

    def test_complete_authority_mode_and_channel_neutrality_fail_closed(self):
        self.assertEqual(action_filter.normalize_supervisor_authority_mode("ON"), "on")
        self.assertFalse(action_filter.supervisor_authority_enabled("off"))
        passed = action_filter.verify_authority_channels(
            mode="off",
            nominal={"reference": [1.0, 2.0], "control_prev": [0.0, 0.0]},
            actual={"reference": [1.0, 2.0], "control_prev": [0.0, 0.0]},
        )
        self.assertEqual(passed["status"], "pass")
        with self.assertRaises(ValueError):
            action_filter.verify_authority_channels(
                mode="off",
                nominal={"reference": [1.0, 2.0]},
                actual={"reference": [1.0, 3.0]},
            )

    def test_authority_on_candidate_application_fails_closed(self):
        passed = action_filter.verify_supervisor_candidate_application(
            mode="on",
            candidate={"reference": [1.0, 2.0]},
            actual={"reference": [1.0, 2.0]},
        )
        self.assertEqual(passed["status"], "pass")
        with self.assertRaisesRegex(ValueError, "failed to apply"):
            action_filter.verify_supervisor_candidate_application(
                mode="on",
                candidate={"reference": [1.0, 2.0]},
                actual={"reference": [1.0, 3.0]},
            )
        # Off deliberately retains a differing candidate as shadow evidence;
        # its factual neutrality is checked by verify_authority_channels.
        off = action_filter.verify_supervisor_candidate_application(
            mode="off",
            candidate={"reference": [1.0, 2.0]},
            actual={"reference": [1.0, 3.0]},
        )
        self.assertFalse(off["candidate_equality_required"])
        with self.assertRaisesRegex(ValueError, "empty"):
            action_filter.verify_supervisor_candidate_application(
                mode="off", candidate={}, actual={}
            )
        with self.assertRaisesRegex(ValueError, "channel set mismatch"):
            action_filter.verify_supervisor_candidate_application(
                mode="off",
                expected_channels=("reference", "heading"),
                candidate={"reference": [1.0]},
                actual={"reference": [1.0]},
            )
        with self.assertRaisesRegex(ValueError, "channel set mismatch"):
            action_filter.verify_supervisor_candidate_application(
                mode="off",
                expected_channels=("reference",),
                candidate={"reference": [1.0], "extra": [2.0]},
                actual={"reference": [1.0], "extra": [2.0]},
            )

    def test_complete_authority_manifest_rejects_empty_missing_and_extra(self):
        expected = action_filter.COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS

        def record():
            return {
                "candidate_computed": True,
                "requested": False,
                "applied": False,
                "authority_assignment_consistent": True,
                "factual_neutral_when_off": True,
            }

        complete = {key: record() for key in expected}
        passed = action_filter.verify_complete_behavioural_authority_manifest(
            mode="off", channels=complete
        )
        self.assertEqual(set(passed["channels"]), set(expected))
        for bad in (
            {},
            {
                key: value for key, value in complete.items()
                if key != "lane_entry_heading_cost"
            },
            {**complete, "undeclared_extra_channel": record()},
        ):
            with self.assertRaisesRegex(ValueError, "channel set mismatch"):
                action_filter.verify_complete_behavioural_authority_manifest(
                    mode="off", channels=bad
                )

    def test_shadow_state_advances_but_factual_solver_and_estimator_state_restore(self):
        class Owner:
            behavior = 2
            reference = [1.0, 2.0]
            control_prev = [0.0, 0.0]
            estimator_release_clock = 7

        owner = Owner()

        def callback():
            owner.behavior += 3
            owner.reference[0] = 99.0
            owner.control_prev[0] = -4.0
            return owner.behavior

        result = action_filter.run_isolated_supervisor_shadow(
            owner=owner,
            shadow_state={"behavior": 10},
            shadow_fields=("behavior",),
            protected_fields=("reference", "control_prev", "estimator_release_clock"),
            callback=callback,
        )
        self.assertEqual(result.result, 13)
        self.assertEqual(result.next_shadow_state["behavior"], 13)
        self.assertEqual(owner.behavior, 2)
        self.assertEqual(owner.reference, [1.0, 2.0])
        self.assertEqual(owner.control_prev, [0.0, 0.0])
        self.assertEqual(owner.estimator_release_clock, 7)

    def test_receipt_prefix_is_sf4_and_validated(self):
        self.assertEqual(
            attempts.receipt_path(Path("cell"), 106, "SF4").name,
            "SF4_ROLLOUT_106_COMPLETE.json",
        )
        with self.assertRaises(ValueError):
            attempts.receipt_path(Path("cell"), 106, "../../bad")

    def test_formal_analyzer_raw_hash_contract_matches_attempt_manager(self):
        self.assertEqual(tuple(analysis.RAW_REQUIRED), tuple(attempts.RAW_REQUIRED_FILES))
        self.assertEqual(tuple(analysis.RAW_OPTIONAL), tuple(attempts.RAW_OPTIONAL_FILES))

    def test_complete_adverse_rollout_is_accepted_once_despite_nonzero_wrapper(self):
        with tempfile.TemporaryDirectory() as temporary:
            cell = Path(temporary) / "SF4_cell"
            args = Namespace(
                cell_dir=cell, cell_id="SF4_cell", init_id=106,
                max_attempts=3, receipt_prefix="SF4",
            )
            with contextlib.redirect_stdout(io.StringIO()) as prepared_output:
                self.assertEqual(attempts.command_prepare(args), 0)
            attempt_dir = Path(json.loads(prepared_output.getvalue())["attempt_dir"])
            scenario = attempt_dir / "scenario_test_ego_init_106_smpc_fixed_risk"
            scenario.mkdir()
            json_values = {
                "scenario_run_summary.json": {
                    "ran_successfully": True,
                    "extra": {
                        "collision_event_count": 1,
                        "collision_terminated": True,
                    },
                },
                "scenario_rollout_config.json": {},
                "smpc_debug_setup.json": {},
                "prediction_deployment_manifest.json": {},
                "prediction_dataset/prediction_dataset_config.json": {},
                "prediction_dataset/prediction_dataset_manifest.json": {},
            }
            for relative, value in json_values.items():
                path = scenario / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value) + "\n")
            for relative in attempts.RAW_REQUIRED_JSONL:
                path = scenario / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n")
            with (scenario / "scenario_result.pkl").open("wb") as handle:
                pickle.dump({"ego": {}}, handle)
            (scenario / "scenario_steps.csv").write_text("step\n0\n")
            (attempt_dir / "runner_attempt.log").write_text(
                "scientific gate reported collision\n"
            )
            finalize = Namespace(**vars(args), attempt_dir=attempt_dir, exit_code=7)
            with contextlib.redirect_stdout(io.StringIO()) as finalized_output:
                self.assertEqual(attempts.command_finalize(finalize), 0)
            finalized = json.loads(finalized_output.getvalue())
            self.assertEqual(finalized["status"], "accepted")
            self.assertFalse(finalized["retry_allowed"])
            with contextlib.redirect_stdout(io.StringIO()) as resumed_output:
                self.assertEqual(attempts.command_prepare(args), 0)
            self.assertEqual(json.loads(resumed_output.getvalue())["status"], "complete")
            self.assertEqual(
                len([
                    path for path in (cell / "_attempts/init_106").glob("attempt_*")
                    if path.is_dir()
                ]),
                1,
            )


class FrozenDesignTests(unittest.TestCase):
    def test_frozen_init_accepts_cross_numpy_final_ulp_without_rewrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ego_init_106.json"
            frozen = {
                "init_speed": 9.480309946842153,
                "start_longitudinal_offset": 2.302768641875152,
            }
            original = json.dumps(frozen, sort_keys=True) + "\n"
            path.write_text(original, encoding="utf-8")

            reproduced = dict(frozen)
            reproduced["start_longitudinal_offset"] = 2.3027686418751516
            payload, rendered = init_generator.freeze_or_validate_candidate(
                path, reproduced
            )

            self.assertEqual(payload, frozen)
            self.assertEqual(rendered, original)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_frozen_init_rejects_material_numeric_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "ego_init_106.json"
            frozen = {
                "init_speed": 9.480309946842153,
                "start_longitudinal_offset": 2.302768641875152,
            }
            path.write_text(
                json.dumps(frozen, sort_keys=True) + "\n", encoding="utf-8"
            )

            reproduced = dict(frozen)
            reproduced["start_longitudinal_offset"] += 1.0e-6
            with self.assertRaisesRegex(SystemExit, "numeric drift"):
                init_generator.freeze_or_validate_candidate(path, reproduced)

    def test_config_arms_have_one_behavioral_difference(self):
        base_path = (
            ROOT / "core" / "scripts" / "carla" / "scenarios"
            / "tuning_configs" / "give_way_v15_supervisor_behavioural_authority_ablation.json"
        )
        base = json.loads(base_path.read_text())
        arms = prepare.validate_config_pair(base)
        differences = prepare.recursive_differences(
            prepare.behavioral_view(arms["on"]),
            prepare.behavioral_view(arms["off"]),
        )
        self.assertEqual(differences, [prepare.BEHAVIORAL_TREATMENT_PATH])

    def test_v15_preserves_v13_except_declared_experiment_mechanics(self):
        tuning = ROOT / "core" / "scripts" / "carla" / "scenarios" / "tuning_configs"
        previous = json.loads((tuning / "give_way_reduced_clear_path_release_v13_risk_owned_yield.json").read_text())
        current = json.loads((tuning / "give_way_v15_supervisor_behavioural_authority_ablation.json").read_text())
        for key in ("config_name", "version", "description"):
            previous.pop(key, None)
            current.pop(key, None)
        differences = prepare.recursive_differences(previous, current)
        self.assertEqual(
            differences,
            [
                ("carla_params",),
                ("vehicle_role_overrides", "ego", "yield_post_solver_action_filter_mode"),
                ("vehicle_role_overrides", "ego", "yield_rule_smpc_bypass_enabled"),
                ("vehicle_role_overrides", "ego", "yield_supervisor_behavioural_authority_mode"),
            ],
        )

    def test_matrix_is_exact_and_sf4_namespaced(self):
        cells = prepare.execution_cells()
        self.assertEqual(len(cells), 8)
        self.assertEqual(len({cell["cell_id"] for cell in cells}), 8)
        self.assertTrue(all(cell["cell_id"].startswith("SF4_") for cell in cells))

    def test_init_manifest_is_strict_stream_continuation(self):
        manifest_path = (
            ROOT / "core" / "scripts" / "carla" / "scenarios" / "inits"
            / "distinction_sf4_supervisor_authority_ablation" / "SF4_INIT_CANDIDATE_MANIFEST.json"
        )
        manifest = json.loads(manifest_path.read_text())
        self.assertEqual(
            manifest["schema_version"],
            "sf4_supervisor_authority_ablation_init_candidates_v1",
        )
        self.assertEqual([item["ego_init_id"] for item in manifest["records"]], list(range(106, 116)))
        self.assertEqual(manifest["stream_predecessor"]["sha256"], "85ec9738373f986347668a6495c8eb717883d70a3a8383174b0066f770a631d4")
        self.assertAlmostEqual(manifest["records"][0]["init_speed"], 9.480309946842153)
        self.assertAlmostEqual(manifest["records"][-1]["start_longitudinal_offset"], -1.5993952652797176)

    def test_preregistration_includes_approach_and_signed_stop_geometry(self):
        prereg_path = (
            ROOT / "docs" / "paper" / "generated"
            / "distinction_sf4_supervisor_authority_ablation" / "prereg"
            / "SF4_SUPERVISOR_BEHAVIOURAL_AUTHORITY_PREREG.json"
        )
        prereg = prepare.validate_prereg(prereg_path)
        self.assertIn(
            "corrected reduced_intervention",
            prereg["research_question"],
        )
        self.assertIn(
            "not the historical full supervisor configuration",
            prereg["research_question"],
        )
        outcomes = set(
            prereg["secondary_estimands"]["same_did_and_direct_effects"]
        )
        self.assertIn("cautious_approach_progress_m", outcomes)
        self.assertIn("first_stop_distance_to_designed_stop_m", outcomes)
        definitions = prereg["secondary_estimands"][
            "behaviour_endpoint_definitions"
        ]
        self.assertIn("not automatically beneficial", definitions[
            "cautious_approach_progress_m"
        ])
        self.assertIn("rather than the front bumper", definitions[
            "first_stop_distance_to_conflict_m"
        ])

    def test_excluded_smoke_covers_full_risk_by_authority_factorial(self):
        expected = {
            ("fixed_on", "fixed_medium", "on"),
            ("fixed_off", "fixed_medium", "off"),
            ("adaptive_on", "adaptive", "on"),
            ("adaptive_off", "adaptive", "off"),
        }
        observed = {
            (label, case["risk"], case["mode"])
            for label, case in smoke_validator.CASES.items()
        }
        self.assertEqual(observed, expected)

        prereg_path = (
            ROOT / "docs" / "paper" / "generated"
            / "distinction_sf4_supervisor_authority_ablation" / "prereg"
            / "SF4_SUPERVISOR_BEHAVIOURAL_AUTHORITY_PREREG.json"
        )
        prereg = prepare.validate_prereg(prereg_path)
        smoke = prereg["design"]["excluded_full_stack_smoke"]
        self.assertEqual(smoke["count"], 4)
        self.assertEqual(
            {
                (case["label"], case["risk_policy"], case["authority"])
                for case in smoke["cases"]
            },
            expected,
        )

        runner = (
            ROOT / "core" / "scripts" / "carla"
            / "run_sf4_supervisor_behavioural_authority_ablation.sh"
        ).read_text(encoding="utf-8")
        for label, risk, mode in expected:
            self.assertIn(f"run_smoke_case {label} {risk} {mode}", runner)

class FormalAnalysisTests(unittest.TestCase):
    def debug_rows(self, mode: str):
        nominal = {"a_des": 1.0, "df_des": 0.1, "v_des": 4.0}
        candidate = {"a_des": -1.0, "df_des": 0.1, "v_des": 1.0}
        actual = candidate if mode == "on" else nominal
        effective_filter = "apply" if mode == "on" else "monitor_only"
        speeds = (2.0, 0.1, 0.1, 0.1, 0.2, 0.9, 0.9, 0.9)
        neutral = {
            "yield_stop_seen": False,
            "yield_stop_active_prev": False,
            "yield_recovery_steps_remaining": 0,
            "yield_last_applied_accel": None,
        }

        def audit():
            return {
                "schema_version": "supervisor_behavioural_authority_channels_v1",
                "mode": mode,
                "authority_enabled": mode == "on",
                "status": "pass",
                "adaptive_risk_only_channels": [],
                "channels": {
                    "reference": {
                        "nominal_sha256": "same",
                        "actual_sha256": "same",
                        "equal": True,
                        "adaptive_risk_only_exception": False,
                    }
                },
            }

        def candidate_application_audit():
            channels = {
                key: {
                    "candidate_sha256": "same",
                    "actual_sha256": (
                        "same" if mode == "on" else "nominal"
                    ),
                    "equal": mode == "on",
                }
                for key in analysis.PRE_SOLVER_CANDIDATE_CHANNELS
            }
            return {
                "schema_version": "supervisor_candidate_application_channels_v1",
                "mode": mode,
                "authority_enabled": mode == "on",
                "candidate_equality_required": mode == "on",
                "status": "pass",
                "channels": channels,
            }

        route_s = (0.0, 1.0, 1.0, 1.0, 1.1, 1.5, 2.0, 2.5)
        rows = []
        for step, speed in enumerate(speeds):
            bypass_requested = step == 0
            bypass_effective = mode == "on" and bypass_requested
            complete_channels = {}
            for channel in analysis.COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS:
                requested = (
                    bypass_requested
                    if channel == "rule_smpc_bypass" else True
                )
                complete_channels[channel] = {
                    "candidate_computed": True,
                    "requested": requested,
                    "applied": mode == "on" and requested,
                    "authority_assignment_consistent": True,
                    "factual_neutral_when_off": True,
                }
            record = {
                "mode": effective_filter,
                "authority_enabled": mode == "on",
                "nominal_solver_command": nominal,
                "supervisor_candidate_command": candidate,
                "actual_command": actual,
                "intervention_requested": True,
                "intervention_applied": mode == "on",
            }
            reference_audit = audit()
            reference_audit["solver_input_authority"] = audit()
            reference_audit["candidate_application_authority"] = (
                candidate_application_audit()
            )
            authority = {
                "schema_version": "supervisor_behavioural_authority_step_v1",
                "mode": mode,
                "authority_enabled": mode == "on",
                "interaction_estimator_computed": True,
                "allowed_solver_influence_when_off": ["adaptive_risk_allocation"],
                "rule_smpc_bypass_configured": True,
                "shadow_state_isolated": True,
                "rule_smpc_bypass_channel": {
                    "configured": True,
                    "shadow_requested": bypass_requested,
                    "shadow_reason": "synthetic" if bypass_requested else None,
                    "effective": bypass_effective,
                    "authority_gated": True,
                    "off_always_executes_solver": True,
                },
                "upstream_shadow_requests": {
                    "reference_requested": True,
                    "heading_cost_requested": False,
                    "reference_linearization_requested": True,
                    "rule_smpc_bypass_requested": bypass_requested,
                    "any_requested": True,
                },
                "upstream_shadow_intensity": {
                    "reference_states_max_abs_delta": 0.5,
                    "reference_inputs_max_abs_delta": 0.25,
                    "heading_cost_max_abs_weight": 0.0,
                    "linearization_states_max_abs_delta": 0.4,
                },
                "interaction_risk_estimator_state": {
                    "rule_yield_phase": "hold_yield_line",
                    "clear_path_release_steps_remaining": 0,
                    "permitted_factual_use_when_authority_off": [
                        "adaptive_risk_allocation"
                    ],
                    "nonrisk_solver_or_control_use_when_authority_off": False,
                    "separate_from_shadow_behaviour_state": True,
                },
                "reference_and_solver_input_audit": reference_audit,
                "factual_behaviour_state_before_solve": neutral,
                "factual_behaviour_state_after_action": neutral,
                "post_action_and_next_state_audit": audit(),
                "complete_candidate_channel_manifest": {
                    "schema_version": (
                        "complete_supervisor_behavioural_authority_manifest_v1"
                    ),
                    "mode": mode,
                    "authority_enabled": mode == "on",
                    "status": "pass",
                    "expected_channels": sorted(
                        analysis.COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS
                    ),
                    "channels": complete_channels,
                },
                "post_solver_shadow_request": {
                    "requested": True,
                    "delta": {"accel_abs": 2.0, "steer_abs": 0.0, "v_des_abs": 3.0},
                },
                "observed_first_stage_activity": {
                    "any_requested": True,
                    "scientific_outcome_not_integrity_gate": True,
                },
                "implementation_manipulation_gate": {
                    "status": "pass",
                    "shadow_state_isolated": True,
                    "candidate_channels_computed": sorted(
                        analysis.COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS
                    ),
                },
            }
            rows.append(
                {
                    "step": step,
                    "vehicle_state": {"speed": speed},
                    "risk": {"solver_uses_adaptive_risk": True},
                    "solver_bypass": {
                        "configuration_enabled": True,
                        "enabled": bypass_effective,
                        "shadow_requested": bypass_requested,
                        "authority_mode": mode,
                        "authority_gated": True,
                        "off_always_executes_solver": True,
                    },
                    "solver": {
                        "bypassed": bypass_effective,
                        "optimal": True,
                        "solve_time": 0.0 if bypass_effective else 0.1,
                        "debug": {
                            "return_status": (
                                None if bypass_effective
                                else (
                                    "SUBOPTIMAL" if step == 1
                                    else "SOLVER_RET_SUCCESS"
                                )
                            )
                        },
                    },
                    "solver_problem": {
                        "problem_id": 2,
                        "bypassed": bypass_effective,
                    },
                    "supervisor_behavioural_authority": authority,
                    "applied": {"is_opt": True, "post_solver_action_filter": record},
                    "yield_stop_supervisor": {
                        "active": step <= 3,
                        "phase": "hold_yield_line" if step <= 3 else "released_recovery",
                        "ego_route_s": route_s[step],
                        "conflict_s": 10.0,
                        "stop_s": 8.0,
                        "stop_clearance": 2.0,
                        "ego_distance_to_conflict": 10.0 - route_s[step],
                        "ego_distance_to_stop": 8.0 - route_s[step],
                        "target_nominally_cleared_conflict": step >= 4,
                        "raw_reduced_clear_path_release": step >= 4,
                        "target_cleared_conflict": step >= 5,
                        "post_solver_action_filter": record,
                        "supervisor_behavioural_authority": authority,
                    },
                }
            )
        return rows

    def test_solver_attempt_boundary_rejects_missing_or_inconsistent_telemetry(self):
        attempted = self.debug_rows("off")[0]
        self.assertEqual(
            analysis.validated_solver_execution(
                attempted, effective_bypass=False
            )["classification"],
            "attempted_controller_accepted",
        )
        for mutation, message in (
            (lambda row: row.pop("solver_problem"), "solver_problem"),
            (lambda row: row["applied"].pop("is_opt"), "applied.is_opt"),
            (lambda row: row["solver"].pop("solve_time"), "solve_time"),
            (lambda row: row["solver"].update({"bypassed": True}), "bypassed"),
            (lambda row: row["solver"].update({"optimal": False}), "disagrees"),
        ):
            row = json.loads(json.dumps(attempted))
            mutation(row)
            with self.assertRaisesRegex(ValueError, message):
                analysis.validated_solver_execution(row, effective_bypass=False)

        bypass = self.debug_rows("on")[0]
        self.assertEqual(
            analysis.validated_solver_execution(
                bypass, effective_bypass=True
            )["classification"],
            "rule_bypass_no_solve",
        )
        bypass["solver"]["solve_time"] = 0.01
        with self.assertRaisesRegex(ValueError, "zero-time"):
            analysis.validated_solver_execution(bypass, effective_bypass=True)

    def make_fixture(self, root: Path):
        results = root / "results"
        prereg = root / "SF4_PREREG.json"
        prereg.write_text(json.dumps({
            "schema_version": "sf4_supervisor_behavioural_authority_prereg_v1",
            "status": "frozen_before_outcomes",
        }))
        order = []
        cells = []
        reactive = {"caution_speed_mps": 4.0}

        def timing_block(value_s, count=8):
            return {
                "observed_sample_count": count,
                "finite_sample_count": count,
                "nonfinite_sample_count": 0,
                "exception_count": 0,
                "thresholds_ms": [50.0, 200.0, 500.0],
                "mean_s": value_s,
                "p50_s": value_s,
                "p95_s": value_s,
                "p99_s": value_s,
                "max_s": value_s,
                "over_50ms_fraction": float(value_s > 0.050),
                "over_200ms_fraction": float(value_s > 0.200),
                "over_500ms_fraction": float(value_s > 0.500),
            }
        init_values = {
            str(init_id): {
                "init_speed": 9.0,
                "start_longitudinal_offset": (init_id - 106) / 100.0,
            }
            for init_id in range(106, 116)
        }
        init_hashes = {str(init_id): "init-%d" % init_id for init_id in range(106, 116)}
        for init_id in range(106, 116):
            for policy in ("adaptive", "fixed_medium"):
                for style in ("assertive", "reactive"):
                    for mode in ("on", "off"):
                        cell_id = "SF4_B1_%s_%s_supervisor_%s" % (policy, style, mode)
                        item = {
                            "cell_id": cell_id, "predictor": "B1", "risk_policy": policy,
                            "target_style": style, "supervisor_authority_mode": mode,
                            "ego_init_id": init_id,
                        }
                        order.append(item)
                        if init_id == 106:
                            cells.append({key: item[key] for key in (
                                "cell_id", "predictor", "risk_policy", "target_style", "supervisor_authority_mode"
                            )})
                        cell = results / cell_id
                        scenario = cell / ("scenario_ego_init_%d" % init_id)
                        scenario.mkdir(parents=True, exist_ok=True)
                        completion_step = {
                            ("fixed_medium", "off"): 200,
                            ("adaptive", "off"): 190,
                            ("fixed_medium", "on"): 200,
                            ("adaptive", "on"): 160,
                        }[(policy, mode)]
                        policy_wall_s = {
                            ("fixed_medium", "off"): 0.100,
                            ("adaptive", "off"): 0.120,
                            ("fixed_medium", "on"): 0.130,
                            ("adaptive", "on"): 0.180,
                        }[(policy, mode)]
                        prediction_wall_s = 0.010
                        timing_diagnostics = {
                            "schema_version": "server_wall_time_diagnostics_v1",
                            "clock": "time.perf_counter",
                            "server_side_diagnostic_only": True,
                            "deployment_or_real_time_guarantee": False,
                            "ego_policy_scope": "synthetic",
                            "prediction_scope": "synthetic",
                            "active_planning_definition": (
                                "ego policy.done() is false immediately after run_step"
                            ),
                            "ego_policy_all_invocations": timing_block(
                                policy_wall_s
                            ),
                            "ego_policy_active_planning_invocations": timing_block(
                                policy_wall_s
                            ),
                            "prediction_all_invocations": timing_block(
                                prediction_wall_s
                            ),
                            "prediction_during_ego_active_planning": timing_block(
                                prediction_wall_s
                            ),
                        }
                        risk_profile = (
                            "adaptive_interaction_severity"
                            if policy == "adaptive" else "fixed_frontier_medium"
                        )
                        runtime_style = (
                            "defensive_reactive" if style == "reactive"
                            else "assertive_constant_speed"
                        )
                        adaptive = {
                            "variant_name": "floor_weak",
                            "approach_preclearance_floor": 1.66,
                            "critical_preclearance_floor": 1.72,
                            "near_preclearance_floor": 1.78,
                        } if policy == "adaptive" else {}
                        values = {
                            "scenario_run_summary.json": {
                                "ran_successfully": True,
                                "carla_fps": 20, "max_iters": 600,
                                "extra": {
                                    "map": "Carla/Maps/Town05",
                                    "collision_telemetry_schema_version": "carla_collision_identity_v2",
                                    "collision_event_count": 0,
                                    "collision_events": [],
                                    "collision_terminated": False,
                                    "server_wall_time_diagnostics": timing_diagnostics,
                                },
                            },
                            "scenario_rollout_config.json": {
                                "schema_version": "scenario_rollout_config_v2",
                                "carla_params": {
                                    "map_str": "Town05", "fps": 20, "side_of_road": "right",
                                    "traffic_control": "unsignalised",
                                    "priority_rule": "turning_gives_way_to_oncoming_straight",
                                    "terminate_on_collision": True,
                                },
                                "execution_provenance": {
                                    "schema_version": "carla_rollout_execution_provenance_v1",
                                    "scenario_source": {"sha256": "scenario-hash"},
                                    "ego_init_source": {
                                        "sha256": init_hashes[str(init_id)],
                                        "parsed_values": init_values[str(init_id)],
                                    },
                                    "tuning_source": {"sha256": mode + "-tuning"},
                                    "tuning_applied": True,
                                    "ego_policy_config": "smpc_var_risk" if policy == "adaptive" else "smpc_fixed_risk",
                                    "risk_profile": risk_profile,
                                    "adaptive_risk_config": adaptive,
                                    "target_style": runtime_style,
                                    "reactive_config": reactive,
                                    "prediction": {
                                        "model_weights_argument": "model", "model_anchors_argument": "anchors",
                                        "model_calibration_argument": "calibration",
                                        "protocol_id": "sf4_supervisor_behavioural_authority_v1",
                                        "cell_id": cell_id, "ego_policy_label": policy,
                                        "git_commit": "synthetic", "logging_enabled": True,
                                        "logging_stride": 1, "logging_horizon": 10,
                                    },
                                },
                                "effective_runtime_vehicle_params": [
                                    {
                                        "role": "ego", **init_values[str(init_id)],
                                        "risk_profile": risk_profile,
                                        "smpc_config": "var_risk" if policy == "adaptive" else "fixed_risk",
                                        "adaptive_risk_config": adaptive,
                                        "yield_post_solver_action_filter_mode": "apply",
                                        "yield_supervisor_behavioural_authority_mode": mode,
                                        "yield_rule_smpc_bypass_enabled": True,
                                        "yield_supervisor_mode": "reduced_intervention",
                                    },
                                    {
                                        "role": "target", "target_style": runtime_style,
                                        "policy_type": "defensive_reactive" if style == "reactive" else "straight",
                                        "init_speed": 9.0, "nominal_speed": 9.0,
                                        "start_longitudinal_offset": 0.0,
                                    },
                                ],
                            },
                            "smpc_debug_setup.json": {
                                "risk_profile": risk_profile,
                                "fixed_risk": policy != "adaptive",
                                "yield_stop_supervisor": {
                                    "mode": "reduced_intervention",
                                    "rule_smpc_bypass_enabled": True,
                                    "behavioural_authority": {
                                        "mode": mode,
                                        "authority_enabled": mode == "on",
                                    },
                                    "post_solver_action_filter": {
                                        "configured_mode": "apply",
                                        "mode": "apply" if mode == "on" else "monitor_only",
                                        "authority_enabled": mode == "on",
                                    },
                                },
                            },
                            "prediction_deployment_manifest.json": {
                                "status": "pass",
                                "model_artifact": {"sha256_tree": "synthetic-model"},
                                "calibration_artifact": {"sha256": "synthetic-calibration"},
                                "anchors_artifact": {"sha256": "synthetic-anchors"},
                                "warmup_passed": True,
                            },
                            "prediction_dataset/prediction_dataset_config.json": {
                                "stride": 1, "horizon": 10,
                                "dataset_metadata": {
                                    "ego_init_id": init_id, "protocol_id": "sf4_supervisor_behavioural_authority_v1",
                                    "cell_id": cell_id, "ego_policy": policy,
                                    "target_style": runtime_style, "map": "Town05",
                                },
                            },
                            "prediction_dataset/prediction_dataset_manifest.json": {"status": "pass"},
                            "smpc_completion.json": {"step": completion_step},
                        }
                        for relative, value in values.items():
                            path = scenario / relative
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text(json.dumps(value) + "\n")
                        debug = self.debug_rows(mode)
                        (scenario / "smpc_debug_steps.jsonl").write_text(
                            "".join(json.dumps(row) + "\n" for row in debug)
                        )
                        for relative in (
                            "prediction_dataset/prediction_dataset_raw.jsonl",
                            "prediction_dataset/prediction_dataset_labeled.jsonl",
                        ):
                            path = scenario / relative
                            path.parent.mkdir(parents=True, exist_ok=True)
                            path.write_text("{}\n")
                        with (scenario / "scenario_result.pkl").open("wb") as handle:
                            pickle.dump({"ego": {}}, handle)
                        (scenario / "scenario_steps.csv").write_text(
                            "step,ego_policy_run_step_wall_time_s,"
                            "ego_policy_done_after_step,"
                            "prediction_pipeline_wall_time_s\n"
                            + "".join(
                                "%d,%.6f,False,%.6f\n"
                                % (step, policy_wall_s, prediction_wall_s)
                                for step in range(8)
                            )
                        )
                        attempt_root = cell / "_attempts" / ("init_%d" % init_id)
                        attempt_dir = attempt_root / "attempt_001"
                        attempt_dir.mkdir(parents=True, exist_ok=True)
                        attempts.atomic_json(
                            attempt_dir / "attempt_started.json",
                            {
                                "schema_version": "r3_attempt_started_v2",
                                "attempt": 1,
                                "cell_id": cell_id,
                                "ego_init_id": init_id,
                                "started_at_utc": "2026-08-14T00:00:00+00:00",
                                "pid": 1,
                            },
                        )
                        record_path = attempt_dir / "attempt_record.json"
                        attempts.atomic_json(
                            record_path,
                            {
                                "schema_version": "r3_attempt_record_v2",
                                "attempt": 1,
                                "cell_id": cell_id,
                                "ego_init_id": init_id,
                                "accepted": True,
                                "classification": "accepted",
                                "retry_allowed": False,
                                "exit_code": 0,
                                "classifier_matches": [],
                                "raw_evidence_sha256_before_promotion": analysis.raw_evidence_hash(scenario),
                                "ended_at_utc": "2026-08-14T00:00:01+00:00",
                            },
                        )
                        ledger_path = attempts.refresh_ledger(
                            cell, cell_id, init_id, 10
                        )
                        attempts.write_receipt(
                            cell_dir=cell,
                            cell_id=cell_id,
                            init_id=init_id,
                            scenario_dir=scenario,
                            attempt_number=1,
                            record_path=record_path,
                            ledger_path=ledger_path,
                            recovery=False,
                            receipt_prefix="SF4",
                        )
        for cell in results.iterdir():
            evaluations = []
            for scenario in sorted(
                path for path in cell.iterdir()
                if path.is_dir() and path.name.startswith("scenario_")
            ):
                evaluations.append({
                    "scenario_dir": str(scenario), "completion_valid": True,
                    "pair_safety": [{
                        "footprint_margin_m": 0.25,
                        "min_footprint_separation_m": 1.25,
                        "footprint_collision": False,
                    }],
                    "footprint_margin_sensitivity": {
                        "0": [{
                            "footprint_margin_m": 0.0,
                            "min_footprint_separation_m": 1.75,
                            "footprint_collision": False,
                        }],
                        "0.25": [{
                            "footprint_margin_m": 0.25,
                            "min_footprint_separation_m": 1.25,
                            "footprint_collision": False,
                        }],
                        "0.35": [{
                            "footprint_margin_m": 0.35,
                            "min_footprint_separation_m": 1.05,
                            "footprint_collision": False,
                        }],
                        "0.5": [{
                            "footprint_margin_m": 0.5,
                            "min_footprint_separation_m": 0.75,
                            "footprint_collision": False,
                        }],
                    },
                    "yield_rules": [{"target_clears_before_ego_enters": True}],
                    "fixed_geometry_yield_rules": [{
                        "geometry_source": "controller_route_projection",
                        "target_clears_before_ego_enters": True,
                    }],
                })
            (cell / "postcarla_trajectory_gate.json").write_text(json.dumps({"evaluations": evaluations}) + "\n")
        contract = root / "sf4_contract.json"
        contract.write_text(json.dumps({
            "schema_version": "sf4_supervisor_behavioural_authority_run_contract_v1",
            "expected_rollouts": 80,
            "server_wall_time_contract": {
                "schema_version": "server_wall_time_diagnostics_v1",
                "clock": "time.perf_counter",
                "inferential_unit": "ego_init_id paired cluster",
                "server_side_diagnostic_only": True,
                "deployment_or_real_time_guarantee": False,
            },
            "cells": cells,
            "execution_order": order,
            "git_commit": "synthetic",
            "scenario": {"map": "Town05", "fps": 20, "max_iters": 600, "source_sha256": "scenario-hash"},
            "prediction_protocol_id": "sf4_supervisor_behavioural_authority_v1",
            "risk_profiles": {"adaptive": "adaptive_interaction_severity", "fixed_medium": "fixed_frontier_medium"},
            "target_styles_runtime": {"assertive": "assertive_constant_speed", "reactive": "defensive_reactive"},
            "target_conditions": {"start_longitudinal_offset_m": 0.0, "init_speed_mps": 9.0, "nominal_speed_mps": 9.0},
            "reactive_parameters": reactive,
            "adaptive_parameters": {
                "variant_name": "floor_weak", "approach_preclearance_floor": 1.66,
                "critical_preclearance_floor": 1.72, "near_preclearance_floor": 1.78,
            },
            "init_values": init_values,
            "hashes": {
                "prereg_json": analysis.sha256(prereg), "init_files": init_hashes,
                "supervisor_authority_tuning": {"on": "on-tuning", "off": "off-tuning"},
                "b1_model_tree": "synthetic-model", "b1_calibration": "synthetic-calibration",
                "anchors": "synthetic-anchors",
            },
        }) + "\n")
        return results, contract, prereg

    def test_end_to_end_cluster_did_and_manipulation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, contract, prereg = self.make_fixture(root)
            output = root / "analysis"
            payload = analysis.run(Namespace(
                results_dir=results, contract=contract, prereg=prereg, output_dir=output,
            ))
            self.assertEqual(payload["observed_rollouts"], 80)
            inference = json.loads((output / "sf4_inference.json").read_text())
            primary = inference["outcomes"]["failure_penalized_completion_time_s"]
            self.assertAlmostEqual(primary["mean_effect"], -1.5)
            self.assertEqual(primary["cluster_bootstrap_95ci"], [-1.5, -1.5])
            self.assertAlmostEqual(
                primary["exact_two_sided_sign_flip_sensitivity_value"], 2 / 1024
            )
            manipulation = json.loads((output / "sf4_manipulation_checks.json").read_text())
            observed = manipulation["observed_first_stage_activity"]
            self.assertEqual(observed["by_authority"]["off"]["authority_applied_fraction"], 0.0)
            self.assertEqual(observed["by_authority"]["on"]["authority_applied_fraction"], 1.0)
            self.assertEqual(observed["status"], "active")
            self.assertTrue((output / "sf4_primary_and_direct_effects.tex").is_file())
            behavioural_tex = (
                output / "sf4_behavioural_authority_effects.tex"
            ).read_text()
            self.assertIn("Minimum 0.25-m/actor", behavioural_tex)
            self.assertIn("Cautious approach progress", behavioural_tex)
            self.assertIn("First sustained-stop distance", behavioural_tex)
            self.assertIn("Signed stop-line error", behavioural_tex)
            self.assertIn("Stopped duration", behavioural_tex)
            self.assertIn("Nominal clear to actual-path release", behavioural_tex)
            self.assertIn("Actual-path release to sustained resume", behavioural_tex)
            self.assertIn("Buffered clear to sustained resume", behavioural_tex)
            self.assertIn("Adaptive minus fixed-medium, authority on", behavioural_tex)
            self.assertIn("Adaptive minus fixed-medium, authority off", behavioural_tex)
            self.assertIn("Authority on minus off, adaptive", behavioural_tex)
            self.assertIn("Authority on minus off, fixed-medium", behavioural_tex)
            self.assertIn("$n/10$", behavioural_tex)
            self.assertIn("not randomisation inference", behavioural_tex)
            self.assertIn("not bumper clearance", behavioural_tex)
            self.assertIn(
                "sf4_behavioural_authority_effects.tex", payload["products"]
            )
            self.assertEqual(
                inference["outcomes"]["cautious_approach_progress_m"][
                    "defined_init_clusters"
                ],
                10,
            )
            self.assertEqual(
                inference["outcomes"]["first_stop_distance_to_designed_stop_m"][
                    "defined_init_clusters"
                ],
                10,
            )
            self.assertTrue((output / "sf4_authority_manipulation_and_first_stage.tex").is_file())
            self.assertTrue((output / "sf4_computational_wall_time.tex").is_file())
            self.assertTrue((output / "sf4_controller_acceptance_and_solver_status.tex").is_file())
            self.assertIn("authority_effect_adaptive", inference["direct_paired_effects"]["failure_penalized_completion_time_s"])
            timing_did = inference["outcomes"]["ego_policy_wall_time_p50_ms"]
            self.assertAlmostEqual(timing_did["mean_effect"], 30.0)
            wall_time = json.loads(
                (output / "sf4_server_wall_time_diagnostics.json").read_text()
            )
            self.assertEqual(wall_time["status"], "pass")
            timing_tex = (output / "sf4_computational_wall_time.tex").read_text()
            self.assertIn("Shared prediction P50", timing_tex)
            self.assertIn("Shared prediction P95", timing_tex)
            self.assertIn("Shared prediction P99", timing_tex)
            report = (output / "SF4_ANALYSIS_REPORT.md").read_text()
            self.assertIn("shared-prediction P50", report)
            self.assertIn("not relabelled as a measured end-to-end", report)
            controller = json.loads(
                (output / "sf4_controller_acceptance_and_solver_status.json").read_text()
            )
            self.assertEqual(
                controller["full_matrix"]["factual_solver_attempts"], 600
            )
            self.assertEqual(
                controller["full_matrix"]["fallback_or_nonaccepted_attempts"],
                0,
            )
            self.assertGreater(
                controller["full_matrix"]["raw_solver_return_status_counts"][
                    "SUBOPTIMAL"
                ],
                0,
            )
            self.assertGreater(payload["solver_execution"]["bypass_requested_steps"], 0)
            self.assertGreater(payload["solver_execution"]["factual_solver_attempts"], 0)
            self.assertTrue(
                payload["solver_execution"][
                    "controller_acceptance_not_strict_optimizer_feasibility"
                ]
            )

    def test_goal_stop_after_release_is_not_a_give_way_stop(self):
        rows = []
        for step, speed in enumerate((2.0, 1.0, 1.0, 1.0, 0.1, 0.1, 0.1)):
            rows.append({
                "step": step,
                "vehicle_state": {"speed": speed},
                "yield_stop_supervisor": {
                    "active": step <= 1,
                    "phase": "hold_yield_line" if step <= 1 else "released_recovery",
                    "raw_reduced_clear_path_release": step >= 2,
                    "target_nominally_cleared_conflict": step >= 2,
                    "target_cleared_conflict": step >= 2,
                },
            })
        metrics = analysis.behavior_metrics(rows)
        self.assertIsNone(metrics["first_sustained_stop_step"])
        self.assertIsNone(metrics["first_stop_distance_to_conflict_m"])

    def test_cautious_progress_and_signed_stop_geometry_are_reconstructed(self):
        metrics = analysis.behavior_metrics(self.debug_rows("on"))
        self.assertEqual(metrics["yield_entry_step"], 0)
        self.assertEqual(metrics["first_sustained_stop_step"], 1)
        self.assertAlmostEqual(metrics["cautious_approach_progress_m"], 1.0)
        self.assertAlmostEqual(metrics["first_stop_distance_to_conflict_m"], 9.0)
        self.assertAlmostEqual(
            metrics["first_stop_distance_to_designed_stop_m"], 7.0
        )
        self.assertAlmostEqual(metrics["stopped_duration_s"], 0.2)

    def test_terminal_stop_with_entry_but_without_release_is_censored(self):
        rows = []
        for step, speed in enumerate((3.0, 2.0, 1.0, 1.0, 0.1, 0.1, 0.1)):
            rows.append({
                "step": step,
                "vehicle_state": {"speed": speed},
                "yield_stop_supervisor": {
                    "active": step <= 1,
                    "phase": (
                        "hold_yield_line" if step <= 1 else "inactive"
                    ),
                    "ego_distance_to_conflict": 50.0,
                    "raw_reduced_clear_path_release": False,
                    "target_nominally_cleared_conflict": False,
                    "target_cleared_conflict": False,
                },
            })
        metrics = analysis.behavior_metrics(rows)
        self.assertEqual(metrics["yield_entry_step"], 0)
        self.assertIsNone(metrics["actual_path_release_step"])
        self.assertIsNone(metrics["first_sustained_stop_step"])
        self.assertIsNone(metrics["first_stop_distance_to_conflict_m"])

    def test_terminal_stop_without_yield_entry_does_not_create_events(self):
        rows = []
        for step, speed in enumerate((3.0, 2.0, 1.0, 0.1, 0.1, 0.1)):
            rows.append({
                "step": step,
                "vehicle_state": {"speed": speed},
                "yield_stop_supervisor": {
                    "active": False,
                    "phase": "inactive",
                    # These deliberately stale/terminal flags must not create
                    # give-way clocks without an observed yield entry.
                    "raw_reduced_clear_path_release": step >= 2,
                    "target_nominally_cleared_conflict": step >= 2,
                    "target_cleared_conflict": step >= 2,
                    "ego_distance_to_conflict": 99.0,
                },
            })
        metrics = analysis.behavior_metrics(rows)
        self.assertTrue(all(value is None for value in metrics.values()))

    def test_wall_time_nonfinite_is_reported_without_imputation(self):
        def block(values, nonfinite=0):
            finite = list(values)
            value = finite[0] if finite else None
            return {
                "observed_sample_count": len(finite) + nonfinite,
                "finite_sample_count": len(finite),
                "nonfinite_sample_count": nonfinite,
                "exception_count": 0,
                "thresholds_ms": [50.0, 200.0, 500.0],
                "mean_s": value,
                "p50_s": value,
                "p95_s": value,
                "p99_s": value,
                "max_s": value,
                "over_50ms_fraction": (
                    float(value > 0.050) if value is not None else None
                ),
                "over_200ms_fraction": (
                    float(value > 0.200) if value is not None else None
                ),
                "over_500ms_fraction": (
                    float(value > 0.500) if value is not None else None
                ),
            }

        diagnostics = {
            "schema_version": "server_wall_time_diagnostics_v1",
            "clock": "time.perf_counter",
            "server_side_diagnostic_only": True,
            "deployment_or_real_time_guarantee": False,
            "active_planning_definition": (
                "ego policy.done() is false immediately after run_step"
            ),
            "ego_policy_all_invocations": block([0.1], nonfinite=1),
            "ego_policy_active_planning_invocations": block(
                [0.1], nonfinite=1
            ),
            "prediction_all_invocations": {
                **block([0.01, 0.01]),
                "mean_s": 0.01,
            },
            "prediction_during_ego_active_planning": {
                **block([0.01, 0.01]),
                "mean_s": 0.01,
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scenario_steps.csv"
            path.write_text(
                "step,ego_policy_run_step_wall_time_s,"
                "ego_policy_done_after_step,prediction_pipeline_wall_time_s\n"
                "0,0.1,False,0.01\n"
                "1,,False,0.01\n"
            )
            result = analysis.wall_time_metrics(
                path, {"extra": {"server_wall_time_diagnostics": diagnostics}}
            )
        self.assertEqual(
            result["status"], "partial_nonfinite_or_missing_secondary"
        )
        self.assertEqual(result["ego_policy_wall_time_nonfinite_count"], 1)
        self.assertIsNone(result["ego_policy_wall_time_p50_ms"])
        self.assertAlmostEqual(result["prediction_wall_time_p99_ms"], 10.0)

    def test_zero_observed_activity_is_retained_scientific_outcome(self):
        template = {
            "debug_steps": 4,
            "supervisor_any_channel_requested_fraction": 0.0,
            "supervisor_candidate_requested_fraction": 0.0,
            "supervisor_authority_applied_fraction": 0.0,
            "upstream_reference_requested_fraction": 0.0,
            "upstream_heading_cost_requested_fraction": 0.0,
            "upstream_reference_linearization_requested_fraction": 0.0,
            "rule_smpc_bypass_requested_fraction": 0.0,
            "rule_smpc_bypass_applied_fraction": 0.0,
            "factual_solver_attempted_fraction": 1.0,
            "upstream_reference_states_max_abs_delta_mean": 0.0,
            "upstream_reference_inputs_max_abs_delta_mean": 0.0,
            "upstream_heading_cost_max_abs_weight_mean": 0.0,
            "upstream_linearization_states_max_abs_delta_mean": 0.0,
            "candidate_minus_nominal_accel_abs_mean_mps2": 0.0,
            "actual_minus_nominal_accel_abs_mean_mps2": 0.0,
        }
        rows = [
            {
                **template,
                "supervisor_authority_mode": mode,
                "risk_policy": risk,
                "target_style": style,
            }
            for mode in ("on", "off")
            for risk in ("adaptive", "fixed_medium")
            for style in ("assertive", "reactive")
        ]
        result = analysis.manipulation_summary(rows)
        self.assertEqual(result["status"], "pass")
        observed = result["observed_first_stage_activity"]
        self.assertEqual(observed["status"], "inactive_scientific_outcome")
        self.assertFalse(observed["zero_activity_triggers_extra_rollouts"])

    def test_collision_and_yield_failure_are_accepted_scientific_outcomes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, contract_path, _ = self.make_fixture(root)
            contract = json.loads(contract_path.read_text())
            item = contract["execution_order"][0]
            cell = results / item["cell_id"]
            receipt_path = cell / ("SF4_ROLLOUT_%d_COMPLETE.json" % item["ego_init_id"])
            receipt = json.loads(receipt_path.read_text())
            scenario = cell / receipt["scenario_dir"]
            summary_path = scenario / "scenario_run_summary.json"
            summary = json.loads(summary_path.read_text())
            summary["extra"].update({
                "collision_event_count": 1,
                "collision_events": [{"collision_category": "ego_target"}],
                "collision_terminated": True,
            })
            summary_path.write_text(json.dumps(summary) + "\n")
            (scenario / "smpc_completion.json").unlink()
            record_path = cell / receipt["attempt_record"]
            record = json.loads(record_path.read_text())
            record["raw_evidence_sha256_before_promotion"] = analysis.raw_evidence_hash(scenario)
            attempts.atomic_json(record_path, record)
            ledger_path = attempts.refresh_ledger(
                cell, item["cell_id"], int(item["ego_init_id"]), 10
            )
            attempts.write_receipt(
                cell_dir=cell,
                cell_id=item["cell_id"],
                init_id=int(item["ego_init_id"]),
                scenario_dir=scenario,
                attempt_number=1,
                record_path=record_path,
                ledger_path=ledger_path,
                recovery=False,
                receipt_prefix="SF4",
            )
            gate_path = cell / "postcarla_trajectory_gate.json"
            gate = json.loads(gate_path.read_text())
            match = next(value for value in gate["evaluations"] if Path(value["scenario_dir"]).name == scenario.name)
            match["completion_valid"] = False
            match["fixed_geometry_yield_rules"] = [{
                "geometry_source": "controller_route_projection",
                "target_clears_before_ego_enters": False,
            }]
            gate_path.write_text(json.dumps(gate) + "\n")
            row, _ = analysis.analyze_rollout(results, item, contract)
            self.assertEqual(row["failure_penalized_completion_time_s"], 30.0)
            self.assertEqual(row["native_collision_any"], 1)
            self.assertEqual(row["adverse_collision_any"], 1)
            self.assertEqual(row["yield_rule_failure"], 1)
            self.assertTrue(
                attempts.valid_receipt(
                    cell, item["cell_id"], int(item["ego_init_id"]), "SF4"
                )
            )
            self.assertEqual(
                len([
                    path
                    for path in (cell / "_attempts" / "init_106").glob("attempt_*")
                    if path.is_dir()
                ]),
                1,
            )

    def test_primary_yield_penalty_uses_fixed_route_geometry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, contract_path, _ = self.make_fixture(root)
            contract = json.loads(contract_path.read_text())
            item = contract["execution_order"][0]
            cell = results / item["cell_id"]
            receipt = json.loads(
                (cell / ("SF4_ROLLOUT_%d_COMPLETE.json" % item["ego_init_id"])).read_text()
            )
            scenario = cell / receipt["scenario_dir"]
            gate_path = cell / "postcarla_trajectory_gate.json"
            gate = json.loads(gate_path.read_text())
            match = next(
                value for value in gate["evaluations"]
                if Path(value["scenario_dir"]).name == scenario.name
            )
            # Realised-trajectory geometry disagrees, but the frozen
            # route-projected geometry remains the primary definition.
            match["yield_rules"] = [{"target_clears_before_ego_enters": False}]
            match["fixed_geometry_yield_rules"] = [{
                "geometry_source": "controller_route_projection",
                "target_clears_before_ego_enters": True,
            }]
            gate_path.write_text(json.dumps(gate) + "\n")
            row, _ = analysis.analyze_rollout(results, item, contract)
            self.assertEqual(row["yield_rule_failure"], 0)
            self.assertEqual(row["trajectory_inferred_yield_rule_failure"], 1)
            self.assertEqual(row["completion_success"], 1)

    def test_physical_overlap_and_margin_violation_are_not_conflated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, contract_path, _ = self.make_fixture(root)
            contract = json.loads(contract_path.read_text())
            item = contract["execution_order"][0]
            cell = results / item["cell_id"]
            receipt = json.loads(
                (cell / ("SF4_ROLLOUT_%d_COMPLETE.json" % item["ego_init_id"])).read_text()
            )
            scenario = cell / receipt["scenario_dir"]
            gate_path = cell / "postcarla_trajectory_gate.json"
            gate = json.loads(gate_path.read_text())
            match = next(
                value for value in gate["evaluations"]
                if Path(value["scenario_dir"]).name == scenario.name
            )
            primary = match["footprint_margin_sensitivity"]["0.25"][0]
            primary.update({
                "min_footprint_separation_m": 0.0,
                "footprint_collision": True,
            })
            match["pair_safety"][0].update({
                "min_footprint_separation_m": 0.0,
                "footprint_collision": True,
            })
            gate_path.write_text(json.dumps(gate) + "\n")
            row, _ = analysis.analyze_rollout(results, item, contract)
            self.assertEqual(row["margin_adjusted_bbox_violation_any"], 1)
            self.assertEqual(row["physical_bbox_overlap_any"], 0)
            self.assertEqual(row["adverse_collision_any"], 0)
            self.assertEqual(row["completion_success"], 1)

            zero_margin = match["footprint_margin_sensitivity"]["0"][0]
            zero_margin.update({
                "min_footprint_separation_m": 0.0,
                "footprint_collision": True,
            })
            gate_path.write_text(json.dumps(gate) + "\n")
            row, _ = analysis.analyze_rollout(results, item, contract)
            self.assertEqual(row["physical_bbox_overlap_any"], 1)
            self.assertEqual(row["adverse_collision_any"], 1)
            self.assertEqual(row["completion_success"], 0)
            self.assertEqual(row["failure_penalized_completion_time_s"], 30.0)

    def test_receipt_allows_only_infrastructure_retries_before_unique_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, contract_path, _ = self.make_fixture(root)
            item = json.loads(contract_path.read_text())["execution_order"][0]
            cell = results / item["cell_id"]
            init_id = int(item["ego_init_id"])
            receipt_path = cell / ("SF4_ROLLOUT_%d_COMPLETE.json" % init_id)
            original = json.loads(receipt_path.read_text())
            scenario = cell / original["scenario_dir"]
            init_root = cell / "_attempts" / ("init_%d" % init_id)
            accepted_dir = init_root / "attempt_002"
            (init_root / "attempt_001").rename(accepted_dir)
            accepted_started = json.loads(
                (accepted_dir / "attempt_started.json").read_text()
            )
            accepted_started["attempt"] = 2
            attempts.atomic_json(accepted_dir / "attempt_started.json", accepted_started)
            accepted_record = json.loads(
                (accepted_dir / "attempt_record.json").read_text()
            )
            accepted_record["attempt"] = 2
            attempts.atomic_json(accepted_dir / "attempt_record.json", accepted_record)
            failed_dir = init_root / "attempt_001"
            failed_dir.mkdir()
            attempts.atomic_json(
                failed_dir / "attempt_started.json",
                {
                    "schema_version": "r3_attempt_started_v2",
                    "attempt": 1,
                    "cell_id": item["cell_id"],
                    "ego_init_id": init_id,
                    "started_at_utc": "2026-08-13T23:59:00+00:00",
                    "pid": 1,
                },
            )
            failed_record_path = failed_dir / "attempt_record.json"
            failed_record = {
                "schema_version": "r3_attempt_record_v2",
                "attempt": 1,
                "cell_id": item["cell_id"],
                "ego_init_id": init_id,
                "accepted": False,
                "classification": "infrastructure_failure",
                "retry_allowed": True,
                "exit_code": 1,
                "classifier_matches": ["spawn_collision"],
                "ended_at_utc": "2026-08-13T23:59:01+00:00",
            }
            attempts.atomic_json(failed_record_path, failed_record)
            ledger = attempts.refresh_ledger(cell, item["cell_id"], init_id, 10)
            attempts.write_receipt(
                cell_dir=cell,
                cell_id=item["cell_id"],
                init_id=init_id,
                scenario_dir=scenario,
                attempt_number=2,
                record_path=accepted_dir / "attempt_record.json",
                ledger_path=ledger,
                recovery=False,
                receipt_prefix="SF4",
            )
            self.assertTrue(
                attempts.valid_receipt(cell, item["cell_id"], init_id, "SF4")
            )
            # Reclassifying the first attempt as a scientific/non-infrastructure
            # failure cannot be laundered into a valid retry receipt.
            failed_record.update(
                {
                    "classification": "unknown_nonretryable_failure",
                    "retry_allowed": False,
                    "classifier_matches": [],
                }
            )
            attempts.atomic_json(failed_record_path, failed_record)
            ledger = attempts.refresh_ledger(cell, item["cell_id"], init_id, 10)
            attempts.write_receipt(
                cell_dir=cell,
                cell_id=item["cell_id"],
                init_id=init_id,
                scenario_dir=scenario,
                attempt_number=2,
                record_path=accepted_dir / "attempt_record.json",
                ledger_path=ledger,
                recovery=False,
                receipt_prefix="SF4",
            )
            self.assertFalse(
                attempts.valid_receipt(cell, item["cell_id"], init_id, "SF4")
            )

    def test_receipt_rejects_any_attempt_after_acceptance(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, contract_path, _ = self.make_fixture(root)
            item = json.loads(contract_path.read_text())["execution_order"][0]
            cell = results / item["cell_id"]
            init_id = int(item["ego_init_id"])
            later = cell / "_attempts" / ("init_%d" % init_id) / "attempt_002"
            later.mkdir()
            for name, value in (
                (
                    "attempt_started.json",
                    {
                        "attempt": 2, "cell_id": item["cell_id"],
                        "ego_init_id": init_id,
                    },
                ),
                (
                    "attempt_record.json",
                    {
                        "attempt": 2, "cell_id": item["cell_id"],
                        "ego_init_id": init_id, "accepted": False,
                        "classification": "infrastructure_failure",
                        "retry_allowed": True,
                        "classifier_matches": ["carla_timeout"],
                    },
                ),
            ):
                attempts.atomic_json(later / name, value)
            ledger = attempts.refresh_ledger(cell, item["cell_id"], init_id, 10)
            receipt_path = cell / ("SF4_ROLLOUT_%d_COMPLETE.json" % init_id)
            receipt = json.loads(receipt_path.read_text())
            receipt["attempt_ledger_sha256_at_receipt"] = attempts.sha256(ledger)
            attempts.atomic_json(receipt_path, receipt)
            self.assertFalse(
                attempts.valid_receipt(cell, item["cell_id"], init_id, "SF4")
            )

    def test_compact_package_is_deterministic_and_verifiable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, contract, prereg = self.make_fixture(root)
            analysis.run(Namespace(
                results_dir=results, contract=contract, prereg=prereg,
                output_dir=results / "analysis",
            ))
            (results / "sf4_supervisor_behavioural_authority_run_contract.json").write_bytes(contract.read_bytes())
            for relative in packager.TOP_LEVEL:
                path = results / relative
                if path.is_file():
                    continue
                payload = {"status": "pass"}
                if relative == "SF4_COMPLETE.json":
                    payload.update({"observed_rollouts": 80})
                path.write_text(json.dumps(payload) + "\n")
            tuning = results / "_frozen_tuning"
            tuning.mkdir()
            (tuning / "supervisor_authority_on.json").write_text("{}\n")
            (tuning / "supervisor_authority_off.json").write_text("{}\n")
            first = root / "first.tar.gz"
            second = root / "second.tar.gz"
            one = packager.create(results, first)
            two = packager.create(results, second)
            self.assertEqual(one["archive_sha256"], two["archive_sha256"])
            verified = packager.verify(first)
            self.assertEqual(verified["status"], "pass")
            self.assertEqual(verified["included_files"], one["included_files"])

    def test_full_raw_snapshot_is_deterministic_resumable_and_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            results, contract, prereg = self.make_fixture(root)
            analysis.run(Namespace(
                results_dir=results, contract=contract, prereg=prereg,
                output_dir=results / "analysis",
            ))
            (results / "sf4_supervisor_behavioural_authority_run_contract.json").write_bytes(
                contract.read_bytes()
            )
            for relative in full_packager.TOP_LEVEL_REQUIRED:
                path = results / relative
                if path.is_file():
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({"status": "pass"}) + "\n")
            tuning = results / "_frozen_tuning"
            tuning.mkdir()
            (tuning / "supervisor_authority_on.json").write_text("{}\n")
            (tuning / "supervisor_authority_off.json").write_text("{}\n")
            output = (
                results
                / "sf4_supervisor_behavioural_authority_full_raw_snapshot.tar.gz"
            )
            first = full_packager.create(results, output, prereg)
            second = full_packager.create(results, output, prereg)
            self.assertEqual(first["archive_sha256"], second["archive_sha256"])
            self.assertFalse(first["reused_verified_archive"])
            self.assertTrue(second["reused_verified_archive"])
            verified = full_packager.verify(output)
            self.assertEqual(verified["status"], "pass")
            self.assertEqual(verified["observed_rollouts"], 80)
            files = json.loads(
                full_packager.files_manifest_path(output).read_text()
            )["files"]
            names = {item["path"] for item in files}
            self.assertTrue(any(name.endswith("/scenario_result.pkl") for name in names))
            self.assertTrue(any(name.endswith("/scenario_steps.csv") for name in names))
            self.assertTrue(any("/_attempts/" in ("/" + name) for name in names))
            source_pickle = next(results.glob("SF4_*/scenario_*/scenario_result.pkl"))
            self.assertTrue(source_pickle.is_file())
            marker = json.loads((results / full_packager.MARKER_NAME).read_text())
            self.assertTrue(marker["bbox_and_separation_recomputation_supported"])
            self.assertTrue(marker["server_wall_time_recomputation_supported"])
            self.assertTrue(
                marker[
                    "controller_acceptance_and_raw_status_recomputation_supported"
                ]
            )
            self.assertFalse(marker["source_files_deleted"])


if __name__ == "__main__":
    unittest.main()
