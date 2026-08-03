#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.audit_final_thesis_evidence import build


class FinalThesisEvidenceAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_final_evidence_gates_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "audit.json"
            result = build(self.repo, output)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["check_count"], 14)
            self.assertEqual(result["failure_count"], 0)
            self.assertEqual(result["warning_count"], 8)
            self.assertFalse(result["new_formal_experiment_required"])
            self.assertTrue(all(item["status"] == "pass" for item in result["checks"]))
            self.assertEqual(json.loads(output.read_text()), result)


if __name__ == "__main__":
    unittest.main()
