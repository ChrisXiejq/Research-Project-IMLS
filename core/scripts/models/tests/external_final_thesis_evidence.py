#!/usr/bin/env python3

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

from core.scripts.models.tools.audit_final_thesis_evidence import build


class FinalThesisEvidenceAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_final_evidence_gates_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            result = build(self.repo, output, closure_mode="pre-sf4")
            self.assertEqual(result["status"], "partial_pre_sf4")
            self.assertEqual(result["check_count"], 14)
            self.assertEqual(result["failure_count"], 0)
            self.assertEqual(result["warning_count"], 8)
            self.assertTrue(result["new_formal_experiment_required"])
            self.assertTrue(all(item["status"] == "pass" for item in result["checks"]))
            self.assertEqual(json.loads(output.read_text()), result)

            final = build(self.repo, Path(directory) / "final.json")
            self.assertEqual(final["status"], "fail")
            self.assertFalse(final["final_release_eligible"])


if __name__ == "__main__":
    unittest.main()
