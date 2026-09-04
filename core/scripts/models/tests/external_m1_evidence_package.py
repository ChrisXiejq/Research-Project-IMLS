#!/usr/bin/env python3

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.experimental.build_m1_evidence_package import build


class M1EvidencePackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_m1_resolves_every_locator_and_value_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path, second_path = Path(first), Path(second)
            first_marker = build(self.repo, first_path, closure_mode="pre-sf4")
            second_marker = build(self.repo, second_path, closure_mode="pre-sf4")
            self.assertEqual(first_marker, second_marker)
            self.assertEqual(first_marker["status"], "partial_pre_sf4")
            self.assertEqual(first_marker["value_audit_status"], "pass")
            self.assertEqual(first_marker["closure_mode"], "pre-sf4")
            self.assertEqual(first_marker["supervisor_feedback_closure_status"], "incomplete")
            self.assertFalse(first_marker["final_release_eligible"])
            self.assertEqual(first_marker["invalid_locators"], 0)
            self.assertEqual(first_marker["value_mismatches"], 0)
            self.assertEqual(first_marker["orphan_headline_claims"], 0)
            self.assertEqual(first_marker["legacy_corrected_pooling_violations"], [])
            self.assertEqual(first_marker["aggregation_semantic_violations"], [])
            self.assertEqual(first_marker["headline_aggregation"], "rollout_macro")
            self.assertEqual(first_marker["independent_paired_init_groups"], 5)
            self.assertFalse(first_marker["overlapping_windows_treated_as_independent"])
            self.assertTrue(first_marker["additional_large_scale_carla_required"])
            manifest = json.loads((first_path / "M1_EVIDENCE_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual({row["hypothesis"] for row in manifest["hypotheses"]}, {"H1", "H2", "H3", "H4"})
            self.assertGreaterEqual(manifest["record_count"], 50)
            records = {row["evidence_id"]: row for row in manifest["records"]}
            expected = {
                "H1_B0_TEST_NLL": 2.1707117557525635,
                "H1_B1_TEST_NLL": 1.857094407081604,
                "H1_B1_MINUS_B0_TEST_NLL": -0.3136173486709595,
                "H1_B0_TEST_ADE": 1.2826716899871826,
                "H1_B1_TEST_ADE": 0.09965752065181732,
                "H1_B1_MINUS_B0_TEST_ADE": -1.1830141693353653,
                "H1_B0_TEST_FDE": 2.6443111896514893,
                "H1_B1_TEST_FDE": 0.12089526653289795,
                "H1_B1_MINUS_B0_TEST_FDE": -2.5234159231185913,
            }
            for evidence_id, value in expected.items():
                record = records[evidence_id]
                self.assertAlmostEqual(record["value"], value)
                self.assertTrue(record["aggregation_unit"].startswith("rollout-macro"))
                if record["source"]["kind"] == "file":
                    self.assertIn(
                        "/rollout_aggregation/macro_mean/",
                        record["source"]["locator"]["pointer"],
                    )
            self.assertNotEqual(records["H1_B0_TEST_ADE"]["value"], 1.2987937927246094)
            self.assertNotEqual(records["H1_B1_TEST_ADE"]["value"], 0.10587570071220398)
            for filename, expected_hash in first_marker["artifacts"].items():
                self.assertEqual(
                    hashlib.sha256((first_path / filename).read_bytes()).hexdigest(),
                    expected_hash,
                )
            for filename in (*first_marker["artifacts"], "M1_COMPLETE.json"):
                self.assertEqual((first_path / filename).read_bytes(), (second_path / filename).read_bytes())

    def test_m1_default_final_mode_fails_closed_before_sf4(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            marker = build(self.repo, Path(output))
        self.assertEqual(marker["status"], "fail")
        self.assertEqual(marker["closure_mode"], "final")
        self.assertEqual(marker["value_audit_status"], "pass")
        self.assertNotEqual(marker["supervisor_feedback_closure_status"], "pass")
        self.assertFalse(marker["final_release_eligible"])


if __name__ == "__main__":
    unittest.main()
