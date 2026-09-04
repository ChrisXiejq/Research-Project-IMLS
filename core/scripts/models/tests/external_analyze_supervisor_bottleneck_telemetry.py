
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

from core.scripts.models.analysis.analyze_supervisor_bottleneck_telemetry import (
    build_audit,
    classify_intervention_record,
)


def record(*, requested=0.0, applied=0.0, bypass=0.0, actual=0.0):
    return {
        "supervisor_any_channel_requested_fraction": requested,
        "supervisor_authority_applied_fraction": applied,
        "rule_smpc_bypass_applied_fraction": bypass,
        "actual_minus_nominal_accel_abs_mean_mps2": actual,
    }


class InterventionClassificationTest(unittest.TestCase):
    def test_apply(self):
        self.assertEqual(classify_intervention_record(record(requested=0.5, applied=0.2, actual=0.7)), "apply")

    def test_monitor_only(self):
        self.assertEqual(classify_intervention_record(record(requested=0.5)), "monitor_only")

    def test_bypass_has_explicit_precedence(self):
        self.assertEqual(classify_intervention_record(record(requested=0.5, applied=0.2, bypass=0.1, actual=0.7)), "bypass")

    def test_missing_is_not_zero(self):
        row = record()
        row.pop("actual_minus_nominal_accel_abs_mean_mps2")
        self.assertEqual(classify_intervention_record(row), "missing")


class SupervisorBottleneckTelemetryIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]

    def test_canonical_audit_reconciles_and_refuses_masking(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            inspection = temporary / "server.json"
            inspection.write_text(json.dumps({"schema_version": "server_evidence_inspection_v1", "status": "pass"}))
            output = temporary / "out"
            complete = build_audit(self.root, output, inspection)
            self.assertEqual(complete["status"], "pass")
            self.assertTrue(complete["checks"]["solver_reconciled"])
            solver = json.loads((output / "solver_path_reconciliation.json").read_text())
            self.assertEqual(solver["totals"]["factual_solver_attempts"], 18552)
            self.assertEqual(solver["totals"]["fallback_or_nonaccepted_attempts"], 730)
            attenuation = json.loads((output / "attenuation_claim_audit.json").read_text())
            self.assertFalse(attenuation["selective_masking_identified"])
            self.assertEqual(attenuation["floor_saturation"]["authority_off_completion"], 0)

    def test_phase_missingness_is_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            inspection = temporary / "server.json"
            inspection.write_text(json.dumps({"schema_version": "server_evidence_inspection_v1", "status": "pass"}))
            output = temporary / "out"
            build_audit(self.root, output, inspection)
            phase = (output / "phase_event_availability.csv").read_text()
            self.assertIn("descriptive_only_missing_event_clock", phase)
            self.assertNotIn(",True", phase)
            contrasts = json.loads((output / "phase_contrast_availability.json").read_text())
            release = contrasts["metrics"]["actual_path_release_to_sustained_resume_s"]
            self.assertEqual(release["authority_effect_adaptive"]["defined_init_clusters"], 3)
            self.assertEqual(
                release["authority_effect_adaptive"]["status"],
                "descriptive_only_missing_event_clock",
            )


if __name__ == "__main__":
    unittest.main()
