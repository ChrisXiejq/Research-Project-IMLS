#!/usr/bin/env python3

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import copy
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.tools.audit_supervisor_finetune_feedback import (
    build,
    exact_sign_flip_paired_p,
    frozen_test_population_contract,
    scan_old_percentage_accuracy,
)


class SupervisorFinetuneFeedbackAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]

    def test_current_frozen_evidence_builds_complete_deterministic_audit(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_dir = Path(first)
            second_dir = Path(second)
            first_completion = build(self.repo, first_dir)
            second_completion = build(self.repo, second_dir)

            self.assertEqual(first_completion, second_completion)
            self.assertEqual(first_completion["status"], "pass")
            self.assertEqual(first_completion["failure_count"], 0)
            self.assertEqual(first_completion["old_percentage_accuracy_hit_count"], 0)
            self.assertEqual(first_completion["independent_paired_init_groups"], 5)
            self.assertFalse(first_completion["overlapping_windows_treated_as_independent"])
            self.assertEqual(
                first_completion["frozen_test_population_contract_status"], "pass"
            )

            manifest_path = first_dir / first_completion["manifest"]
            self.assertEqual(
                hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                first_completion["manifest_sha256"],
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["artifacts"], first_completion["artifacts"])
            for name, expected_hash in first_completion["artifacts"].items():
                self.assertEqual(
                    hashlib.sha256((first_dir / name).read_bytes()).hexdigest(),
                    expected_hash,
                )

            rollout_tex = (
                first_dir / "finetune_b0_b1_rollout_macro.tex"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "B0 & 315 & 20 & 5 & 2.171 & 1.283 & 2.644 \\\\",
                rollout_tex,
            )
            self.assertIn(
                "B1 & 315 & 20 & 5 & 1.857 & 0.100 & 0.121 \\\\",
                rollout_tex,
            )
            self.assertIn(
                "B1$-$B0 & 315 & 20 & 5 & -0.314 & -1.183 & -2.523 \\\\",
                rollout_tex,
            )
            self.assertNotIn("1.299", rollout_tex)
            self.assertNotIn("2.685", rollout_tex)

            paired_tex = (
                first_dir / "finetune_b0_b1_paired_init_effects.tex"
            ).read_text(encoding="utf-8")
            self.assertIn("All lower?", paired_tex)
            self.assertIn("each of 5/5", (first_dir / "SUPERVISOR_COMMENT_3_AUDIT.md").read_text())
            for init_id in range(46, 51):
                self.assertIn(f"{init_id} & ", paired_tex)
            self.assertIn("sign-flip sensitivity values", paired_tex)
            self.assertIn("not treatment-randomisation inference", paired_tex)
            self.assertIn("Init-macro mean & -- & -0.316 & -1.189 & -2.544 & 5/5", paired_tex)

            with (first_dir / "frozen_test_same_aggregation.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                summary = list(csv.DictReader(handle))
            self.assertEqual(len(summary), 4)
            self.assertEqual(
                {row["aggregation_level"] for row in summary},
                {"rollout_macro", "held_out_init_group_macro"},
            )

            with (first_dir / "frozen_test_paired_by_init.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                pairs = list(csv.DictReader(handle))
            self.assertEqual([int(row["ego_init_id"]) for row in pairs], list(range(46, 51)))
            self.assertTrue(
                all(int(row["B1_better_top1_ADE_m"]) == 1 for row in pairs)
            )
            self.assertTrue(
                all(int(row["B1_better_top1_FDE_m"]) == 1 for row in pairs)
            )

            with (first_dir / "physical_baselines_same_aggregation.csv").open(
                "r", encoding="utf-8", newline=""
            ) as handle:
                physical = list(csv.DictReader(handle))
            self.assertEqual({row["baseline"] for row in physical}, {"CA", "CV", "train_mean"})
            self.assertTrue(
                all(row["aggregation_level"] == "held_out_init_group_macro" for row in physical)
            )
            self.assertTrue(all(row["B1_ADE_better_init_count"] == "5" for row in physical))
            self.assertTrue(all(row["B1_FDE_better_init_count"] == "5" for row in physical))
            self.assertTrue(all(row["nll_comparison"].startswith("not_reported") for row in physical))

            report = json.loads((first_dir / "finetune_audit.json").read_text())
            self.assertEqual(report["status"], "pass")
            self.assertFalse(
                report["metric_policy"]["overlapping_windows_are_independent"]
            )
            self.assertEqual(
                report["response_active_tail"]["full_horizon_windows"], 15
            )
            contract_path = first_dir / "frozen_test_population_contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            self.assertEqual(contract["status"], "pass")
            self.assertTrue(all(contract["checks"].values()))
            self.assertEqual(
                hashlib.sha256(contract_path.read_bytes()).hexdigest(),
                first_completion["frozen_test_population_contract_sha256"],
            )
            scan = json.loads(
                (first_dir / "percentage_accuracy_scan.json").read_text(encoding="utf-8")
            )
            self.assertTrue(
                all(not root.startswith("/") for root in scan["scanned_roots"])
            )
            self.assertIn("docs/dissertation/latex", scan["scanned_roots"])

    def test_old_percentage_accuracy_scan_detects_superseded_claim(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bad.md").write_text(
                "Fine-tuning accuracy improved from 0.98% to 100%.\n",
                encoding="utf-8",
            )
            result = scan_old_percentage_accuracy([root])
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["hit_count"], 1)

    def test_old_percentage_accuracy_scan_allows_only_explicit_retraction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "withdrawn.md").write_text(
                "An earlier report described a rise from 0.98% to 100%. "
                "We withdraw that number: it is not evidence for trajectory quality.\n",
                encoding="utf-8",
            )
            result = scan_old_percentage_accuracy([root])
            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["hit_count"], 0)

            (root / "misleading.md").write_text(
                "The old metric was superseded, but accuracy improved from 0.98% "
                "to 100% and proves the model is better.\n",
                encoding="utf-8",
            )
            result = scan_old_percentage_accuracy([root])
            self.assertEqual(result["status"], "fail")
            self.assertEqual(result["hit_count"], 1)

    def test_exact_five_pair_resolution_is_reported_honestly(self) -> None:
        self.assertEqual(exact_sign_flip_paired_p([-1, -2, -3, -4, -5]), 0.0625)

    def test_population_contract_rejects_equal_counts_with_mismatched_identity(self) -> None:
        b1 = json.loads(
            (
                self.repo
                / "docs/paper/generated/day8/final_test/B1/seed_37/test_all.json"
            ).read_text(encoding="utf-8")
        )
        b0 = json.loads(
            (
                self.repo
                / "docs/paper/generated/day10/gaps/b0_offline/b0_test_all.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(frozen_test_population_contract(b0, b1)["status"], "pass")

        mutations = {
            "jsonl_hash": lambda value: value["jsonl"].__setitem__("sha256", "0" * 64),
            "anchors_hash": lambda value: value["anchors_artifact"].__setitem__(
                "sha256", "1" * 64
            ),
            "horizon": lambda value: value.__setitem__("horizon", 9),
            "test_calibration_leakage": lambda value: value.__setitem__(
                "calibration_fit_uses_test", True
            ),
            "per_init_count": lambda value: value["uncalibrated"][
                "init_group_aggregation"
            ]["per_init_group"]["ego_init_46"].__setitem__("samples", 65),
            "per_rollout_count": lambda value: next(
                iter(value["uncalibrated"]["rollout_aggregation"]["per_rollout"].values())
            ).__setitem__("samples", 14),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                candidate = copy.deepcopy(b0)
                mutate(candidate)
                contract = frozen_test_population_contract(candidate, b1)
                self.assertEqual(contract["status"], "fail")
                self.assertFalse(all(contract["checks"].values()))


if __name__ == "__main__":
    unittest.main()
