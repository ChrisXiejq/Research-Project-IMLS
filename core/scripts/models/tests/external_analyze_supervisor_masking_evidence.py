
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

from core.scripts.models.analysis.analyze_supervisor_masking_evidence import (
    V3_EXTERNAL_SCHEMA_VERSION,
    analyze_aligned_attenuation,
    build_analysis,
)


class AlignedAttenuationTest(unittest.TestCase):
    def _records(self, *, pre_delta=1.0, post_delta=0.2):
        rows = []
        for group_id in range(4):
            for active in (False, True):
                alignment = f"g{group_id}-{'a' if active else 'i'}"
                rows.extend(
                    [
                        {
                            "alignment_id": alignment,
                            "group_id": group_id,
                            "policy": "A",
                            "nominal_command": [0.0, 0.0],
                            "executed_command": [0.0, 0.0],
                            "supervisor_active": active,
                        },
                        {
                            "alignment_id": alignment,
                            "group_id": group_id,
                            "policy": "B",
                            "nominal_command": [pre_delta, 0.0],
                            "executed_command": [post_delta if active else pre_delta, 0.0],
                            "supervisor_active": active,
                        },
                    ]
                )
        return rows

    def test_identifies_immediate_command_masking_only_when_active(self):
        result = analyze_aligned_attenuation(
            self._records(), policy_pair=["A", "B"], draws=500
        )
        active = next(row for row in result["strata"] if row["stratum"] == "active")
        inactive = next(row for row in result["strata"] if row["stratum"] == "inactive")
        self.assertAlmostEqual(active["retention_ratio"], 0.2)
        self.assertEqual(active["verdict"], "causally_identified_command_level_masking")
        self.assertAlmostEqual(inactive["retention_ratio"], 1.0)
        self.assertEqual(inactive["verdict"], "retained")
        self.assertTrue(result["causal_command_masking_identified"])
        self.assertFalse(result["trajectory_level_causal_claim_licensed"])

    def test_degenerate_nominal_denominator_fails_closed(self):
        result = analyze_aligned_attenuation(
            self._records(pre_delta=0.0, post_delta=0.0),
            policy_pair=["A", "B"],
            draws=500,
        )
        active = next(row for row in result["strata"] if row["stratum"] == "active")
        self.assertEqual(active["status"], "fail_closed_degenerate_denominator")
        self.assertIsNone(active["retention_ratio"])
        self.assertEqual(active["verdict"], "controller_insensitivity_not_supervisor_masking")
        self.assertFalse(result["causal_command_masking_identified"])

    def test_missing_policy_pair_is_rejected(self):
        rows = self._records()
        rows.pop()
        with self.assertRaisesRegex(ValueError, "exactly one row per policy"):
            analyze_aligned_attenuation(rows, policy_pair=["A", "B"], draws=500)


class SupervisorMaskingCanonicalIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[4]

    def _external_v3(self):
        rows = []
        sources = []
        for predictor in ("B1", "P_star"):
            for risk in ("adaptive", "fixed_medium"):
                for target in ("assertive_constant_speed", "defensive_reactive"):
                    for init_id in range(81, 91):
                        adaptive = risk == "adaptive"
                        pstar = predictor == "P_star"
                        rows.append(
                            {
                                "predictor": predictor,
                                "risk": risk,
                                "target": target,
                                "ego_init_id": init_id,
                                "mean_tightening": 1.3 if adaptive else 1.6,
                                "mean_nominal_accel_mps2": 0.1 + 0.01 * adaptive + 0.02 * pstar,
                                "mean_actual_accel_mps2": 0.3 + 0.005 * adaptive + 0.01 * pstar,
                                "mean_abs_supervisor_accel_delta_mps2": 0.8,
                            }
                        )
                        sources.append(
                            {
                                "relative_path": f"{predictor}/{risk}/{target}/{init_id}.jsonl",
                                "sha256": f"{len(sources) + 1:064x}",
                                "line_count": 10,
                                "bytes": 100,
                            }
                        )
        return {
            "schema_version": V3_EXTERNAL_SCHEMA_VERSION,
            "status": "pass",
            "population": {
                "rollouts": 80,
                "ego_init_ids": list(range(81, 91)),
                "step_rows_are_not_independent_units": True,
            },
            "rollout_summaries": rows,
            "source_inventory": sources,
            "same_state_alternative_commands_present": False,
        }

    def test_canonical_release_reconciles_without_pooling_or_masking_overclaim(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "evidence.json"
            result = build_analysis(self.root, output)
        self.assertEqual(result["status"], "pass")
        h1 = result["H1_authority"]
        self.assertEqual(h1["arms"]["on"]["completion_successes"], 40)
        self.assertEqual(h1["arms"]["off"]["completion_successes"], 0)
        self.assertEqual(h1["arms"]["off"]["yield_rule_failures"], 38)
        self.assertEqual(h1["arms"]["off"]["adverse_collision_rollouts"], 21)
        self.assertEqual(h1["mechanism"]["solver_paths"]["factual_solver_attempts"], 18552)
        self.assertTrue(result["H2_predictor_transfer"]["blocks_are_juxtaposed_not_pooled"])
        self.assertEqual(
            result["H2_predictor_transfer"]["candidate_and_executed_control"]["status"],
            "unavailable_no_provenance_bound_raw_summary",
        )
        h3 = result["H3_risk_transfer"]
        self.assertEqual(len(h3["r3_full_fixed_frontier"]["comparisons"]), 12)
        self.assertEqual(h3["r3_full_fixed_frontier"]["adaptive_dominates"], 3)
        self.assertEqual(
            result["identification_verdicts"]["H3_strongest_licensed_verdict"],
            "consistent_with_masking",
        )
        self.assertEqual(result["population_separation"]["pooled_cross_population_estimates"], 0)

    def test_provenance_bound_external_summary_adds_descriptive_command_layer(self):
        with tempfile.TemporaryDirectory() as directory:
            external = Path(directory) / "v3.json"
            external.write_text(json.dumps(self._external_v3()))
            result = build_analysis(
                self.root,
                Path(directory) / "evidence.json",
                v3_command_audit_path=external,
            )
        risk = result["H3_risk_transfer"]["v3_constraint_candidate_executed_transfer"]
        self.assertEqual(risk["status"], "available_descriptive_different_factual_trajectories")
        self.assertEqual(len(risk["contrasts"]), 4)
        self.assertTrue(all(not row["causal_attenuation_licensed"] for row in risk["contrasts"]))
        tightening = risk["contrasts"][0]["effects"]["mean_tightening"]["mean_effect"]
        self.assertAlmostEqual(tightening, -0.3)
        self.assertEqual(
            result["identification_verdicts"]["H3_strongest_licensed_verdict"],
            "consistent_with_masking",
        )

    def test_requested_missing_external_summary_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                build_analysis(
                    self.root,
                    Path(directory) / "evidence.json",
                    v3_command_audit_path=Path(directory) / "missing.json",
                )

    def test_malformed_external_provenance_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = self._external_v3()
            payload["source_inventory"][0]["sha256"] = "not-a-hash"
            external = Path(directory) / "v3.json"
            external.write_text(json.dumps(payload))
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                build_analysis(
                    self.root,
                    Path(directory) / "evidence.json",
                    v3_command_audit_path=external,
                )

    def test_shadow_analysis_is_consumed_at_immediate_command_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            shadow = Path(directory) / "shadow.json"
            shadow.write_text(
                json.dumps(
                    {
                        "schema_version": "shadow_command_transmission_analysis_v1",
                        "status": "pass",
                        "source": {"path": "shadow.csv", "sha256": "a" * 64, "rows": 240},
                        "integrity": {
                            "shadow_actuation_count": 0,
                            "all_factual_parity": True,
                        },
                        "causal_scope": "same-state immediate longitudinal command transmission only",
                        "prohibited_overclaim": "No trajectory-level counterfactual claim.",
                        "aggregates": [
                            {
                                "axis": "risk",
                                "matched_policy": "B1",
                                "stratum": "active",
                                "monitor_separation_accel_mps2": 0.5,
                                "enabled_separation_accel_mps2": 0.1,
                                "retention_ratio": 0.2,
                                "verdict": "command_level_masking_identified",
                            },
                            {
                                "axis": "predictor",
                                "matched_policy": "fixed_medium",
                                "stratum": "active",
                                "monitor_separation_accel_mps2": 0.01,
                                "enabled_separation_accel_mps2": 0.01,
                                "retention_ratio": None,
                                "verdict": "controller_insensitivity_supervisor_masking_not_testable",
                            },
                        ],
                    }
                )
            )
            result = build_analysis(
                self.root,
                Path(directory) / "evidence.json",
                aligned_evidence_path=shadow,
            )
        self.assertEqual(
            result["identification_verdicts"]["H3_strongest_licensed_verdict"],
            "causally_identified_command_level_masking",
        )
        self.assertEqual(
            result["identification_verdicts"]["H2_strongest_licensed_verdict"],
            "consistent_with_masking",
        )
        self.assertTrue(result["H3_risk_transfer"]["causal_masking_identified"])
        self.assertFalse(result["H2_predictor_transfer"]["causal_masking_identified"])


if __name__ == "__main__":
    unittest.main()
