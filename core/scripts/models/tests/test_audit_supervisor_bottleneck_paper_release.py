import json
import shutil
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.audit_supervisor_bottleneck_paper_release import audit_release


class SupervisorBottleneckPaperReleaseAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]
        cls.release = cls.root / "docs/paper/generated/supervisor_bottleneck_v1/paper_release"

    def test_current_release_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            receipt = audit_release(self.root, self.release, Path(directory) / "receipt.json")
            self.assertEqual(receipt["status"], "pass")
            self.assertTrue(receipt["checks"]["sf4_40_on_0_off_completion"])
            self.assertTrue(receipt["checks"]["masking_overclaim_absent"])

    def test_stale_table_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "release"
            shutil.copytree(self.release, copied)
            table = copied / "tables/table10_limitations.csv"
            table.write_text(table.read_text() + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale_table"):
                audit_release(self.root, copied, Path(directory) / "receipt.json")


if __name__ == "__main__":
    unittest.main()
