
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import csv
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.analysis.analyze_shadow_command_transmission import analyze


FIELDS = [
    "ego_init_id", "factual_rollout_id", "state_key", "predictor", "risk_policy",
    "supervisor_mapping", "nominal_accel_mps2", "post_accel_mps2",
    "supervisor_any_requested", "shadow_actuated", "solver_accepted", "fallback_used",
    "factual_branch", "factual_command_parity",
]


class ShadowCommandTransmissionTest(unittest.TestCase):
    def _write(self, path: Path, *, actuated=False, degenerate=False):
        rows = []
        for init_id in (116, 117, 118):
            for state in ("0", "1"):
                for predictor in ("B1", "P_star"):
                    for risk in ("fixed_medium", "adaptive"):
                        for mapping in ("monitor_only", "enabled"):
                            pred = 0.0 if predictor == "B1" else (0.01 if degenerate else 1.0)
                            risk_delta = 0.0 if risk == "fixed_medium" else (0.01 if degenerate else 0.5)
                            monitor = pred + risk_delta
                            post = monitor if mapping == "monitor_only" else 0.2 * monitor
                            rows.append({
                                "ego_init_id": init_id,
                                "factual_rollout_id": f"r{init_id}",
                                "state_key": state,
                                "predictor": predictor,
                                "risk_policy": risk,
                                "supervisor_mapping": mapping,
                                "nominal_accel_mps2": monitor,
                                "post_accel_mps2": post,
                                "supervisor_any_requested": True,
                                "shadow_actuated": actuated and len(rows) == 0,
                                "solver_accepted": True,
                                "fallback_used": False,
                                "factual_branch": (
                                    predictor == "B1"
                                    and risk == "fixed_medium"
                                    and mapping == "enabled"
                                ),
                                "factual_command_parity": True,
                            })
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def test_identifies_command_level_attenuation(self):
        with tempfile.TemporaryDirectory() as directory:
            input_csv = Path(directory) / "shadow.csv"
            self._write(input_csv)
            result = analyze(input_csv, Path(directory) / "out.json", resamples=1000)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["integrity"]["shadow_actuation_count"], 0)
            all_cells = [row for row in result["aggregates"] if row["stratum"] == "all"]
            self.assertTrue(all(row["verdict"] == "command_level_masking_identified" for row in all_cells))
            self.assertTrue(all(abs(row["retention_ratio"] - 0.2) < 1e-12 for row in all_cells))

    def test_degenerate_upstream_contrast_refuses_masking(self):
        with tempfile.TemporaryDirectory() as directory:
            input_csv = Path(directory) / "shadow.csv"
            self._write(input_csv, degenerate=True)
            result = analyze(input_csv, Path(directory) / "out.json", resamples=200)
            self.assertTrue(all(
                row["verdict"] == "controller_insensitivity_supervisor_masking_not_testable"
                for row in result["aggregates"]
            ))

    def test_shadow_actuation_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            input_csv = Path(directory) / "shadow.csv"
            self._write(input_csv, actuated=True)
            with self.assertRaisesRegex(ValueError, "Shadow actuation detected"):
                analyze(input_csv, Path(directory) / "out.json", resamples=100)


if __name__ == "__main__":
    unittest.main()
