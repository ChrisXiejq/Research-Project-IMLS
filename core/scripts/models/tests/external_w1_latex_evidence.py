#!/usr/bin/env python3

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.experimental.build_w1_latex_evidence import build


class W1LatexEvidenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_offline_tables_are_rollout_macro_traceable_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_dir, second_dir = Path(first), Path(second)
            first_receipt = build(self.repo, first_dir, closure_mode="pre-sf4")
            second_receipt = build(self.repo, second_dir, closure_mode="pre-sf4")

            self.assertEqual(first_receipt, second_receipt)
            self.assertEqual(first_receipt["status"], "partial_pre_sf4")
            self.assertEqual(first_receipt["closure_mode"], "pre-sf4")
            self.assertTrue(first_receipt["value_evidence_ready"])
            self.assertFalse(first_receipt["final_release_eligible"])
            self.assertIn("rollout_aggregation.macro_mean", first_receipt["aggregation_contract"])
            self.assertEqual(first_receipt["validated_counts"]["validation_runs"], 15)
            self.assertGreaterEqual(len(first_receipt["source_sha256"]), 30)

            for name, expected_hash in first_receipt["artifacts"].items():
                self.assertEqual(
                    hashlib.sha256((first_dir / name).read_bytes()).hexdigest(),
                    expected_hash,
                )
                self.assertEqual(
                    (first_dir / name).read_bytes(),
                    (second_dir / name).read_bytes(),
                )

            test_tex = (first_dir / "w1_frozen_test.tex").read_text(encoding="utf-8")
            self.assertIn("one common rollout-macro aggregation", test_tex)
            self.assertIn("B0 & -- & control & 2.171 & 1.283 & 2.644", test_tex)
            self.assertIn("B1 & 37 & 1 & 1.857 & 0.100 & 0.121", test_tex)
            self.assertIn("B2-D & 11 & 2 & 1.873 & 0.210 & 0.351", test_tex)
            self.assertNotIn("1.299", test_tex)
            self.assertNotIn("2.685", test_tex)
            self.assertNotIn("0.106", test_tex)

            validation_tex = (first_dir / "w1_validation_runs.tex").read_text(
                encoding="utf-8"
            )
            self.assertIn("NLL, ADE and FDE are uncalibrated rollout-macro", validation_tex)
            self.assertIn("B1 & 11 & 20 & 1,034,208 & 1.861 & 0.110 & 0.135", validation_tex)
            self.assertNotIn("1.861 & 0.115 & 0.142", validation_tex)

    def test_default_final_mode_rejects_partial_m1(self) -> None:
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaisesRegex(ValueError, "M1 evidence package"):
                build(self.repo, Path(output))

    def test_workflow_renderer_semantic_transform_survives_line_wrapping(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is unavailable")
        script = (
            self.repo / "core" / "scripts" / "models"
            / "experimental/render_w1_r3_figures_png.cjs"
        )
        completed = subprocess.run(
            [node, str(script), "--repo-root", str(self.repo), "--self-test"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "pass")
        self.assertTrue(payload["workflow_semantic_transform"])

    def test_w1_audit_freezes_discovery_before_running_mutating_regressions(self) -> None:
        source = (
            self.repo / "core" / "scripts" / "models" / "experimental/audit_w1_manuscript.py"
        ).read_text(encoding="utf-8")
        count_line = "discovered_test_count = discover_regression_test_count(REPO_ROOT)"
        execute_line = "tests = subprocess.run("
        self.assertIn(count_line, source)
        self.assertIn(execute_line, source)
        self.assertLess(source.index(count_line), source.index(execute_line))


if __name__ == "__main__":
    unittest.main()
