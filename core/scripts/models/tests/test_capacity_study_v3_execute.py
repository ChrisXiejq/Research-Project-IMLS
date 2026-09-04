#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import json
import sys
import tempfile
import unittest
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(MODELS_DIR / "experimental"))

from capacity_study_v3_execute import (  # noqa: E402
    audit_training,
    completion_is_valid,
    training_plan,
    unique_training_specs,
)
from capacity_study_v3_runs import run_manifest  # noqa: E402
from capacity_study_v3_protocol import PROTOCOL_PATH, sha256_file, sha256_payload  # noqa: E402
from train_prediction_model_v3 import artifact_hash, source_hashes  # noqa: E402


class CapacityStudyV3ExecuteTests(unittest.TestCase):
    def test_plan_is_exact_and_resume_is_completion_marker_driven(self) -> None:
        manifest = run_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest_path = root / "runs.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            base_path = root / "base"
            base_path.mkdir()
            (base_path / "saved_model.pb").write_bytes(b"base")
            anchors_path = root / "anchors.npy"
            anchors_path.write_bytes(b"anchors")
            plan = training_plan(
                manifest,
                manifest_path=manifest_path,
                merged_dir=root / "data",
                base_model=base_path,
                anchors=anchors_path,
                output_root=root / "runs",
                python_bin="python-server",
                trainer=root / "trainer.py",
            )
            self.assertEqual(plan["planned_unique_runs"], 270)
            self.assertEqual(plan["core_runs"], 189)
            self.assertEqual(plan["additional_fraction_runs"], 81)
            self.assertEqual(plan["pending_runs"], 270)
            self.assertEqual(len({row["command"] for row in plan["jobs"]}), 270)

            spec = unique_training_specs(manifest)[0]
            completion = root / "runs" / spec["run_id"] / "TRAINING_COMPLETE.json"
            completion.parent.mkdir(parents=True)
            model_dir = completion.parent / "best_model"
            model_dir.mkdir()
            (model_dir / "saved_model.pb").write_bytes(b"model")
            history_path = completion.parent / "history.csv"
            history_path.write_text("epoch,val_loss\n0,1.0\n", encoding="utf-8")
            best_weights = completion.parent / "best.weights.h5"
            best_weights.write_bytes(b"weights")
            training_start = completion.parent / "training_start.json"
            start_payload = {"status": "recorded"}
            start_payload["record_sha256"] = sha256_payload(start_payload)
            training_start.write_text(json.dumps(start_payload), encoding="utf-8")
            data_integrity = completion.parent / "training_data_integrity.json"
            integrity_payload = {
                "status": "pass",
                "formal_mode": True,
                "hard_failures": [],
                "train_validation_group_overlap": [],
                "train_validation_sample_overlap_count": 0,
            }
            integrity_payload["audit_sha256"] = sha256_payload(integrity_payload)
            data_integrity.write_text(
                json.dumps(integrity_payload), encoding="utf-8"
            )
            training_health = completion.parent / "training_health.json"
            health_payload = {
                "status": "pass",
                "hard_checks_pass": True,
                "formal_run": True,
                "optimizer": {
                    "name": "adamw",
                    "weight_decay": 1.0e-5,
                    "gradient_clip_norm": 10.0,
                },
            }
            health_payload["health_sha256"] = sha256_payload(health_payload)
            training_health.write_text(
                json.dumps(health_payload),
                encoding="utf-8",
            )
            data_dir = root / "data"
            data_dir.mkdir()
            for name in (
                "train.jsonl",
                "val.jsonl",
                "DAY7_COMPLETE.json",
                "DAY7_MODEL_IMPLEMENTATION_COMPLETE.json",
            ):
                (data_dir / name).write_text(name, encoding="utf-8")
            data_hashes = {
                "train_jsonl": sha256_file(data_dir / "train.jsonl"),
                "val_jsonl": sha256_file(data_dir / "val.jsonl"),
                "day7_complete": sha256_file(data_dir / "DAY7_COMPLETE.json"),
                "model_implementation_complete": sha256_file(
                    data_dir / "DAY7_MODEL_IMPLEMENTATION_COMPLETE.json"
                ),
                "interaction_normalization_train": None,
            }
            config_path = completion.parent / "run_config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "merged_dir": str(data_dir),
                        "dataset_artifact_sha256": data_hashes,
                        "max_train_samples": None,
                        "max_val_samples": None,
                        "optimization": {
                            "optimizer": "adamw",
                            "weight_decay": 1.0e-5,
                            "gradient_clip_norm": 10.0,
                            "encoder_dropout": 0.1,
                            "early_stopping_patience": 12,
                            "checkpoint_metric": "validation_rollout_macro_trajectory_mixture_NLL_per_step",
                        },
                        "source_sha256": source_hashes(),
                        "protocol_sha256": sha256_file(PROTOCOL_PATH),
                        "run_manifest": str(manifest_path),
                        "run_manifest_sha256": sha256_file(manifest_path),
                        "anchors": str(anchors_path),
                        "anchors_sha256": sha256_file(anchors_path),
                        "base_model": str(base_path),
                        "base_model_artifact": artifact_hash(base_path),
                    }
                ),
                encoding="utf-8",
            )
            completion.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "formal_run": True,
                        **{key: spec[key] for key in (
                            "run_id", "model_cell_id", "family", "capacity_tier",
                            "history_horizon_s", "learning_rate", "seed",
                            "data_fraction", "train_groups",
                        )},
                        "checkpoint_selection_metric": "validation_rollout_macro_trajectory_mixture_NLL_per_step",
                        "best_model": artifact_hash(model_dir),
                        "best_weights": artifact_hash(best_weights),
                        "history_csv": artifact_hash(history_path),
                        "run_config": artifact_hash(config_path),
                        "training_start": artifact_hash(training_start),
                        "training_data_integrity": artifact_hash(data_integrity),
                        "training_health": artifact_hash(training_health),
                        "dataset_artifact_sha256": data_hashes,
                        "parameters": {"trainable_parameters": 1},
                    }
                ),
                encoding="utf-8",
            )
            resumed = training_plan(
                manifest,
                manifest_path=manifest_path,
                merged_dir=root / "data",
                base_model=base_path,
                anchors=anchors_path,
                output_root=root / "runs",
                python_bin="python-server",
                trainer=root / "trainer.py",
            )
            self.assertEqual(resumed["complete_runs"], 1)
            self.assertEqual(resumed["pending_runs"], 269)
            self.assertEqual(audit_training(manifest, root / "runs")["status"], "incomplete")
            payload = json.loads(completion.read_text(encoding="utf-8"))
            payload["formal_run"] = False
            completion.write_text(json.dumps(payload), encoding="utf-8")
            self.assertFalse(completion_is_valid(completion, spec))


if __name__ == "__main__":
    unittest.main()
