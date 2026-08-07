from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path


MODELS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODELS_DIR))

from distinction_analysis_utils import (  # noqa: E402
    assert_equal_lengths,
    assert_single_result_generation,
    collision_episodes,
    resolve_json_pointer,
)


class DistinctionRegressionGateTests(unittest.TestCase):
    def test_json_pointer_escaping_and_failure(self):
        payload = {"a/b": {"~key": [4, 7]}}
        self.assertEqual(resolve_json_pointer(payload, "/a~1b/~0key/1"), 7)
        with self.assertRaises(KeyError):
            resolve_json_pointer(payload, "/missing")

    def test_collision_callbacks_are_collapsed_to_episodes(self):
        self.assertEqual(collision_episodes([10, 10, 11, 12, 17, 18]), [[10, 11, 12], [17, 18]])

    def test_all_lengths_must_match(self):
        self.assertEqual(assert_equal_lengths({"a": [1, 2], "b": [3, 4]}), 2)
        with self.assertRaises(ValueError):
            assert_equal_lengths({"a": [1], "b": [2, 3], "c": [4]})

    def test_result_generations_cannot_be_mixed(self):
        records = [{"result_generation": "distinction_v1"}, {"result_generation": "distinction_v1"}]
        self.assertEqual(assert_single_result_generation(records), "distinction_v1")
        with self.assertRaises(ValueError):
            assert_single_result_generation(
                [{"result_generation": "legacy_day12"}, {"result_generation": "distinction_v1"}]
            )


class CorrectedControlContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(__file__).resolve().parents[4]
        cls.mpc_path = cls.repo / "core/scripts/carla/utils/mpc_utils.py"
        cls.agent_path = cls.repo / "core/scripts/carla/policies/smpc_agent.py"
        cls.scenario_path = cls.repo / "core/scripts/carla/scenarios/run_intersection_scenario.py"
        tree = ast.parse(cls.mpc_path.read_text(encoding="utf-8"))
        selected = [
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in {
                "_joint_mode_component",
                "_mode_component",
                "_mode_consumption_map",
            }
        ]
        namespace = {}
        exec(compile(ast.Module(body=selected, type_ignores=[]), "<mode-contract>", "exec"), namespace)
        cls.mode = staticmethod(namespace["_mode_component"])
        cls.mode_map = staticmethod(namespace["_mode_consumption_map"])

    def test_corrected_single_tv_consumes_all_three_spatial_modes(self):
        for profile in (
            "upstream_code",
            "fixed_frontier_medium",
            "adaptive_interaction_severity",
        ):
            self.assertEqual(
                [self.mode(j, 0, 3, 1, profile) for j in range(3)],
                [0, 1, 2],
            )
        self.assertEqual(self.mode_map(3, 1), [[0], [1], [2]])

    def test_multi_tv_base_k_joint_mode_mapping(self):
        expected = [[j % 3, (j // 3) % 3] for j in range(9)]
        self.assertEqual(self.mode_map(3, 2), expected)

    def test_legacy_mode_collapse_requires_explicit_flag(self):
        self.assertEqual(
            [self.mode(j, 0, 3, 1, legacy_mode_indexing=True) for j in range(3)],
            [0, 0, 0],
        )

    def test_corrected_version_and_shared_amin_are_default(self):
        agent = self.agent_path.read_text(encoding="utf-8")
        scenario = self.scenario_path.read_text(encoding="utf-8")
        self.assertIn(
            "control_implementation_version=smpc.CONTROL_IMPLEMENTATION_CORRECTED_V1",
            agent,
        )
        self.assertIn(
            'control_implementation_version : str = "corrected_joint_modes_shared_amin_v1"',
            scenario,
        )
        self.assertIn("self._solver_a_min = -4.0 if self._legacy_control_implementation else -3.0", agent)
        self.assertIn("A_MIN=self._solver_a_min", agent)
        self.assertIn("return self._ref_gen_a_min, self._ref_gen_a_max", agent)

    def test_every_step_prediction_log_contains_mode_hash_contract(self):
        agent = self.agent_path.read_text(encoding="utf-8")
        for token in (
            'payload["mode_consumption"]',
            '"spatial_mode_index"',
            '"mean_sha256"',
            '"covariance_sha256"',
        ):
            self.assertIn(token, agent)


if __name__ == "__main__":
    unittest.main()
