from __future__ import annotations

import unittest

from write_pre_freeze_training_curve_audit_v4 import enforce_required_pass


class FinalConvergenceGateTest(unittest.TestCase):
    def test_required_pass_accepts_pass(self) -> None:
        enforce_required_pass(
            {"status": "pass", "unresolved_boundary_underfit_runs": []}, True
        )

    def test_required_pass_rejects_unresolved_training(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "convergence audit failed"):
            enforce_required_pass(
                {
                    "status": "fail",
                    "unresolved_boundary_underfit_runs": ["run-a"],
                },
                True,
            )

    def test_diagnostic_mode_preserves_failed_trigger_audit(self) -> None:
        enforce_required_pass(
            {"status": "fail", "unresolved_boundary_underfit_runs": ["run-a"]},
            False,
        )


if __name__ == "__main__":
    unittest.main()
