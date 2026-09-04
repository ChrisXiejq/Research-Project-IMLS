
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.experimental.summarize_v3_server_command_transmission import summarize


class V3ServerCommandTransmissionTest(unittest.TestCase):
    def _record(self, risk, nominal, actual, requested=False):
        return {
            "risk": {"applied_tight": risk},
            "applied": {
                "is_opt": True,
                "post_solver_action_filter": {
                    "nominal_solver_command": {"a_des": nominal},
                    "actual_command": {"a_des": actual},
                    "intervention_requested": requested,
                    "intervention_applied": requested,
                },
            },
            "supervisor_behavioural_authority": {
                "observed_first_stage_activity": {"any_requested": requested}
            },
        }

    def test_rollout_macro_pairing_and_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "closed_loop"
            for predictor in ("B1", "P_star"):
                for risk in ("adaptive", "fixed_medium"):
                    for target in ("assertive_constant_speed", "defensive_reactive"):
                        cell = root / f"{predictor}__{risk}__{target}"
                        for init_id in range(81, 91):
                            rollout = cell / f"scenario_uk_give_way_ego_init_{init_id}"
                            rollout.mkdir(parents=True)
                            base = 1.0 if risk == "adaptive" else 2.0
                            records = [
                                self._record(base, 0.1, 0.3, True),
                                self._record(base, 0.2, 0.2, False),
                            ]
                            (rollout / "smpc_debug_steps.jsonl").write_text(
                                "".join(json.dumps(record) + "\n" for record in records)
                            )
            output = Path(directory) / "out"
            result = summarize(root, output)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(len(result["rollout_summaries"]), 80)
            self.assertEqual(len(result["cell_summaries"]), 8)
            self.assertEqual(len(result["paired_risk_contrasts"]), 4)
            self.assertTrue(all(row["mean_tightening_effect"] == -1.0 for row in result["paired_risk_contrasts"]))
            self.assertEqual(len(result["source_inventory"]), 80)
            self.assertFalse(result["same_state_alternative_commands_present"])
            self.assertTrue((output / "v3_risk_command_transmission.json").is_file())

    def test_missing_rollout_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "closed_loop"
            root.mkdir()
            with self.assertRaisesRegex(ValueError, "Expected exactly 80"):
                summarize(root, Path(directory) / "out")


if __name__ == "__main__":
    unittest.main()
