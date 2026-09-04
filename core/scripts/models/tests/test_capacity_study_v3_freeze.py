#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import copy
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from capacity_model_config_v3 import capacity_manifest  # noqa: E402
from capacity_study_v3_freeze import (  # noqa: E402
    build_selection_freeze,
    calibration_jobs,
    fresh_evaluation_jobs,
    validate_calibration_record,
    validate_selection_freeze,
)
from capacity_study_v3_runs import core_runs, select_learning_rates  # noqa: E402
from capacity_study_v3_protocol import LEARNING_RATES  # noqa: E402


def validation_rows():
    rows = []
    for spec in core_runs():
        score = 2.0 + 0.1 * LEARNING_RATES.index(spec.learning_rate)
        if spec.model_cell_id == "mlp-h0p4-small":
            score -= 1.0
        rows.append(
            {
                "run_id": spec.run_id,
                "model_cell_id": spec.model_cell_id,
                "learning_rate": spec.learning_rate,
                "seed": spec.seed,
                "split": "validation",
                "status": "pass",
                "rollout_macro_nll": score + spec.seed * 1.0e-5,
                "best_epoch": 40,
                "epochs_allowed": 80,
            }
        )
    return rows


def freeze_inputs():
    selection = select_learning_rates(validation_rows())
    capacity = capacity_manifest()
    head_counts = {row["capacity_tier"]: row["trainable_parameters"] for row in capacity["head_configs"]}
    encoder_counts = {
        (row["family"], row["history_horizon_s"], row["capacity_tier"]): row["trainable_parameters"]
        for row in capacity["encoder_configs"]
    }
    specs = {row.run_id: row for row in core_runs()}
    completions = {}
    calibrations = {}
    latencies = {}
    for cell in selection["selected_cells"]:
        for run_id in cell["retained_run_ids"]:
            spec = specs[run_id]
            count = (
                head_counts[spec.capacity_tier]
                if spec.family == "head"
                else encoder_counts[(spec.family, spec.history_horizon_s, spec.capacity_tier)]
            )
            identity = (run_id.encode("utf-8").hex() + "0" * 64)[:64]
            completions[run_id] = {
                "status": "pass",
                "run_id": run_id,
                "family": spec.family,
                "capacity_tier": spec.capacity_tier,
                "history_horizon_s": spec.history_horizon_s,
                "seed": spec.seed,
                "parameters": {
                    "trainable_parameters": count,
                    "total_parameters": count + 1_000_000,
                },
                "capacity_config": {"trainable_parameters": count},
                "best_model": {"sha256_tree": identity},
                "training_wall_time_s": 10.0,
                "tensorflow_version": "fixture",
                "visible_devices": ["GPU:0"],
            }
            calibrations[run_id] = {
                "fit_split": "val",
                "parameters": {"temperature": 1.0, "covariance_scale": 1.0},
                "model_artifact": {"sha256_tree": identity},
                "calibration_fit_uses_test": False,
            }
            latencies[run_id] = {"mean_ms": 5.0}
    return selection, completions, calibrations, latencies


class CapacityStudyV3FreezeTest(unittest.TestCase):
    def test_calibration_jobs_cover_every_retained_seed(self):
        selection, _, _, _ = freeze_inputs()
        jobs = calibration_jobs(
            selection,
            training_root="train",
            output_root="calibration",
            merged_dir="merged",
            anchors="anchors.npy",
        )
        self.assertEqual(len(jobs), 63)
        self.assertEqual(len({row["run_id"] for row in jobs}), 63)
        self.assertTrue(all(row["split"] == "val" for row in jobs))
        self.assertTrue(all(row["require_complete_interaction_history"] for row in jobs))

    def test_calibration_rejects_test_fit_and_model_drift(self):
        record = {
            "fit_split": "val",
            "parameters": {"temperature": 1.0, "covariance_scale": 1.0},
            "model_artifact": {"sha256_tree": "abc"},
        }
        validate_calibration_record(record, expected_model_identity="abc")
        contaminated = copy.deepcopy(record)
        contaminated["fit_split"] = "test"
        with self.assertRaisesRegex(ValueError, "validation only"):
            validate_calibration_record(contaminated, expected_model_identity="abc")
        with self.assertRaisesRegex(ValueError, "binding mismatch"):
            validate_calibration_record(record, expected_model_identity="different")

    def test_selection_freeze_chooses_best_sequence_model_without_test_access(self):
        selection, completions, calibrations, latencies = freeze_inputs()
        freeze = build_selection_freeze(
            selection=selection,
            convergence={"status": "pass", "fresh_test_access_allowed": True},
            training_completions=completions,
            calibration_records=calibrations,
            latency_records=latencies,
            data_provenance={"train": "hash-train", "validation": "hash-val"},
            source_revision="fixture",
        )
        validate_selection_freeze(freeze)
        self.assertEqual(freeze["P_star"]["model_cell_id"], "mlp-h0p4-small")
        self.assertEqual(freeze["P_star"]["family"], "mlp")
        self.assertFalse(freeze["selection_uses_fresh_test"])
        self.assertIn("representative_run_id", freeze["B1"])

        jobs = fresh_evaluation_jobs(
            freeze,
            training_root="train",
            calibration_root="calibration",
            dataset_roots={"general_test": "general", "interaction_challenge": "challenge"},
            output_root="evaluation",
            anchors="anchors.npy",
        )
        self.assertEqual(len(jobs), 126)
        self.assertTrue(all(row["interaction_ablation"] == "none" for row in jobs))

    def test_freeze_requires_all_seed_artifacts_and_convergence(self):
        selection, completions, calibrations, latencies = freeze_inputs()
        completions.pop(next(iter(completions)))
        with self.assertRaisesRegex(ValueError, "63 retained runs"):
            build_selection_freeze(
                selection=selection,
                convergence={"status": "pass", "fresh_test_access_allowed": True},
                training_completions=completions,
                calibration_records=calibrations,
                latency_records=latencies,
                data_provenance={},
                source_revision="fixture",
            )
        selection, completions, calibrations, latencies = freeze_inputs()
        with self.assertRaisesRegex(ValueError, "convergence"):
            build_selection_freeze(
                selection=selection,
                convergence={"status": "requires_extension", "fresh_test_access_allowed": False},
                training_completions=completions,
                calibration_records=calibrations,
                latency_records=latencies,
                data_provenance={},
                source_revision="fixture",
            )


if __name__ == "__main__":
    unittest.main()
