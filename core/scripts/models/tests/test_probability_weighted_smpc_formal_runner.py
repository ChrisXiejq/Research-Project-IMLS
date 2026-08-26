import re
import unittest
from pathlib import Path


RUNNER = (
    Path(__file__).resolve().parents[2]
    / "carla"
    / "run_probability_weighted_v2_recovery_formal.sh"
)


class ProbabilityWeightedFormalRunnerTest(unittest.TestCase):
    def test_frozen_supervisor_on_matrix_has_eighty_unique_rollouts(self):
        source = RUNNER.read_text()
        matrix = source.split("done <<'CELLS'", 1)[1].split("CELLS", 1)[0]
        rows = [line.split() for line in matrix.splitlines() if line.strip()]

        self.assertEqual(len(rows), 8)
        self.assertTrue(all(len(row) == 4 for row in rows))
        self.assertEqual(len({row[0] for row in rows}), 8)
        self.assertEqual({row[1] for row in rows}, {"B1", "P_star"})
        self.assertEqual({row[2] for row in rows}, {"fixed_medium", "adaptive"})
        self.assertEqual(
            {row[3] for row in rows},
            {"assertive_constant_speed", "defensive_reactive"},
        )
        self.assertIn("for init_id in {126..135}", source)
        self.assertRegex(source, r'expected\s*=\s*80')
        self.assertIn('"expected_unique_rollouts": 80', source)

    def test_runner_is_supervisor_on_and_probability_weighted(self):
        source = RUNNER.read_text()
        self.assertIn('"supervisor_authority": "on"', source)
        self.assertIn(
            '"objective_id": "multipath_joint_probability_expected_cost_v2"',
            source,
        )
        self.assertIn('"objective_unweighted_option_available": False', source)
        self.assertNotIn("rule_absent", source)
        self.assertNotRegex(source, re.compile(r"fixed_(aggressive|conservative)"))


if __name__ == "__main__":
    unittest.main()
