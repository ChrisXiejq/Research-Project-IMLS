
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import pathlib
import sys
import unittest

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[4]
UTILS = ROOT / "core/scripts/carla/utils"
sys.path.insert(0, str(UTILS))

from mode_probability_contract import (  # noqa: E402
    OBJECTIVE_WEIGHTING_ID,
    active_objective_weights,
    joint_mode_probabilities,
    normalize_probability_vector,
)


class ModeProbabilityContractTests(unittest.TestCase):
    def test_normalization_preserves_relative_mass(self):
        result = normalize_probability_vector(
            [8.0, 1.5, 0.5], expected_size=3, label="test"
        )
        np.testing.assert_allclose(result, [0.8, 0.15, 0.05], atol=1.0e-12)

    def test_invalid_probability_vectors_fail_closed(self):
        invalid = ([0.5, -0.1, 0.6], [0.0, 0.0, 0.0], [0.5, np.nan, 0.5])
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                normalize_probability_vector(
                    values, expected_size=3, label="invalid"
                )
        with self.assertRaises(ValueError):
            normalize_probability_vector([0.5, 0.5], expected_size=3, label="shape")

    def test_joint_probabilities_match_flat_joint_mode_order(self):
        result = joint_mode_probabilities(
            [[0.8, 0.2], [0.25, 0.75]], n_targets=2, n_modes=2
        )
        np.testing.assert_allclose(result, [0.2, 0.05, 0.6, 0.15])
        self.assertAlmostEqual(float(np.sum(result)), 1.0)

    def test_objective_uses_probabilities_after_branching(self):
        probabilities = [0.8, 0.15, 0.05]
        np.testing.assert_allclose(
            active_objective_weights(probabilities, active_branch_count=3),
            probabilities,
        )
        np.testing.assert_allclose(
            active_objective_weights(probabilities, active_branch_count=1),
            [1.0],
        )
        self.assertEqual(
            OBJECTIVE_WEIGHTING_ID,
            "multipath_joint_probability_expected_cost_v2",
        )

    def test_partial_branch_sets_are_rejected(self):
        with self.assertRaises(ValueError):
            active_objective_weights([0.5, 0.3, 0.2], active_branch_count=2)


if __name__ == "__main__":
    unittest.main()
