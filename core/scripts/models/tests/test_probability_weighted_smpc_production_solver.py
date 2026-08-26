import os
import unittest

import numpy as np


@unittest.skipUnless(
    os.environ.get("RUN_PRODUCTION_GUROBI_SMOKE") == "1",
    "Production SMPC smoke runs only in the licensed CARLA/Gurobi environment",
)
class ProbabilityWeightedProductionSmpcTests(unittest.TestCase):
    @staticmethod
    def _update_payload(horizon):
        dt = 0.2
        speed = 5.0
        x_reference = dt * speed * np.arange(horizon + 1, dtype=float)
        zeros = np.zeros(horizon + 1, dtype=float)
        mode_means = np.full((3, horizon, 2), 20.0, dtype=float)
        mode_covariances = np.tile(
            np.eye(2, dtype=float), (3, horizon, 1, 1)
        )
        target_shapes = [
            [0.1 * np.eye(2, dtype=float) for _ in range(horizon)]
            for _ in range(3)
        ]
        return {
            "dx0": 0.0,
            "dy0": 0.0,
            "dpsi0": 0.0,
            "dv0": 0.0,
            "Rs_ev": [np.eye(2, dtype=float) for _ in range(horizon)],
            "x_tv0": [20.0],
            "y_tv0": [20.0],
            "x_ref": x_reference,
            "y_ref": zeros,
            "psi_ref": zeros,
            "v_ref": np.full(horizon + 1, speed, dtype=float),
            "a_ref": zeros,
            "df_ref": zeros,
            "x_lin": x_reference,
            "y_lin": zeros,
            "psi_lin": zeros,
            "v_lin": np.full(horizon + 1, speed, dtype=float),
            "a_lin": zeros,
            "df_lin": zeros,
            "mus": [mode_means],
            "sigmas": [mode_covariances],
            "acc_prev": 0.0,
            "df_prev": 0.0,
            "tv_shapes": [target_shapes],
            "heading_cost_weights": np.zeros(horizon, dtype=float),
            "probs": [0.80, 0.15, 0.05],
        }

    def test_fixed_and_adaptive_production_problem_consume_weighted_contract(self):
        from core.scripts.carla.utils.mode_probability_contract import (
            OBJECTIVE_WEIGHTING_CONTRACT_SHA256,
            OBJECTIVE_WEIGHTING_ID,
        )
        from core.scripts.carla.utils.mpc_utils import SMPC_MMPreds

        horizon = 5
        for fixed_risk in (True, False):
            with self.subTest(fixed_risk=fixed_risk):
                controller = SMPC_MMPreds(
                    N=horizon,
                    DT=0.2,
                    N_modes_MAX=3,
                    N_TV_MAX=1,
                    T_BAR_MAX=3,
                    fixed_risk=fixed_risk,
                    fps=20,
                )
                problem_id = 2
                controller.update(
                    problem_id,
                    self._update_payload(horizon),
                )
                result = controller.solve(problem_id)
                self.assertTrue(result["optimal"])
                debug = result["debug"]
                self.assertEqual(debug["objective_weighting"], OBJECTIVE_WEIGHTING_ID)
                self.assertEqual(
                    debug["objective_weighting_contract_sha256"],
                    OBJECTIVE_WEIGHTING_CONTRACT_SHA256,
                )
                np.testing.assert_allclose(
                    debug["joint_mode_probabilities"],
                    [0.80, 0.15, 0.05],
                    rtol=0.0,
                    atol=1.0e-12,
                )
                np.testing.assert_allclose(
                    debug["active_objective_weights"],
                    [0.80, 0.15, 0.05],
                    rtol=0.0,
                    atol=1.0e-12,
                )
                self.assertAlmostEqual(debug["joint_mode_probability_sum"], 1.0)
                self.assertFalse(debug["objective_unweighted_option_available"])


if __name__ == "__main__":
    unittest.main()
