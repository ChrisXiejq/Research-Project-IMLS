#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.build_m1_evidence_package import build


class M1EvidencePackageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_m1_resolves_every_locator_and_value_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path, second_path = Path(first), Path(second)
            first_marker = build(self.repo, first_path)
            second_marker = build(self.repo, second_path)
            self.assertEqual(first_marker, second_marker)
            self.assertEqual(first_marker["status"], "pass")
            self.assertEqual(first_marker["invalid_locators"], 0)
            self.assertEqual(first_marker["value_mismatches"], 0)
            self.assertEqual(first_marker["orphan_headline_claims"], 0)
            self.assertEqual(first_marker["legacy_corrected_pooling_violations"], [])
            self.assertFalse(first_marker["additional_large_scale_carla_required"])
            manifest = json.loads((first_path / "M1_EVIDENCE_MANIFEST.json").read_text(encoding="utf-8"))
            self.assertEqual({row["hypothesis"] for row in manifest["hypotheses"]}, {"H1", "H2", "H3", "H4"})
            self.assertGreaterEqual(manifest["record_count"], 50)
            for filename in (*first_marker["artifacts"], "M1_COMPLETE.json"):
                self.assertEqual((first_path / filename).read_bytes(), (second_path / filename).read_bytes())


if __name__ == "__main__":
    unittest.main()
