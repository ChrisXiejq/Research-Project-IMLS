from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class UniformEpochOverrideTest(unittest.TestCase):
    def test_extension_preserves_frozen_manifest_epoch_budget(self) -> None:
        models_dir = Path(__file__).resolve().parents[1]
        code = r"""
import json

import capacity_study_v3_protocol as protocol
import train_thesis_core_cached_v4e_120 as wrapper
from thesis_core_v3_runs import thesis_core_manifest, validate_thesis_core_manifest

manifest = thesis_core_manifest()
audit = validate_thesis_core_manifest(manifest)
callback = wrapper.trainer.HistoryRestoredEarlyStopping(
    [3.0, 2.0, 2.1, 2.2, 2.3]
)
callback.on_train_begin()
print("V4E_CONTRACT=" + json.dumps({
    "protocol_epochs": protocol.CORE_EPOCHS,
    "trainer_epochs": wrapper.trainer.CORE_EPOCHS,
    "manifest_epochs": sorted({row["epochs"] for row in manifest["runs"]}),
    "planned_runs": audit["planned_runs"],
    "restored_best": callback.best,
    "restored_wait": callback.wait,
}, sort_keys=True))
"""
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(models_dir)
        completed = subprocess.run(
            [sys.executable, "-c", code],
            cwd=models_dir,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        line = next(
            value
            for value in completed.stdout.splitlines()
            if value.startswith("V4E_CONTRACT=")
        )
        payload = json.loads(line.split("=", 1)[1])
        self.assertEqual(payload["protocol_epochs"], 80)
        self.assertEqual(payload["trainer_epochs"], 120)
        self.assertEqual(payload["manifest_epochs"], [80])
        self.assertEqual(payload["planned_runs"], 27)
        self.assertEqual(payload["restored_best"], 2.0)
        self.assertEqual(payload["restored_wait"], 3)


if __name__ == "__main__":
    unittest.main()
