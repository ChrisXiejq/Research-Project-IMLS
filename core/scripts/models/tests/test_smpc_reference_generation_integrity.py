"""Regression gates for dynamically feasible SMPC reference integrity."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[4]
AGENT = ROOT / "core" / "scripts" / "carla" / "policies" / "smpc_agent.py"


class ReferenceGenerationIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = AGENT.read_text(encoding="utf-8")

    def test_supervisor_on_restores_source_reference_solve_budget(self):
        self.assertIn(
            "5.0 if self.supervisor_free_smpc_enabled else 2.0",
            self.source,
        )
        self.assertNotIn(
            "5.0 if self.supervisor_free_smpc_enabled else 0.2",
            self.source,
        )

    def test_invalid_reference_is_rejected_in_every_authority_mode(self):
        self.assertIn(
            "result_valid = bool(result.get(\"optimal\", False) and arrays_finite)",
            self.source,
        )
        self.assertIn("if not result_valid:", self.source)
        self.assertNotIn(
            "if self.supervisor_free_smpc_enabled and (\n"
            "            not result.get(\"optimal\", False) or not arrays_finite",
            self.source,
        )

    def test_closed_loop_failure_retains_last_valid_reference(self):
        for channel in ("states", "inputs", "route_s"):
            self.assertIn(
                f"self._last_valid_feas_ref_{channel}.copy()",
                self.source,
            )
        self.assertIn(
            "reference_generation_failed_retained_last_valid",
            self.source,
        )
        self.assertIn(
            'self._reference_generation_status["last_fallback_used"] = True',
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
