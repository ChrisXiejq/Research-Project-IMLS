
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import copy
import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.tools.build_supervisor_masking_contract import (
    _safe_claim_language,
    _sanitize_remote,
    build_contract,
)


class SupervisorMaskingContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]
        cls.dissertation_root = cls.root.parent / "Jiaqi-Xie-Dissertation"

    def build(self, directory: str) -> tuple[dict, Path]:
        output = Path(directory) / "contract"
        complete = build_contract(self.root, self.dissertation_root, output)
        return complete, output

    def test_builds_v2_contract_without_modifying_v1(self):
        prior_marker = (
            self.root
            / "docs/paper/generated/supervisor_bottleneck_v1/paper_release/"
            "PAPER_EVIDENCE_COMPLETE.json"
        )
        before = prior_marker.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            complete, output = self.build(directory)
            self.assertEqual(complete["status"], "pass")
            self.assertEqual(complete["schema_version"], "supervisor_masking_contract_complete_v2")
            self.assertEqual(complete["hypotheses"], ["H1", "H2", "H3"])
            self.assertEqual(complete["claims"], 10)
            self.assertEqual(complete["populations"], 8)
            self.assertTrue(complete["prior_release_immutable"])
            self.assertTrue(all(complete["checks"].values()))
            for name in complete["products"]:
                self.assertTrue((output / name).is_file(), name)
        self.assertEqual(prior_marker.read_bytes(), before)

    def test_immutable_baseline_records_heads_remotes_divergence_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            _, output = self.build(directory)
            baseline = json.loads((output / "immutable_baseline.json").read_text())
            self.assertEqual(
                baseline["schema_version"], "supervisor_masking_immutable_baseline_v2"
            )
            self.assertEqual(baseline["status"], "pass")
            repositories = {row["name"]: row for row in baseline["repositories"]}
            self.assertEqual(set(repositories), {"experiment", "dissertation"})
            for row in repositories.values():
                self.assertRegex(row["head"], r"^[0-9a-f]{40}$")
                self.assertRegex(row["head_tree"], r"^[0-9a-f]{40}$")
                self.assertIn("origin", row["remotes"])
                self.assertIn("worktree_inventory", row)
                self.assertIsInstance(row["ahead"], int)
                self.assertIsInstance(row["behind"], int)
            prior = baseline["prior_release"]
            self.assertTrue(prior["all_artifacts_match"])
            self.assertTrue(prior["artifact_checks"])
            self.assertTrue(all(row["matches"] for row in prior["artifact_checks"]))

    def test_terminology_has_one_located_concept_per_required_term(self):
        required = {
            "MultiPath",
            "multimodal SMPC",
            "fixed risk allocation",
            "adaptive risk allocation",
            "candidate command",
            "executed command",
            "supervisor authority",
            "attenuation",
            "compression",
            "masking",
        }
        with tempfile.TemporaryDirectory() as directory:
            _, output = self.build(directory)
            ledger = json.loads((output / "terminology_ledger.json").read_text())
            self.assertEqual(
                ledger["schema_version"], "supervisor_masking_terminology_ledger_v2"
            )
            terms = ledger["terms"]
            self.assertTrue(required.issubset({row["canonical_term"] for row in terms}))
            self.assertEqual(len(terms), len({row["term_id"] for row in terms}))
            for row in terms:
                self.assertTrue((self.root / row["code_or_evidence_locator"]).is_file())
                self.assertTrue(row["do_not_conflate_with"])

    def test_identification_ladder_reserves_masking_for_aligned_or_factorial_design(self):
        with tempfile.TemporaryDirectory() as directory:
            _, output = self.build(directory)
            payload = json.loads((output / "identification_ladder.json").read_text())
            levels = payload["levels"]
            self.assertEqual([row["level"] for row in levels], list(range(1, 7)))
            self.assertEqual(levels[-1]["verdict"], "causally_identified_masking")
            alternatives = levels[-1]["required_evidence_any_of"]
            self.assertTrue(any("same-state" in " ".join(items) for items in alternatives))
            self.assertTrue(any("factorial" in " ".join(items) for items in alternatives))
            self.assertIn("counterfactual trajectory", levels[-1]["does_not_license"])

    def test_hypotheses_include_treatments_units_layers_and_falsification(self):
        required_fields = {
            "treatment",
            "independent_unit",
            "upstream_outcome",
            "candidate_control_outcome",
            "executed_outcome",
            "falsification_rule",
            "population_boundary",
            "claimable_conclusion",
            "current_verdict_vocabulary",
            "prohibited_overclaims",
            "sources",
        }
        with tempfile.TemporaryDirectory() as directory:
            _, output = self.build(directory)
            registry = json.loads((output / "hypothesis_registry.json").read_text())
            self.assertEqual(set(registry["hypotheses"]), {"H1", "H2", "H3"})
            for hypothesis in registry["hypotheses"].values():
                self.assertTrue(required_fields.issubset(hypothesis))
            self.assertEqual(
                set(registry["hypotheses"]["H2"]["subquestions"]),
                {"Capacity", "Information", "Architecture"},
            )

    def test_rejects_universal_safety_and_unidentified_masking_language(self):
        safe = {
            "paper_argument": "Bounded nominal yielding result.",
            "hypotheses": {
                "H1": {"claimable_conclusion": "Observed in the tested sample."}
            },
        }
        _safe_claim_language(safe)
        unsafe = copy.deepcopy(safe)
        unsafe["hypotheses"]["H1"]["claimable_conclusion"] = (
            "The rule-based supervisor guarantees safety."
        )
        with self.assertRaisesRegex(ValueError, "Unsafe or unidentified"):
            _safe_claim_language(unsafe)
        unidentified = copy.deepcopy(safe)
        unidentified["paper_argument"] = (
            "All predictor improvements are masked by the shared stack."
        )
        with self.assertRaisesRegex(ValueError, "Unsafe or unidentified"):
            _safe_claim_language(unidentified)

    def test_every_claim_has_source_locator_xor_explicit_gap(self):
        with tempfile.TemporaryDirectory() as directory:
            _, output = self.build(directory)
            matrix = json.loads((output / "claim_evidence_matrix.json").read_text())
            claims = matrix["claims"]
            self.assertTrue(
                {"H2_CAPACITY", "H2_INFORMATION", "H2_ARCHITECTURE"}.issubset(
                    {row["claim_id"] for row in claims}
                )
            )
            for row in claims:
                self.assertNotEqual(bool(row["source_locators"]), bool(row["evidence_gap"]))
                if row["source_locators"]:
                    for source in row["source_locators"]:
                        self.assertTrue((self.root / source["path"]).is_file())
                        self.assertRegex(source["sha256"], r"^[0-9a-f]{64}$")
                else:
                    self.assertTrue(row["evidence_gap"]["missing_estimand"])

    def test_populations_keep_units_denominators_and_completion_states_distinct(self):
        with tempfile.TemporaryDirectory() as directory:
            _, output = self.build(directory)
            registry = json.loads((output / "population_registry.json").read_text())
            rows = {row["population_id"]: row for row in registry["populations"]}
            self.assertEqual(
                set(rows),
                {
                    "foundation_prediction",
                    "V3_CIA_offline",
                    "V3_selected_model_closed_loop",
                    "R3_predictor_risk",
                    "SF4_authority",
                    "legacy_timing_shift",
                    "supervisor_threshold_sweep",
                    "legacy_implicit_filter_smoke",
                },
            )
            self.assertEqual(rows["foundation_prediction"]["denominator"]["rollouts"], 20)
            self.assertEqual(rows["V3_CIA_offline"]["denominator"]["valid_runs"], 27)
            self.assertEqual(rows["V3_selected_model_closed_loop"]["denominator"]["rollouts"], 80)
            self.assertEqual(rows["R3_predictor_risk"]["denominator"]["rollouts"], 80)
            self.assertEqual(rows["SF4_authority"]["denominator"]["rollouts"], 80)
            self.assertEqual(rows["legacy_timing_shift"]["denominator"]["rollouts"], 120)
            self.assertIsNone(rows["supervisor_threshold_sweep"]["completion_marker"])
            self.assertEqual(
                rows["supervisor_threshold_sweep"]["availability"],
                "not_present_in_canonical_generated_evidence",
            )
            self.assertEqual(
                rows["legacy_implicit_filter_smoke"]["pooling_permission"],
                "excluded_from_headline_evidence",
            )
            signatures = [row["population_signature"] for row in rows.values()]
            self.assertEqual(len(signatures), len(set(signatures)))

    def test_remote_credentials_are_sanitized(self):
        self.assertEqual(
            _sanitize_remote("https://secret@example.com/owner/repo.git"),
            "https://example.com/owner/repo.git",
        )
        self.assertEqual(
            _sanitize_remote("git@github.com:owner/repo.git"),
            "git@github.com:owner/repo.git",
        )


if __name__ == "__main__":
    unittest.main()
