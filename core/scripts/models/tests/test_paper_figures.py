#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.build_paper_figures import build


class PaperFiguresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_figures_are_traceable_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_dir, second_dir = Path(first), Path(second)
            first_payload = build(self.repo, first_dir)
            second_payload = build(self.repo, second_dir)
            self.assertEqual(first_payload, second_payload)
            self.assertEqual(first_payload["status"], "pass")
            self.assertEqual(first_payload["figure_count"], 8)
            for filename, record in first_payload["figures"].items():
                self.assertEqual((first_dir / filename).read_bytes(), (second_dir / filename).read_bytes())
                self.assertTrue(record["evidence_ids"])
            completion = json.loads((first_dir / "PAPER_FIGURES_COMPLETE.json").read_text())
            self.assertEqual(completion["status"], "pass")


if __name__ == "__main__":
    unittest.main()
