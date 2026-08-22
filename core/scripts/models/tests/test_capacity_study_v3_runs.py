#!/usr/bin/env python3
from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from capacity_study_v3_runs import (  # noqa: E402
    convergence_extension_plan,
    core_runs,
    fraction_convergence_extension_plan,
    fraction_runs,
    missing_runs,
    run_manifest,
    select_fraction_learning_rates,
    select_learning_rates,
    select_p_star,
    validate_run_manifest,
)
from capacity_study_v3_protocol import LEARNING_RATES  # noqa: E402


def validation_fixture(*, boundary_cell: str | None = None):
    rows = []
    for spec in core_runs():
        lr_rank = LEARNING_RATES.index(spec.learning_rate)
        score = 1.0 + lr_rank * 0.1 + spec.seed * 1.0e-5
        rows.append(
            {
                "run_id": spec.run_id,
                "model_cell_id": spec.model_cell_id,
                "learning_rate": spec.learning_rate,
                "seed": spec.seed,
                "split": "validation",
                "status": "pass",
                "rollout_macro_nll": score,
                "best_epoch": 79 if spec.model_cell_id == boundary_cell and lr_rank == 0 else 40,
                "epochs_allowed": 80,
            }
        )
    return rows


class CapacityStudyV3RunsTest(unittest.TestCase):
    def test_core_and_fraction_grids_have_exact_counts_and_resume(self):
        core = core_runs()
        fractions = fraction_runs()
        self.assertEqual(len(core), 189)
        self.assertEqual(len({row.run_id for row in core}), 189)
        self.assertEqual(len(fractions), 108)
        self.assertEqual(sum(row.linked_core_run_id is not None for row in fractions), 27)
        self.assertEqual(sum(row.is_additional_fraction_run for row in fractions), 81)
        completed = [row.run_id for row in core[:10]]
        self.assertEqual(len(missing_runs(core, completed)), 179)
        with self.assertRaisesRegex(ValueError, "unknown run ids"):
            missing_runs(core, ["not-planned"])

    def test_manifest_is_deterministic_and_rejects_drift(self):
        first = run_manifest()
        second = run_manifest()
        self.assertEqual(first, second)
        report = validate_run_manifest(first)
        self.assertEqual(report["core"], 189)
        altered = copy.deepcopy(first)
        altered["core_runs"][0]["seed"] = 99
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_run_manifest(altered)

    def test_validation_selection_is_group_complete_and_test_blind(self):
        rows = validation_fixture()
        selection = select_learning_rates(rows)
        self.assertEqual(selection["selection_split"], "validation")
        self.assertEqual(len(selection["selected_cells"]), 21)
        self.assertTrue(
            all(row["selected_learning_rate"] == 3.0e-5 for row in selection["selected_cells"])
        )
        contaminated = copy.deepcopy(rows)
        contaminated[0]["split"] = "test"
        with self.assertRaisesRegex(ValueError, "validation rows only"):
            select_learning_rates(contaminated)
        incomplete = rows[:-1]
        with self.assertRaisesRegex(ValueError, "Expected three validation seeds"):
            select_learning_rates(incomplete)

    def test_p_star_uses_frozen_tie_breakers_and_can_select_mlp(self):
        selection = select_learning_rates(validation_fixture())
        eligibility = {}
        for row in selection["selected_cells"]:
            cell_id = row["model_cell_id"]
            if cell_id.startswith(("mlp-", "transformer-")):
                eligibility[cell_id] = {
                    "converged": True,
                    "capacity_audit_pass": True,
                    "calibration_complete": True,
                    "latency_gate_pass": True,
                    "trainable_parameters": 200_000,
                    "warmed_batch_one_latency": 0.01,
                }
                row["median_validation_rollout_macro_nll"] = 1.0
        # Lexical tie-breaker chooses mlp before transformer when all else is equal.
        selected = select_p_star(selection, eligibility)
        self.assertEqual(selected["role"], "P_star")
        self.assertEqual(selected["family"], "mlp")
        self.assertTrue(selected["model_cell_id"].startswith("mlp-"))

    def test_convergence_boundary_blocks_fresh_test_and_expands_matched_cells(self):
        rows = validation_fixture(boundary_cell="transformer-h1p0-small")
        selection = select_learning_rates(rows)
        plan = convergence_extension_plan(selection, rows)
        self.assertEqual(plan["status"], "requires_extension")
        self.assertFalse(plan["fresh_test_access_allowed"])
        self.assertIn("transformer-h1p0-small", plan["boundary_cells"])
        self.assertIn("mlp-h1p0-small", plan["extension_cells"])
        self.assertIn("head-small", plan["extension_cells"])
        self.assertTrue(all(row["epochs"] == 120 for row in plan["extension_runs"]))

    def test_converged_selection_allows_freeze(self):
        rows = validation_fixture()
        selection = select_learning_rates(rows)
        plan = convergence_extension_plan(selection, rows)
        self.assertEqual(plan["status"], "pass")
        self.assertTrue(plan["fresh_test_access_allowed"])
        self.assertEqual(plan["extension_runs"], [])

    def test_fraction_learning_rate_selection_repeats_within_each_fraction(self):
        rows = []
        for spec in fraction_runs():
            rows.append(
                {
                    "run_id": spec.run_id,
                    "model_cell_id": spec.model_cell_id,
                    "learning_rate": spec.learning_rate,
                    "data_fraction": spec.data_fraction,
                    "seed": spec.seed,
                    "split": "validation",
                    "status": "pass",
                    "rollout_macro_nll": LEARNING_RATES.index(spec.learning_rate),
                }
            )
        selected = select_fraction_learning_rates(rows)
        self.assertEqual(len(selected["selected_fraction_cells"]), 12)
        self.assertTrue(
            all(
                row["selected_learning_rate"] == 3.0e-5
                for row in selected["selected_fraction_cells"]
            )
        )
        for row in rows:
            row["best_epoch"] = (
                79
                if row["model_cell_id"] == "transformer-h1p0-large"
                and row["data_fraction"] == 0.25
                and row["learning_rate"] == 3.0e-5
                else 40
            )
            row["epochs_allowed"] = 80
        selected = select_fraction_learning_rates(rows)
        convergence = fraction_convergence_extension_plan(selected, rows)
        self.assertEqual(convergence["status"], "requires_extension")
        self.assertEqual(convergence["boundary_data_fractions"], [0.25])
        self.assertEqual(len(convergence["extension_runs"]), 9)
        self.assertEqual(
            {row["model_cell_id"] for row in convergence["extension_runs"]},
            {"head-large", "mlp-h1p0-large", "transformer-h1p0-large"},
        )

    def test_boundary_at_extended_budget_fails_closed(self):
        rows = validation_fixture(boundary_cell="transformer-h1p0-small")
        for row in rows:
            if row["model_cell_id"] == "transformer-h1p0-small" and row["learning_rate"] == 3.0e-5:
                row["epochs_allowed"] = 120
                row["best_epoch"] = 119
                row["checkpoint_run_id"] = row["run_id"] + "__extended120"
        selection = select_learning_rates(rows)
        plan = convergence_extension_plan(selection, rows)
        self.assertEqual(plan["status"], "nonconverged_at_max_budget")
        self.assertFalse(plan["fresh_test_access_allowed"])
        self.assertEqual(plan["extension_runs"], [])


if __name__ == "__main__":
    unittest.main()
