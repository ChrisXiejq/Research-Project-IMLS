
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import os
import unittest

import numpy as np

try:
    import casadi as ca
except ImportError:  # Local documentation environments need not ship Gurobi/CasADi.
    ca = None


@unittest.skipIf(ca is None, "CasADi solver test runs in the CARLA/Gurobi environment")
class ProbabilityWeightedSmpcSolverTests(unittest.TestCase):
    @staticmethod
    def _solve(probabilities, adaptive_risk):
        from core.scripts.carla.utils.mpc_utils import (
            _probability_weighted_active_branch_cost,
        )

        probabilities = np.asarray(probabilities, dtype=float)
        opti = ca.Opti("conic")
        command = opti.variable()
        mode_probabilities = opti.parameter(3)
        branch_targets = (-2.0, 0.0, 4.0)
        branch_costs = [
            (command - target) ** 2 for target in branch_targets
        ]
        objective = _probability_weighted_active_branch_cost(
            branch_costs,
            mode_probabilities,
        )
        opti.subject_to(opti.bounded(-10.0, command, 10.0))
        if adaptive_risk:
            branch_safety = opti.variable(3)
            opti.subject_to(opti.bounded(0.5, branch_safety, 1.0))
            opti.subject_to(
                ca.dot(mode_probabilities, branch_safety) >= 0.8
            )
            objective += 1.0e-4 * ca.sumsqr(branch_safety - 0.8)
        opti.minimize(objective)
        solver_name = os.environ.get("SMPC_NUMERICAL_TEST_SOLVER", "gurobi")
        solver_options = {"OutputFlag": 0} if solver_name == "gurobi" else {}
        opti.solver(
            solver_name,
            {"error_on_fail": True},
            solver_options,
        )
        opti.set_value(mode_probabilities, probabilities)
        solution = opti.solve()
        return float(solution.value(command)), float(solution.value(objective))

    def test_asymmetric_probability_swap_changes_solution_in_expected_direction(self):
        for adaptive_risk in (False, True):
            with self.subTest(adaptive_risk=adaptive_risk):
                left_weighted, left_objective = self._solve(
                    [0.80, 0.15, 0.05], adaptive_risk
                )
                right_weighted, right_objective = self._solve(
                    [0.05, 0.15, 0.80], adaptive_risk
                )
                self.assertAlmostEqual(left_weighted, -1.4, places=5)
                self.assertAlmostEqual(right_weighted, 3.1, places=5)
                self.assertGreater(right_weighted - left_weighted, 4.0)
                self.assertTrue(np.isfinite(left_objective))
                self.assertTrue(np.isfinite(right_objective))

    def test_uniform_probabilities_recover_the_branch_target_mean(self):
        command, objective = self._solve([1.0 / 3.0] * 3, False)
        self.assertAlmostEqual(command, 2.0 / 3.0, places=5)
        self.assertTrue(np.isfinite(objective))

    def test_shared_policy_cost_has_unit_weight(self):
        from core.scripts.carla.utils.mpc_utils import (
            _probability_weighted_active_branch_cost,
        )

        shared_cost = ca.MX(7.5)
        probability_vector = ca.MX.sym("probability_vector", 3)
        expression = _probability_weighted_active_branch_cost(
            [shared_cost], probability_vector
        )
        evaluated = ca.Function("shared_cost", [], [expression])()["o0"]
        self.assertEqual(float(evaluated), 7.5)


if __name__ == "__main__":
    unittest.main()
