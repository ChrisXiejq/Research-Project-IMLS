#!/usr/bin/env python3
"""End-to-end tests for Day 8 validation freeze and test reporting."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
VARIANTS = ("B1", "B2-M", "B2-D", "T1", "T2")
SEEDS = {"B1": 37, "B2-M": 37, "B2-D": 11, "T1": 23, "T2": 23}
SUBSETS = ("all", "assertive", "reactive", "pre_response", "response_active")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_artifact(path: Path) -> dict:
    files = sorted(item for item in path.rglob("*") if item.is_file())
    digest = hashlib.sha256()
    total = 0
    for item in files:
        digest.update(str(item.relative_to(path)).encode())
        digest.update(b"\0")
        digest.update(sha256(item).encode())
        total += item.stat().st_size
    return {
        "path": str(path),
        "files": len(files),
        "bytes": total,
        "sha256_tree": digest.hexdigest(),
    }


def metric_block(value: float) -> dict:
    return {
        "top1_ADE_mean": value,
        "top1_FDE_mean": value + 0.1,
        "trajectory_mixture_NLL_per_step_mean": value + 1.0,
        "rollout_aggregation": {
            "macro_mean": {"trajectory_mixture_NLL_per_step_mean": value + 1.0}
        },
        "probabilistic": {
            "coverage_mean_absolute_error": value / 10.0,
            "covariance_audit": {"invalid_matrices": 0},
        },
    }


class Day8FinalizationTest(unittest.TestCase):
    def test_freeze_test_summary_and_package_preserve_validation_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "day8"
            test_dir = root / "final_test_v1"
            ranking = []
            runs = []
            for rank, variant in enumerate(VARIANTS, start=1):
                seed = SEEDS[variant]
                run_dir = root / "runs" / variant / f"seed_{seed}"
                model_dir = run_dir / "best_model"
                model_dir.mkdir(parents=True)
                (model_dir / "saved_model.pb").write_bytes(f"{variant}-{seed}".encode())
                model = tree_artifact(model_dir)
                calibration = {
                    "fit_split": "val",
                    "parameters": {
                        "temperature": 1.0 + rank / 10,
                        "covariance_scale": 0.01,
                    },
                    "model_artifact": model,
                }
                write_json(run_dir / "calibration.json", calibration)
                write_json(run_dir / "TRAINING_COMPLETE.json", {"status": "pass"})
                ranking.append(
                    {
                        "variant": variant,
                        "representative_seed": seed,
                        "representative_rule": "fixture validation median",
                    }
                )
                runs.append(
                    {
                        "variant": variant,
                        "seed": seed,
                        "training": {"model_artifact": model},
                    }
                )
            summary = {
                "status": "pass",
                "observed_runs": 15,
                "test_accessed": False,
                "provisional_selected_variant": "B1",
                "provisional_representative_seed": 37,
                "variant_ranking": ranking,
                "runs": runs,
            }
            summary_path = root / "day8_validation_summary.json"
            write_json(summary_path, summary)
            write_json(
                root / "DAY8_VALIDATION_COMPLETE.json",
                {
                    "status": "pass",
                    "validation_summary_sha256": sha256(summary_path),
                },
            )
            selection_path = test_dir / "DAY8_MODEL_SELECTION_FROZEN.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "experimental/freeze_day8_model_selection.py"),
                    "--results-dir",
                    str(root),
                    "--output-json",
                    str(selection_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            selection = json.loads(selection_path.read_text())

            # Make T2 look best on test. It must still not replace validation-selected B1.
            for index, variant in enumerate(VARIANTS):
                seed = SEEDS[variant]
                frozen = selection["representatives_for_single_test_pass"][variant]
                calibration = json.loads(
                    (root / "runs" / variant / f"seed_{seed}" / "calibration.json").read_text()
                )
                value = float(len(VARIANTS) - index) / 10.0
                for subset in SUBSETS:
                    output = test_dir / variant / f"seed_{seed}" / f"test_{subset}.json"
                    base = {
                        "evaluation_schema_version": "multipath_accuracy_calibration_v2",
                        "split": "test",
                        "subset": subset,
                        "calibration_fit_uses_test": False,
                        "model_artifact": frozen["model"],
                        "calibration": calibration,
                    }
                    if subset == "pre_response":
                        base.update(
                            {
                                "status": "not_applicable",
                                "samples": 0,
                                "independent_rollouts": 0,
                                "independent_init_groups": 0,
                                "reason": "fixture empty subset",
                            }
                        )
                    else:
                        samples, rollouts = {
                            "all": (10, 20),
                            "assertive": (4, 10),
                            "reactive": (6, 10),
                            "response_active": (3, 5),
                        }[subset]
                        base.update(
                            {
                                "status": "pass",
                                "samples": samples,
                                "independent_rollouts": rollouts,
                                "independent_init_groups": 5,
                                "latency": {"mean_prediction_ms_per_sample": 2.0},
                                "uncalibrated": metric_block(value),
                                "calibrated": metric_block(value - 0.01),
                            }
                        )
                    write_json(output, base)

            summary_output = test_dir / "day8_frozen_test_summary.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "experimental/summarize_day8_frozen_test.py"),
                    "--results-dir",
                    str(root),
                    "--test-dir",
                    str(test_dir),
                    "--selection-json",
                    str(selection_path),
                    "--output-json",
                    str(summary_output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            final = json.loads(summary_output.read_text())
            self.assertEqual(final["closed_loop_selected_variant"], "B1")
            self.assertEqual(final["test_ranking_for_reporting_only"][0]["variant"], "T2")
            self.assertFalse(final["test_used_for_selection"])

            write_json(test_dir / "DAY8_TEST_COMPLETE.json", {"status": "pass"})
            archive = test_dir / "day8_frozen_test_snapshot.tar.gz"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "experimental/package_day8_test_snapshot.py"),
                    "--test-dir",
                    str(test_dir),
                    "--output",
                    str(archive),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            with tarfile.open(archive, "r:gz") as packaged:
                self.assertEqual(len(packaged.getnames()), 28)


if __name__ == "__main__":
    unittest.main()
