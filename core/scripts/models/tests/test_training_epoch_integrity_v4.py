from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import csv
import tempfile
import unittest
from pathlib import Path

import h5py

from training_epoch_integrity_v4 import (
    inspect_epoch_artifacts,
    restored_early_stopping_state,
)


class EpochArtifactIntegrityTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.history = self.root / "history.csv"
        self.checkpoints = self.root / "epoch_checkpoints"
        self.checkpoints.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_history(self, epochs: list[int]) -> None:
        with self.history.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["epoch", "loss", "val_rollout_macro_nll"]
            )
            writer.writeheader()
            for epoch in epochs:
                writer.writerow(
                    {"epoch": epoch, "loss": 1.0, "val_rollout_macro_nll": 1.0}
                )

    def write_checkpoint(self, epoch: int, *, valid: bool = True) -> None:
        path = self.checkpoints / f"epoch_{epoch:03d}.weights.h5"
        if valid:
            with h5py.File(path, "w") as handle:
                handle.create_dataset("weight", data=[float(epoch)])
        else:
            path.write_bytes(b"truncated")

    def write_backup(self, epoch: int) -> Path:
        backup = self.root / "resume_backup" / "chief"
        backup.mkdir(parents=True)
        (backup / f"ckpt-{epoch}.index").write_bytes(b"index")
        (backup / f"ckpt-{epoch}.data-00000-of-00001").write_bytes(b"data")
        return backup.parent

    def test_contiguous_population_passes(self) -> None:
        self.write_history([0, 1, 2])
        for epoch in (1, 2, 3):
            self.write_checkpoint(epoch)
        report = inspect_epoch_artifacts(
            self.history,
            self.checkpoints,
            backup_dir=self.write_backup(3),
            validate_hdf5=True,
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["history_rows"], 3)

    def test_equal_counts_with_shared_gap_fail(self) -> None:
        self.write_history([0, 2])
        for epoch in (1, 3):
            self.write_checkpoint(epoch)
        report = inspect_epoch_artifacts(self.history, self.checkpoints)
        self.assertEqual(report["status"], "fail")
        self.assertIn(
            "history_epoch_sequence_not_contiguous_from_zero", report["errors"]
        )
        self.assertIn(
            "checkpoint_epoch_sequence_not_contiguous_from_one", report["errors"]
        )

    def test_truncated_hdf5_fails(self) -> None:
        self.write_history([0])
        self.write_checkpoint(1, valid=False)
        report = inspect_epoch_artifacts(
            self.history, self.checkpoints, validate_hdf5=True
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["unreadable_checkpoints"], ["epoch_001.weights.h5"])

    def test_optimizer_backup_must_match_committed_history(self) -> None:
        self.write_history([0, 1])
        for epoch in (1, 2):
            self.write_checkpoint(epoch)
        report = inspect_epoch_artifacts(
            self.history, self.checkpoints, backup_dir=self.write_backup(3)
        )
        self.assertEqual(report["status"], "fail")
        self.assertIn("optimizer_backup_history_epoch_mismatch", report["errors"])

    def test_early_stopping_state_is_restored_from_full_history(self) -> None:
        state = restored_early_stopping_state(
            [3.0, 2.0, 2.1, 2.2, 2.3], patience=3
        )
        self.assertEqual(state["best_epoch"], 2)
        self.assertEqual(state["consecutive_non_improving_epochs"], 3)
        self.assertTrue(state["stop_already_reached"])

    def test_new_improvement_resets_early_stopping_wait(self) -> None:
        state = restored_early_stopping_state(
            [3.0, 2.0, 2.1, 1.9], patience=3
        )
        self.assertEqual(state["best_epoch"], 4)
        self.assertEqual(state["consecutive_non_improving_epochs"], 0)
        self.assertFalse(state["stop_already_reached"])


if __name__ == "__main__":
    unittest.main()
