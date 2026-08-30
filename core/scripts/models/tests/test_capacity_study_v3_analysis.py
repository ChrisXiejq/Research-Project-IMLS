#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from capacity_study_v3_analysis import (  # noqa: E402
    aggregate_windows_by_rollout,
    conflict_zone_probability_mass,
    holm_adjust,
    measure_latency,
    paired_sign_flip_p,
    pareto_membership,
    response_onset_timing_error_s,
    synthesize_three_axes,
    target_speed_profile_rmse,
    validate_claim_evidence,
)


def three_axis_fixture():
    values = {
        "transformer-h1p0-small": 2.0,
        "transformer-h1p0-large": 1.0,
        "transformer-h0p0-large": 1.8,
        "transformer-h0p4-large": 1.4,
        "mlp-h0p0-large": 1.8,
        "mlp-h0p4-large": 1.6,
        "mlp-h1p0-large": 1.4,
    }
    rows = []
    for init_id in range(51, 61):
        for seed in (11, 23, 37):
            for cell_id, value in values.items():
                for window_id in range(2):
                    rows.append(
                        {
                            "dataset": "general_test",
                            "model_cell_id": cell_id,
                            "seed": seed,
                            "ego_init_id": init_id,
                            "rollout_id": f"init{init_id}_reactive",
                            "window_id": window_id,
                            "rollout_macro_nll": value + 0.001 * (init_id - 51),
                        }
                    )
    return rows


class CapacityStudyV3AnalysisTest(unittest.TestCase):
    def test_exact_sign_flip_uses_exact_denominator(self):
        self.assertAlmostEqual(
            paired_sign_flip_p({index: 1.0 for index in range(5)}),
            2.0 / 32.0,
        )

    def test_three_axis_known_effects_and_independent_units(self):
        report = synthesize_three_axes(three_axis_fixture())
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["independent_init_groups"], 10)
        effects = {
            row["contrast_id"]: row["effect"] for row in report["primary_contrasts"]
        }
        self.assertAlmostEqual(
            effects["H1_capacity_transformer_full_small_minus_large"], 1.0
        )
        self.assertAlmostEqual(
            effects["H2_information_mlp_snapshot_minus_full"], 0.4
        )
        self.assertAlmostEqual(
            effects["H2_information_transformer_snapshot_minus_full"], 0.8
        )
        self.assertAlmostEqual(
            effects["H3_attention_history_gain_difference_in_differences"], 0.4
        )
        self.assertTrue(
            all("holm_adjusted_p" in row for row in report["primary_contrasts"])
        )

    def test_rollout_macro_does_not_treat_duplicate_windows_as_independent(self):
        rows = three_axis_fixture()
        aggregated = aggregate_windows_by_rollout(rows, ["rollout_macro_nll"])
        self.assertEqual(len(aggregated), 10 * 3 * 7)
        duplicated = rows + rows
        aggregated_again = aggregate_windows_by_rollout(
            duplicated, ["rollout_macro_nll"]
        )
        self.assertEqual(len(aggregated_again), len(aggregated))
        self.assertEqual(
            aggregated_again[0]["rollout_macro_nll"], aggregated[0]["rollout_macro_nll"]
        )

    def test_interaction_metrics_have_exact_analytic_values(self):
        times = [0.0, 0.2, 0.4, 0.6]
        truth = [[0.0, 0.0], [2.0, 0.0], [3.8, 0.0], [5.4, 0.0]]
        prediction = [[0.0, 0.0], [2.0, 0.0], [4.0, 0.0], [5.8, 0.0]]
        self.assertAlmostEqual(
            target_speed_profile_rmse(truth, truth, times), 0.0
        )
        self.assertAlmostEqual(
            response_onset_timing_error_s(prediction, truth, times), 0.2
        )
        mass = conflict_zone_probability_mass(
            [
                [[5.0, 5.0], [6.0, 6.0]],
                [[5.0, 0.0], [4.0, 0.0]],
                [[-5.0, 0.0], [-6.0, 0.0]],
            ],
            [0.2, 0.5, 0.3],
        )
        self.assertAlmostEqual(mass, 0.5)

    def test_holm_latency_and_pareto_contracts(self):
        adjusted = holm_adjust({"a": 0.01, "b": 0.03, "c": 0.20})
        self.assertAlmostEqual(adjusted["a"], 0.03)
        self.assertAlmostEqual(adjusted["b"], 0.06)
        self.assertAlmostEqual(adjusted["c"], 0.20)
        latency = measure_latency(lambda: sum(range(10)), warmup_count=2, measured_count=4, trainable_parameters=100)
        self.assertEqual(latency["warmup_count"], 2)
        self.assertEqual(latency["measured_count"], 4)
        self.assertEqual(latency["estimated_dense_multiply_add_flops"], 200)
        frontier = pareto_membership(
            [
                {"id": "fast_good", "rollout_macro_nll": 1.0, "mean_ms": 1.0},
                {"id": "slow_bad", "rollout_macro_nll": 2.0, "mean_ms": 2.0},
                {"id": "slow_best", "rollout_macro_nll": 0.5, "mean_ms": 3.0},
            ]
        )
        membership = {row["id"]: row["pareto"] for row in frontier}
        self.assertTrue(membership["fast_good"])
        self.assertFalse(membership["slow_bad"])
        self.assertTrue(membership["slow_best"])

    def test_appendix_corruptions_cannot_support_headline_claims(self):
        validate_claim_evidence("information", ["trained_horizon_full_minus_snapshot"])
        with self.assertRaisesRegex(ValueError, "appendix diagnostics"):
            validate_claim_evidence("architecture", ["history_shuffle_transformer"])


if __name__ == "__main__":
    unittest.main()
