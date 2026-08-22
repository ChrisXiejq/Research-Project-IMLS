#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from capacity_study_v3_protocol import atomic_json, sha256_payload  # noqa: E402
from thesis_core_v3_postprocess import _branch, _hash_valid, stage_plan  # noqa: E402
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
            "supports_preregistered_direction",
        )
        self.assertEqual(
            _branch({"effect": -1.0, "cluster_interval_95": [-2.0, -0.1]}),
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
