
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import json
import unittest
from pathlib import Path


CONFIG_DIR = (
    Path(__file__).resolve().parents[2]
    / "carla"
    / "scenarios"
    / "tuning_configs"
)


class RuleAbsentMatchedConfigTest(unittest.TestCase):
    def test_only_supervisor_execution_fields_change_from_on_arm(self):
        with (CONFIG_DIR / "give_way_reduced_clear_path_release_v13_risk_owned_yield.json").open() as handle:
            enabled = json.load(handle)["vehicle_role_overrides"]
        with (CONFIG_DIR / "give_way_probability_weighted_v2_rule_absent_matched.json").open() as handle:
            absent = json.load(handle)["vehicle_role_overrides"]

        expected_changes = {
            "yield_stop_enabled": (True, False),
            "yield_stop_line_creep_enabled": (True, False),
            "yield_dynamic_stop_clearance_enabled": (True, False),
            "yield_emergency_brake_enabled": (True, False),
            "yield_observed_caution_enabled": (True, False),
            "smpc_intersection_approach_speed_shaping_enabled": (True, False),
            "yield_planner_ownership_stress_enabled": (True, False),
            "yield_risk_owned_yield_enabled": (True, False),
            "yield_recovery_enabled": (True, False),
            "yield_rule_smpc_bypass_enabled": (None, False),
            "yield_post_solver_action_filter_mode": (None, "monitor_only"),
            "yield_supervisor_behavioural_authority_mode": (None, "off"),
            "supervisor_free_smpc_enabled": (None, True),
            "implicit_safety_filter_enabled": (None, False),
            "lane_entry_heading_cost_enabled": (None, False),
        }
        enabled_ego = enabled["ego"]
        absent_ego = absent["ego"]
        all_keys = set(enabled_ego) | set(absent_ego)
        observed_changes = {
            key: (enabled_ego.get(key), absent_ego.get(key))
            for key in all_keys
            if enabled_ego.get(key) != absent_ego.get(key)
        }
        self.assertEqual(observed_changes, expected_changes)
        self.assertEqual(enabled["target"], absent["target"])


if __name__ == "__main__":
    unittest.main()
