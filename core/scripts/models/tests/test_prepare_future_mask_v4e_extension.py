from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload
from prepare_future_mask_v4e_extension import prepare, tree_hash
from thesis_core_v3_runs import thesis_core_manifest


class PrepareUniformExtensionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.destination = self.root / "destination"
        self.spill = self.root / "spill"
        self.heldout = self.root / "heldout"
        self.manifest = self.root / "manifest.json"
        self.trigger = self.root / "trigger.json"
        manifest = thesis_core_manifest()
        atomic_json(self.manifest, manifest)
        for spec in manifest["runs"]:
            self._source_run(spec["run_id"])
        trigger = {
            "status": "fail",
            "runs": 27,
            "unresolved_boundary_underfit_runs": [manifest["runs"][0]["run_id"]],
        }
        trigger["audit_sha256"] = sha256_payload(trigger)
        atomic_json(self.trigger, trigger)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _source_run(self, run_id: str) -> None:
        directory = self.source / run_id
        checkpoints = directory / "epoch_checkpoints"
        backup = directory / "resume_backup"
        checkpoints.mkdir(parents=True)
        backup.mkdir()
        history = directory / "history.csv"
        history.write_text("val_rollout_macro_nll\n2.0\n1.9\n", encoding="utf-8")
        weights = directory / "cached_best.weights.h5"
        weights.write_bytes(b"weights")
        (backup / "checkpoint").write_bytes(b"backup")
        (checkpoints / "epoch_001.weights.h5").write_bytes(b"one")
        (checkpoints / "epoch_002.weights.h5").write_bytes(b"two")
        completion = {
            "schema_version": "capacity_history_thesis_core_training_complete_v4_masked",
            "status": "pass",
            "future_validity_contract": "future_valid_mask_fail_closed_v4",
            "run_id": run_id,
            "best_epoch": 2,
            "cached_weights": {
                "path": str(weights),
                "bytes": weights.stat().st_size,
                "sha256": sha256_file(weights),
            },
            "history_csv": {
                "path": str(history),
                "bytes": history.stat().st_size,
                "sha256": sha256_file(history),
            },
            "resume_backup": tree_hash(backup),
            "epoch_checkpoints": tree_hash(checkpoints),
        }
        completion["completion_sha256"] = sha256_payload(completion)
        atomic_json(directory / "TRAINING_COMPLETE.json", completion)

    def args(self) -> argparse.Namespace:
        return argparse.Namespace(
            manifest=self.manifest,
            source_training_root=self.source,
            trigger_audit=self.trigger,
            corrected_heldout_root=self.heldout,
            destination_root=self.destination,
            spill_root=self.spill,
            output=self.root / "EXTENSION_PROTOCOL.json",
        )

    def test_all_runs_are_seeded_uniformly_with_hardlinks(self) -> None:
        result = prepare(self.args())
        self.assertEqual(len(result["run_seed_receipts"]), 27)
        self.assertTrue(result["all_27_runs_extended_uniformly"])
        first = next(iter(result["run_seed_receipts"]))
        source = self.source / first / "epoch_checkpoints/epoch_001.weights.h5"
        destination = (
            self.destination / first / "epoch_checkpoints/epoch_001.weights.h5"
        )
        self.assertEqual(source.stat().st_ino, destination.stat().st_ino)

    def test_any_corrected_heldout_artifact_blocks_extension(self) -> None:
        self.heldout.mkdir()
        (self.heldout / "opened.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "held-out"):
            prepare(self.args())


if __name__ == "__main__":
    unittest.main()
