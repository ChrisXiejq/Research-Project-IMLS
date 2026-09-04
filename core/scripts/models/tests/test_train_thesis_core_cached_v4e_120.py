from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class UniformEpochOverrideTest(unittest.TestCase):
    def test_public_pipeline_uses_external_model_paths(self) -> None:
        models_dir = Path(__file__).resolve().parents[1]
        source = (models_dir / "experimental/run_future_mask_v4e_pipeline.sh").read_text()
        self.assertNotIn("/root/autodl-tmp", source)
        self.assertIn('base_model="${MULTIPATH_BASE_MODEL:?', source)
        self.assertIn('anchors="${MULTIPATH_ANCHORS:-', source)
        self.assertIn('dataset="${PREDICTION_DATASET_ROOT:-', source)

    def test_modern_environment_does_not_install_mismatched_carla(self) -> None:
        repository = Path(__file__).resolve().parents[4]
        environment = (repository / "core/env_setup/environment.modern.yml").read_text()
        requirements = (repository / "core/env_setup/requirements.modern.txt").read_text()
        self.assertNotIn("carla==0.9.15", environment)
        self.assertNotIn("carla==0.9.15", requirements)

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
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(models_dir / "experimental"), str(models_dir))
        )
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
