import tempfile
import unittest
from pathlib import Path

from core.scripts.models.build_supervisor_bottleneck_evidence_gap_gate import build_gate


class SupervisorBottleneckEvidenceGapGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]

    def test_existing_evidence_closes_collection_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_gate(self.root, Path(directory) / "gate.json")
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["decision"], "existing_evidence_sufficient")
            self.assertTrue(result["checks"]["all_headline_claims_disposed"])
            self.assertTrue(result["checks"]["masking_overclaim_refused"])
            self.assertIn("closed", result["collection_authorisation"])
            self.assertEqual(len(result["decision_sha256"]), 64)

    def test_every_headline_disposition_forbids_new_collection(self):
        with tempfile.TemporaryDirectory() as directory:
            result = build_gate(self.root, Path(directory) / "gate.json")
            headline = [row for row in result["headline_dispositions"] if row["claim_id"].startswith("H")]
            self.assertGreaterEqual(len(headline), 6)
            self.assertTrue(all(row["new_collection_needed"] is False for row in headline))


if __name__ == "__main__":
    unittest.main()
