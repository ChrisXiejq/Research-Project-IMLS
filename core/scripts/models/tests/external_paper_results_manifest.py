#!/usr/bin/env python3

import csv
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
            first_completion = build(self.repo, first_dir, closure_mode="pre-sf4")
            second_completion = build(self.repo, second_dir, closure_mode="pre-sf4")

            self.assertEqual(first_completion["status"], "partial_pre_sf4")
            self.assertFalse(first_completion["final_release_eligible"])
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

            with (first_dir / "table03_frozen_test_and_b0_control.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                test_rows = list(csv.DictReader(handle))
            self.assertEqual(len(test_rows), 6)
            by_variant = {row["variant"]: row for row in test_rows}
            self.assertEqual(
                set(by_variant),
                {"B0 pretrained control", "B1", "B2-D", "T2", "T1", "B2-M"},
            )
            self.assertTrue(all(row["metric_aggregation"] == "rollout_macro" for row in test_rows))
            self.assertAlmostEqual(
                float(by_variant["B0 pretrained control"]["test_rollout_macro_top1_ade_m"]),
                1.2826716899871826,
            )
            self.assertAlmostEqual(
                float(by_variant["B1"]["test_rollout_macro_top1_ade_m"]),
                0.09965752065181732,
            )
            self.assertAlmostEqual(
                float(by_variant["T2"]["test_rollout_macro_top1_fde_m"]),
                0.3742082715034485,
            )
            self.assertNotEqual(
                float(by_variant["B0 pretrained control"]["test_rollout_macro_top1_ade_m"]),
                1.2987937927246094,
            )

            for result_id in (
                "R_TEST_B0_MACRO_NLL",
                "R_TEST_B0_TOP1_ADE_M",
                "R_TEST_B0_TOP1_FDE_M",
                "R_TEST_B1_MINUS_B0_ADE",
                "R_TEST_B1_MINUS_B0_FDE",
            ):
                self.assertIn(result_id, manifest["results"])
                self.assertTrue(
                    manifest["results"][result_id]["aggregation_unit"].startswith(
                        "rollout-macro"
                    )
                )
            self.assertAlmostEqual(
                manifest["results"]["R_TEST_B1_MINUS_B0_ADE"]["value"],
                -1.1830141693353653,
            )
            self.assertIn(
                "aggregation_level=rollout_macro",
                manifest["results"]["R_TEST_B1_MINUS_B0_ADE"]["source_locator"],
            )

            for name, expected_hash in first_completion["artifacts"].items():
                self.assertEqual(
                    hashlib.sha256((first_dir / name).read_bytes()).hexdigest(),
                    expected_hash,
                )

    def test_default_final_mode_rejects_partial_chain(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaisesRegex(ValueError, "M1/W1 stage-aware"):
                build(self.repo, Path(output))


if __name__ == "__main__":
    unittest.main()
