import re
import json
import unittest
from pathlib import Path


RUNNER = (
    Path(__file__).resolve().parents[2]
    / "carla"
    / "run_probability_weighted_v2_recovery_formal.sh"
)


class ProbabilityWeightedFormalRunnerTest(unittest.TestCase):
    def test_frozen_supervisor_on_matrix_has_forty_unique_rollouts(self):
        source = RUNNER.read_text()
        self.assertIn("for predictor in B1 P_star", source)
        self.assertIn("for risk in fixed_medium adaptive", source)
        self.assertIn("for init_id in {126..135}", source)
        self.assertIn(
            'expected = 40 if authority_mode == "on" else 20', source
        )
        self.assertIn(
            "expected_unique_rollouts = len(cells) * len(formal_init_ids)",
            source,
        )
        self.assertIn('"target_controller_uses_ego_state": False', source)
        self.assertIn('"reference_generator_max_cpu_time_s": 2.0', source)
        self.assertIn(
            '"invalid_reference_solution_policy": '
            '"reject_initial_retain_last_valid_closed_loop"',
            source,
        )
        self.assertIn('ALLOW_ORCHESTRATION_RECOVERY', source)
        self.assertIn('"execution_complete": True', source)
        self.assertIn('"matrix_execution_complete"', source)
        self.assertNotIn("Formal rollout gate failed", source)

    def test_matched_off_extension_adds_twenty_unique_rollouts(self):
        source = RUNNER.read_text()
        self.assertIn('SUPERVISOR_AUTHORITY_MODE="${SUPERVISOR_AUTHORITY_MODE:-on}"', source)
        self.assertIn("formal_supervisor_off_assertive_20", source)
        self.assertIn('predictors = ("B1", "P_star")', source)
        self.assertIn("formal_init_ids = list(range(126, 131))", source)
        self.assertGreaterEqual(source.count("for predictor in B1 P_star"), 2)
        self.assertIn("for init_id in {126..130}", source)
        self.assertIn('"campaign_id": "probability_weighted_joint_mode_smpc_h2_h3_assertive_unique_60_v2"', source)
        self.assertIn('"authority_integrity_pass": True', source)
        self.assertIn('"implementation_manipulation_gate"', source)
        self.assertIn('"reference_and_solver_input_audit"', source)
        self.assertIn('"post_action_and_next_state_audit"', source)
        self.assertIn('"complete_candidate_channel_manifest"', source)
        self.assertIn('if authority_failures:', source)

    def test_off_tuning_differs_only_in_authority_after_defaults(self):
        tuning_dir = RUNNER.parent / "scenarios" / "tuning_configs"
        on = json.loads(
            (tuning_dir / "give_way_reduced_clear_path_release_v13_risk_owned_yield.json").read_text()
        )
        off = json.loads(
            (tuning_dir / "give_way_probability_weighted_v2_supervisor_off_matched.json").read_text()
        )
        on_ego = dict(on["vehicle_role_overrides"]["ego"])
        off_ego = dict(off["vehicle_role_overrides"]["ego"])
        on_ego.setdefault("yield_rule_smpc_bypass_enabled", True)
        on_ego.setdefault("yield_post_solver_action_filter_mode", "apply")
        on_ego.setdefault("yield_supervisor_behavioural_authority_mode", "on")
        self.assertEqual(on_ego.pop("yield_supervisor_behavioural_authority_mode"), "on")
        self.assertEqual(off_ego.pop("yield_supervisor_behavioural_authority_mode"), "off")
        self.assertEqual(on_ego, off_ego)
        self.assertEqual(
            on["vehicle_role_overrides"]["target"],
            off["vehicle_role_overrides"]["target"],
        )

    def test_runner_is_supervisor_on_and_probability_weighted(self):
        source = RUNNER.read_text()
        self.assertIn('"supervisor_authority": authority_mode', source)
        self.assertIn(
            '"objective_id": "multipath_joint_probability_expected_cost_v2"',
            source,
        )
        self.assertIn('"smpc_model": repo / "core/scripts/carla/utils/mpc_utils.py"', source)
        self.assertIn('"objective_unweighted_option_available": False', source)
        self.assertNotIn("give_way_probability_weighted_v2_rule_absent_matched", source)
        self.assertNotRegex(source, re.compile(r"fixed_(aggressive|conservative)"))
        self.assertNotIn("defensive_reactive", source)


if __name__ == "__main__":
    unittest.main()
