
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import csv
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.tools.build_supervisor_bottleneck_paper_release import build_release


class SupervisorBottleneckPaperReleaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]

    def test_release_reconciles_headline_values(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = build_release(self.root, output)
            self.assertEqual(result["status"], "pass")
            self.assertTrue(result["checks"]["sf4_rollouts_reconcile"])
            with (output / "tables/table08_sf4_authority_cells.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            off = [row for row in rows if row["supervisor_authority"] == "off"]
            on = [row for row in rows if row["supervisor_authority"] == "on"]
            self.assertEqual(sum(int(row["completion_successes"]) for row in off), 0)
            self.assertEqual(sum(int(row["completion_successes"]) for row in on), 40)

    def test_release_keeps_populations_separate_and_sources_located(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            result = build_release(self.root, output)
            populations = result["population_registry"]
            self.assertEqual(len(populations), 5)
            self.assertTrue(all(row["pooling"] == "forbidden_across_evidence_blocks" for row in populations))
            with (output / "tables/scalar_provenance_index.csv").open(newline="") as handle:
                provenance = list(csv.DictReader(handle))
            self.assertGreater(len(provenance), 20)
            self.assertTrue(all(row["canonical_source_locator"] for row in provenance))


if __name__ == "__main__":
    unittest.main()
