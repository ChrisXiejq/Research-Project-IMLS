#!/usr/bin/env python3

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.build_paper_results_manifest import build


class PaperResultsManifestTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_build_is_complete_traceable_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_dir = Path(first)
            second_dir = Path(second)
            first_completion = build(self.repo, first_dir)
            second_completion = build(self.repo, second_dir)

            self.assertEqual(first_completion["status"], "pass")
            self.assertEqual(first_completion["table_count"], 8)
            self.assertGreaterEqual(first_completion["result_count"], 100)
            self.assertEqual(first_completion, second_completion)

            first_manifest = (first_dir / "paper_results_manifest.json").read_bytes()
            second_manifest = (second_dir / "paper_results_manifest.json").read_bytes()
            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual(
                first_completion["manifest_sha256"], hashlib.sha256(first_manifest).hexdigest()
            )

            manifest = json.loads(first_manifest)
            self.assertEqual(manifest["result_count"], len(manifest["results"]))
            self.assertTrue(
                manifest["results"]["R_SENS_SELECTED_ARCHITECTURE_STABLE"]["value"]
            )
            for record in manifest["results"].values():
                source = self.repo / record["source_file"]
                self.assertTrue(source.is_file())
                self.assertEqual(record["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

            for table in manifest["table_files"]:
                self.assertEqual(
                    (first_dir / table).read_bytes(), (second_dir / table).read_bytes()
                )


if __name__ == "__main__":
    unittest.main()
