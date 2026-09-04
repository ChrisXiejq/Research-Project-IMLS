
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[4]
MPC = ROOT / "core/scripts/carla/utils/mpc_utils.py"
AGENT = ROOT / "core/scripts/carla/policies/smpc_agent.py"
SCENARIO = ROOT / "core/scripts/carla/scenarios/run_intersection_scenario.py"


class ProbabilityWeightedSMPCSourceContractTests(unittest.TestCase):
    def test_active_branch_cost_is_probability_weighted(self):
        source = MPC.read_text(encoding="utf-8")
        main = source.split("class SMPC_MMPreds():", 1)[1].split(
            "class SMPC_MMPreds_OBCA():", 1
        )[0]
        self.assertIn("branch_cost = (", main)
        self.assertIn("active_branch_costs.append(branch_cost)", main)
        self.assertIn("_probability_weighted_active_branch_cost(", main)
        self.assertIn("self.probs[i]", main)
        self.assertIn('"objective_unweighted_option_available": False', main)
        self.assertIn('"objective_weighting_contract_sha256"', main)
        self.assertNotIn("cost += branch_cost", main)

    def test_unweighted_runtime_ids_are_rejected(self):
        mpc = MPC.read_text(encoding="utf-8")
        agent = AGENT.read_text(encoding="utf-8")
        self.assertIn("DEPRECATED_UNWEIGHTED_CONTROL_IMPLEMENTATIONS", mpc)
        self.assertIn("Unweighted SMPC objective implementations were removed", agent)
        self.assertIn(
            "CONTROL_IMPLEMENTATION_PROBABILITY_WEIGHTED_V2", agent
        )
        self.assertIn("open_loop/OBCA controllers are not admissible", agent)

    def test_probability_weighted_v2_is_the_scenario_default(self):
        scenario = SCENARIO.read_text(encoding="utf-8")
        self.assertIn(
            'control_implementation_version : str = "corrected_joint_modes_shared_amin_probability_weighted_v2"',
            scenario,
        )

    def test_agent_requires_and_logs_mode_probabilities(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn("joint_mode_probabilities(", source)
        self.assertIn(
            "Probability-weighted SMPC requires MultiPath mode probabilities",
            source,
        )
        self.assertIn('"objective_weighting": OBJECTIVE_WEIGHTING_ID', source)

    def test_solver_update_fails_closed_when_probabilities_are_missing(self):
        source = MPC.read_text(encoding="utf-8")
        self.assertIn('if "probs" not in update_dict:', source)
        self.assertIn("Probability-weighted SMPC update requires explicit", source)
        self.assertNotIn('update_dict.get(\n            "probs"', source)


if __name__ == "__main__":
    unittest.main()
