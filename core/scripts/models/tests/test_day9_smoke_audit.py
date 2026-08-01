#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class Day9AuditTest(unittest.TestCase):
    def test_legacy_boolean_solver_failure_is_recognized(self) -> None:
        from core.scripts.models.audit_day9_smoke import solver_failed

        self.assertTrue(solver_failed({"optimal": False}))
        self.assertTrue(solver_failed({"optimal": 0}))
        self.assertTrue(solver_failed({"exception": "fixture"}))
        self.assertFalse(solver_failed({"optimal": True}))
        self.assertFalse(solver_failed({"optimal": 1}))

    def test_eight_arm_prediction_control_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            arms = []
            for predictor in ("B1", "B0"):
                for policy in ("fixed_medium", "adaptive"):
                    for style in ("assertive", "reactive"):
                        arm_id = f"{predictor}_{policy}_{style}"
                        arm = {
                            "arm_id": arm_id,
                            "predictor": predictor,
                            "risk_policy": policy,
                            "target_style": style,
                        }
                        arms.append(arm)
                        arm_dir = root / arm_id
                        scenario = arm_dir / "scenario_fixture"
                        write_json(
                            arm_dir / "postcarla_trajectory_gate.json",
                            {
                                "overall_status": "PASS",
                                "evaluations": [{"solver_failure_frac": 0.0}],
                            },
                        )
                        write_json(scenario / "scenario_run_summary.json", {"ran_successfully": True})
                        calibration = (
                            {
                                "calibration_source": "/fixture/calibration.json",
                                "calibration_artifact": {"sha256": "calhash"},
                                "calibration_fit_split": "val",
                                "calibration_parameters": {
                                    "temperature": 1.25,
                                    "covariance_scale": 0.01,
                                },
                            }
                            if predictor == "B1"
                            else {
                                "calibration_source": None,
                                "calibration_artifact": None,
                                "calibration_fit_split": None,
                                "calibration_parameters": {
                                    "temperature": 1.0,
                                    "covariance_scale": 1.0,
                                },
                            }
                        )
                        write_json(
                            scenario / "prediction_deployment_manifest.json",
                            {
                                "status": "pass",
                                # Existing Day 9 CARLA artifacts contain legacy integer 1
                                # because bool was checked after int during JSON conversion.
                                "warmup_passed": 1,
                                "model_artifact": {
                                    "sha256_tree": "b1hash" if predictor == "B1" else "b0hash"
                                },
                                **calibration,
                            },
                        )
                        summary = {"finite_frac": 1.0, "nan_count": 0}
                        write_jsonl(
                            scenario / "smpc_debug_steps.jsonl",
                            [
                                {
                                    "solver": {"optimal": True},
                                    "prediction_valid": [True],
                                    "prediction": {
                                        "mode_probs": summary,
                                        "mus": summary,
                                        "sigmas": summary,
                                    },
                                    "risk": {
                                        "solver_risk_mode": (
                                            "adaptive_variable" if policy == "adaptive" else "fixed_static"
                                        )
                                    },
                                    "yield_stop_supervisor": {"active": False},
                                }
                            ],
                        )
                        write_jsonl(
                            scenario / "prediction_dataset" / "prediction_dataset_raw.jsonl",
                            [
                                {
                                    "mode_probabilities": [0.5, 0.5],
                                    "pred_sigmas_world": [
                                        [[[1.0, 0.0], [0.0, 1.0]]],
                                        [[[2.0, 0.0], [0.0, 2.0]]],
                                    ],
                                    "target_reactive_diagnostics": {
                                        "active": style == "reactive"
                                    },
                                }
                            ],
                        )
            contract = {
                "status": "frozen",
                "arms": arms,
                "predictors": {
                    "B1": {
                        "model_sha256_tree": "b1hash",
                        "calibration_sha256": "calhash",
                        "calibration_parameters": {
                            "temperature": 1.25,
                            "covariance_scale": 0.01,
                        },
                    },
                    "B0": {"model_sha256_tree": "b0hash"},
                },
            }
            contract_path = root / "day9_run_contract.json"
            write_json(contract_path, contract)
            output = root / "day9_smoke_audit.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "audit_day9_smoke.py"),
                    "--results-dir",
                    str(root),
                    "--contract-json",
                    str(contract_path),
                    "--output-json",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            audit = json.loads(output.read_text())
            self.assertEqual(audit["status"], "pass")
            self.assertEqual(audit["observed_arms"], 8)
            self.assertTrue(all(item["status"] == "pass" for item in audit["evaluations"]))

            write_json(root / "day9_deployment_preflight.json", {"status": "pass"})
            environment = os.environ.copy()
            environment.update({"DAY9_RESULTS": str(root), "PYTHON_BIN": sys.executable})
            subprocess.run(
                [
                    "bash",
                    str(
                        SCRIPT_DIR.parent
                        / "carla"
                        / "finalize_day9_deployment_smoke.sh"
                    ),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            complete = json.loads((root / "DAY9_COMPLETE.json").read_text())
            provenance = json.loads(
                (root / "day9_finalization_provenance.json").read_text()
            )
            self.assertEqual(complete["status"], "pass")
            self.assertEqual(complete["observed_arms"], 8)
            self.assertTrue(provenance["raw_rollouts_reused"])
            self.assertTrue((root / "day9_smoke_snapshot.tar.gz").is_file())


if __name__ == "__main__":
    unittest.main()
