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

from core.scripts.models.tools.build_paper_figures import build
from core.scripts.models.tools.build_paper_results_manifest import build as build_results


class PaperFiguresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_figures_are_traceable_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first_tables, \
                tempfile.TemporaryDirectory() as second_tables, \
                tempfile.TemporaryDirectory() as first, \
                tempfile.TemporaryDirectory() as second:
            first_tables_dir, second_tables_dir = Path(first_tables), Path(second_tables)
            first_dir, second_dir = Path(first), Path(second)
            build_results(self.repo, first_tables_dir, closure_mode="pre-sf4")
            build_results(self.repo, second_tables_dir, closure_mode="pre-sf4")
            first_payload = build(
                self.repo, first_dir, first_tables_dir, closure_mode="pre-sf4"
            )
            second_payload = build(
                self.repo, second_dir, second_tables_dir, closure_mode="pre-sf4"
            )
            self.assertEqual(first_payload, second_payload)
            self.assertEqual(first_payload["status"], "partial_pre_sf4")
            self.assertFalse(first_payload["final_release_eligible"])
            self.assertEqual(first_payload["figure_count"], 8)
            for filename, record in first_payload["figures"].items():
                self.assertEqual((first_dir / filename).read_bytes(), (second_dir / filename).read_bytes())
                self.assertTrue(record["evidence_ids"])
            completion = json.loads((first_dir / "PAPER_FIGURES_COMPLETE.json").read_text())
            self.assertEqual(completion["status"], "partial_pre_sf4")

            figure03 = (first_dir / "figure03_offline_model_comparison.svg").read_text(
                encoding="utf-8"
            )
            self.assertIn("Frozen-test rollout-macro ADE", figure03)
            self.assertIn("1.28/2.64", figure03)
            self.assertIn("0.10/0.12", figure03)
            self.assertNotIn("1.30/2.68", figure03)
            evidence = first_payload["figures"][
                "figure03_offline_model_comparison.svg"
            ]["evidence_ids"]
            self.assertEqual(len(evidence), 27)
            self.assertIn("R_TEST_B0_TOP1_ADE_M", evidence)
            self.assertIn("R_TEST_B2_D_TOP1_FDE_M", evidence)
            self.assertIn("R_VAL_T2_S23_MACRO_NLL", evidence)

    def test_default_final_mode_rejects_partial_tables(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaisesRegex(ValueError, "Paper table/manifest"):
                build(self.repo, Path(output))


if __name__ == "__main__":
    unittest.main()
