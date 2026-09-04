from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import importlib.util
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = REPO_ROOT / "core/scripts/models/tools/generate_integrated_thesis_story.py"
SPEC = importlib.util.spec_from_file_location("generate_integrated_thesis_story", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IntegratedThesisStoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit, cls.data = MODULE.build_audit(REPO_ROOT)

    def test_all_five_evidence_blocks_pass(self) -> None:
        self.assertEqual(self.audit["status"], "pass")
        self.assertEqual(len(self.audit["evidence_blocks"]), 5)
        self.assertTrue(all(row["status"] == "pass" for row in self.audit["evidence_blocks"]))

    def test_studies_are_explicitly_not_pooled(self) -> None:
        rules = " ".join(self.audit["compatibility_rules"]).lower()
        self.assertIn("do not pool", rules)
        self.assertIn("groups 81--90", rules)
        self.assertIn("groups 101--105", rules)

    def test_h4_contains_model_transfer_and_risk_frontier(self) -> None:
        h4 = self.audit["integrated_hypotheses"]["H4"]
        self.assertIn("validation-selected P*", h4)
        self.assertIn("adaptive risk", h4)
        self.assertIn("fixed risk", h4)

    def test_foundation_uses_corrected_continuous_endpoints(self) -> None:
        block = self.audit["evidence_blocks"][0]
        values = block["key_results"]
        self.assertAlmostEqual(values["B0_ADE_m"], 1.2826716899871826)
        self.assertAlmostEqual(values["B1_ADE_m"], 0.09965752065181732)
        self.assertEqual(values["favourable_groups_each_metric"], "5/5")
        self.assertIn("withdrawn", block["claim_boundary"])

    def test_formal_matrix_counts_are_preserved(self) -> None:
        blocks = {row["id"]: row for row in self.audit["evidence_blocks"]}
        self.assertEqual(blocks["F2_r3_broad_predictor_risk"]["rollouts"], 80)
        self.assertEqual(blocks["F3_sf4_supervisor_authority"]["rollouts"], 80)
        self.assertEqual(blocks["F4_v3_offline_three_axis"]["runs"], 27)
        self.assertEqual(blocks["F5_v3_selected_model_carla"]["rollouts"], 80)


if __name__ == "__main__":
    unittest.main()
