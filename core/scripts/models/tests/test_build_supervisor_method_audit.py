import csv
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.build_supervisor_method_audit import build, materialize


REPO = Path(__file__).resolve().parents[4]


class SupervisorMethodAuditTest(unittest.TestCase):
    def test_contract_is_complete_and_corrects_known_mismatches(self):
        payload = build(REPO)
        self.assertEqual(payload["status"], "pass")
        self.assertEqual(len(payload["formula_to_code"]), 13)
        self.assertEqual(len(payload["supervisor_channels"]), 7)
        self.assertIn("sum_j pi_j J_j", payload["mandatory_corrections"]["objective"])
        self.assertTrue(payload["checks"]["objective_probability_weighting_explicit"])
        self.assertIn("20 Hz", payload["mandatory_corrections"]["timing"])
        covariance = next(row for row in payload["formula_to_code"] if row["id"] == "F02_per_time_covariance")
        self.assertIn("does not predict covariance between different future instants", covariance["plain_language"])

    def test_materialized_csv_and_hash_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = materialize(REPO, Path(tmp))
            self.assertEqual(marker["status"], "pass")
            self.assertEqual(marker["supervisor_channel_count"], 7)
            with (Path(tmp) / "seven_channel_contract.csv").open(encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 7)
            self.assertEqual(len({row["channel"] for row in rows}), 7)
            persisted = json.loads((Path(tmp) / "formula_to_code.json").read_text())
            self.assertTrue(all(persisted["checks"].values()))


if __name__ == "__main__":
    unittest.main()
