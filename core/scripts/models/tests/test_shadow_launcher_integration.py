
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
RUN_ALL = ROOT / "core/scripts/carla/run_all_scenarios.py"
SCENARIO = ROOT / "core/scripts/carla/scenarios/run_intersection_scenario.py"


class ShadowLauncherSourceContractTest(unittest.TestCase):
    def test_default_off_and_explicit_cli_contract(self):
        run_all = RUN_ALL.read_text(encoding="utf-8")
        scenario = SCENARIO.read_text(encoding="utf-8")
        self.assertIn("same_state_shadow_enabled : bool = False", scenario)
        self.assertIn('"--enable_same_state_shadow_replay"', run_all)
        self.assertIn('getattr(args, "enable_same_state_shadow_replay", False)', run_all)

    def test_seven_non_factual_agents_and_non_actuating_bank_are_wired(self):
        source = SCENARIO.read_text(encoding="utf-8")
        self.assertIn("if key == factual:", source)
        self.assertIn("SMPCAgentShadowBank(", source)
        self.assertIn('"shadow_branch_count": len(agents)', source)
        self.assertIn('"shadow_actuation_allowed": False', source)
        self.assertIn("configure_same_state_shadow_only(", source)

    def test_frozen_contract_binds_all_artifact_classes(self):
        source = SCENARIO.read_text(encoding="utf-8")
        for token in (
            '"protocol": {"path": protocol, "sha256"',
            '"assets": {',
            '"code": [',
            '"same_state_shadow_run_contract.json"',
        ):
            self.assertIn(token, source)

    def test_event_anchor_requires_model_gmm_replay_readiness(self):
        source = SCENARIO.read_text(encoding="utf-8")
        self.assertIn('replay_input.get("mode") == "model_gmm"', source)
        self.assertIn("valid_prediction = valid_prediction and replay_ready", source)


if __name__ == "__main__":
    unittest.main()
