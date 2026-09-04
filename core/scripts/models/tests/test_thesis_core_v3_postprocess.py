#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from capacity_study_v3_protocol import atomic_json, sha256_payload  # noqa: E402
from thesis_core_v3_postprocess import (  # noqa: E402
    _branch,
    _hash_valid,
    _stage_complete,
    stage_plan,
)
from thesis_core_v3_runs import thesis_core_manifest  # noqa: E402


class ThesisCorePostprocessTest(unittest.TestCase):
    def test_hash_and_result_branch_contracts(self):
        value = {"status": "pass", "value": 1}
        payload = {**value, "payload_sha256": sha256_payload(value)}
        self.assertTrue(_hash_valid(payload, "payload_sha256"))
        payload["value"] = 2
        self.assertFalse(_hash_valid(payload, "payload_sha256"))
        self.assertEqual(
            _branch({"effect": 1.0, "cluster_interval_95": [0.1, 2.0]}),
            "directional_descriptive_exact_test_resolution_limited",
        )
        self.assertEqual(
            _branch({"effect": -1.0, "cluster_interval_95": [-2.0, -0.1]}),
            "opposing_descriptive_exact_test_resolution_limited",
        )
        self.assertEqual(
            _branch(
                {
                    "effect": 1.0,
                    "cluster_interval_95": [0.1, 2.0],
                    "holm_adjusted_p": 0.04,
                }
            ),
            "supports_preregistered_direction",
        )
        self.assertEqual(
            _branch(
                {
                    "effect": -1.0,
                    "cluster_interval_95": [-2.0, -0.1],
                    "raw_sign_flip_p": 0.04,
                }
            ),
            "opposes_preregistered_direction",
        )
        self.assertEqual(
            _branch({"effect": 0.2, "cluster_interval_95": [-1.0, 1.0]}),
            "inconclusive_or_mixed",
        )

    def test_six_calibration_shards_cover_exactly_27_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            atomic_json(manifest, thesis_core_manifest())
            identifiers = []
            counts = []
            for shard in range(6):
                args = SimpleNamespace(
                    manifest=manifest,
                    stage="calibrate",
                    shard_index=shard,
                    shard_count=6,
                    output_root=root / "calibration",
                    training_root=root / "training",
                    dataset_dir=root / "dataset",
                    cache_dir=root / "cache",
                    base_model=root / "base",
                    anchors=root / "anchors.npy",
                    python_bin="python",
                    calibration_root=None,
                    selection_freeze=None,
                )
                plan = stage_plan(args)
                counts.append(plan["assigned_runs"])
                identifiers.extend(row["run_id"] for row in plan["jobs"])
            self.assertEqual(counts, [5, 5, 5, 4, 4, 4])
            self.assertEqual(len(identifiers), 27)
            self.assertEqual(len(set(identifiers)), 27)

    def test_calibration_stage_requires_both_calibration_and_selection_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "run"
            run_dir = root / run_id
            run_dir.mkdir(parents=True)
            model = {"path": "/model", "sha256_tree": "model"}
            weights = {"path": "/weights", "sha256": "weights"}
            calibration = {
                "status": "pass",
                "calibration_schema_version": "multipath_posthoc_calibration_v4_masked",
                "run_id": run_id,
                "model_cell_id": "head-large",
                "seed": 11,
                "model_artifact": model,
                "cached_weights_artifact": weights,
                "cache_complete_sha256": "cache",
                "dataset_complete_sha256": "dataset",
            }
            calibration["calibration_sha256"] = sha256_payload(calibration)
            atomic_json(run_dir / "calibration.json", calibration)
            self.assertFalse(_stage_complete("calibrate", run_id, root, None))
            selection = {
                "schema_version": (
                    "capacity_history_thesis_core_selection_evaluation_v4_masked"
                ),
                "status": "pass",
                "run_id": run_id,
                "model_cell_id": "head-large",
                "seed": 11,
                "model_artifact": model,
                "cached_weights_artifact": weights,
                "cache_complete_sha256": "cache",
                "dataset_complete_sha256": "dataset",
                "calibration_sha256": calibration["calibration_sha256"],
                "future_validity_contract": "future_valid_mask_fail_closed_v4",
            }
            selection["evaluation_sha256"] = sha256_payload(selection)
            atomic_json(run_dir / "selection_metrics.json", selection)
            self.assertTrue(_stage_complete("calibrate", run_id, root, None))

    def test_heldout_stage_is_blocked_without_selection_freeze(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / "manifest.json"
            atomic_json(manifest, thesis_core_manifest())
            args = SimpleNamespace(
                manifest=manifest,
                stage="heldout",
                shard_index=0,
                shard_count=6,
                output_root=root / "heldout",
                training_root=root / "training",
                dataset_dir=root / "dataset",
                cache_dir=root / "cache",
                base_model=root / "base",
                anchors=root / "anchors.npy",
                python_bin="python",
                calibration_root=root / "calibration",
                selection_freeze=root / "missing.json",
            )
            with self.assertRaisesRegex(ValueError, "blocked"):
                stage_plan(args)


if __name__ == "__main__":
    unittest.main()
