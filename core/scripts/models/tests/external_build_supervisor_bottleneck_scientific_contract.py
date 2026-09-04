
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import csv
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.tools.build_supervisor_bottleneck_scientific_contract import (
    build_contract,
)


class SupervisorBottleneckScientificContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]

    def test_contract_builds_from_canonical_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            complete = build_contract(self.root, output)
            self.assertEqual(complete["status"], "pass")
            self.assertEqual(complete["evidence_blocks"], 5)
            self.assertEqual(complete["claims"], 7)
            self.assertGreaterEqual(complete["terminology_entries"], 20)
            self.assertTrue(complete["population_signatures_unique"])
            self.assertTrue(complete["completion_hashes_unique"])

            registry = json.loads((output / "evidence_blocks.json").read_text())
            ids = [block["block_id"] for block in registry["blocks"]]
            self.assertEqual(len(ids), len(set(ids)))
            signatures = [block["population_signature"] for block in registry["blocks"]]
            self.assertEqual(len(signatures), len(set(signatures)))

    def test_claim_matrix_contains_foundation_and_all_four_axes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_contract(self.root, output)
            with (output / "claim_evidence_boundary.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            claim_ids = {row["claim_id"] for row in rows}
            self.assertTrue(
                {
                    "F0_FOUNDATION",
                    "H1_CAPACITY",
                    "H2_INFORMATION",
                    "H3_ARCHITECTURE",
                    "H4A_SELECTED_MODEL_TRANSFER",
                    "H4B_RISK_FRONTIER",
                    "H4C_SUPERVISOR_AUTHORITY",
                }.issubset(claim_ids)
            )
            self.assertTrue(all(row["prohibited_overclaim"] for row in rows))
            self.assertTrue(all(row["decision_rule"] for row in rows))

    def test_contract_rejects_selective_masking_as_current_verdict(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            build_contract(self.root, output)
            matrix = json.loads((output / "claim_evidence_boundary.json").read_text())
            supervisor = next(
                item for item in matrix["claims"] if item["claim_id"] == "H4C_SUPERVISOR_AUTHORITY"
            )
            self.assertIn("selective_masking_not_supported", supervisor["verdict"])
            self.assertIn("floor saturation", supervisor["boundary"])


if __name__ == "__main__":
    unittest.main()
