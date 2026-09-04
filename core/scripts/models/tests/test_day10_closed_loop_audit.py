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
import hashlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from audit_day10_closed_loop import preflight_semantics, semantic_sha256


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


class Day10AuditTest(unittest.TestCase):
    def test_complete_heldout_matrix(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            normalization = {
                "interaction": "not_applicable_for_two_input_B1",
                "past_states_local": "no explicit normalization",
                "raster": "tensorflow.keras.applications.resnet.preprocess_input",
            }
            cells = []
            for predictor in ("B1", "B0"):
                for policy in (
                    "fixed_aggressive",
                    "fixed_medium",
                    "fixed_conservative",
                    "adaptive",
                ):
                    for style in ("assertive", "reactive"):
                        cell_id = f"{predictor}_{policy}_{style}"
                        cell = {
                            "cell_id": cell_id,
                            "predictor": predictor,
                            "risk_policy": policy,
                            "target_style": style,
                        }
                        cells.append(cell)
                        gate_evaluations = []
                        for init_id in range(46, 51):
                            policy_name = "smpc_var_risk" if policy == "adaptive" else "smpc_fixed_risk"
                            scenario = (
                                root
                                / cell_id
                                / f"scenario_uk_give_way_ego_init_{init_id}_{policy_name}"
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
                                    "warmup_passed": True,
                                    "model_artifact": {
                                        "sha256_tree": "b1hash" if predictor == "B1" else "b0hash"
                                    },
                                    "anchors_artifact": {"sha256": "anchorhash"},
                                    "normalization": normalization,
                                    **calibration,
                                },
                            )
                            write_json(
                                scenario / "smpc_debug_setup.json",
                                {
                                    "risk_profile": (
                                        "adaptive_interaction_severity"
                                        if policy == "adaptive"
                                        else f"fixed_frontier_{policy.removeprefix('fixed_')}"
                                    ),
                                    "fixed_risk": policy != "adaptive",
                                    "yield_stop_supervisor": {
                                        "risk_owned_yield_enabled": 1,
                                        "planner_ownership_stress_enabled": 1,
                                        "mode": "reduced_intervention",
                                    },
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
                                                "adaptive_variable"
                                                if policy == "adaptive"
                                                else "fixed_static"
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
                                        "ego_init_id": init_id,
                                        "cell_id": cell_id,
                                        "ego_policy": policy,
                                        "protocol_id": "day10_a3_heldout_closed_loop_v1",
                                        "git_commit": "fixturecommit",
                                        "target_style": (
                                            "defensive_reactive"
                                            if style == "reactive"
                                            else "assertive_constant_speed"
                                        ),
                                        "target_start_offset_m": 0.0,
                                        "target_speed_mps": 9.0,
                                        "target_style_parameters": (
                                            {
                                                "caution_speed_mps": 4.5,
                                                "minimum_speed_mps": 2.5,
                                            }
                                            if style == "reactive"
                                            else {"nominal_speed_mps": 9.0}
                                        ),
                                        "mode_probabilities": [1.0],
                                        "pred_sigmas_world": [[[1.0, 0.0], [0.0, 1.0]]],
                                        "target_reactive_diagnostics": {
                                            "active": style == "reactive"
                                        },
                                    }
                                ],
                            )
                            gate_evaluations.append(
                                {
                                    "scenario_dir": str(scenario),
                                    "status": "PASS",
                                    "solver_failure_frac": 0.0,
                                }
                            )
                        write_json(
                            root / cell_id / "postcarla_trajectory_gate.json",
                            {"overall_status": "PASS", "evaluations": gate_evaluations},
                        )
            tuning_path = root / "tuning_day10_frozen.json"
            preflight_path = root / "day10_deployment_preflight.json"
            write_json(tuning_path, {"fixture": "tuning"})
            write_json(preflight_path, {"status": "pass"})
            contract = {
                "status": "frozen",
                "cells": cells,
                "ego_init_ids": list(range(46, 51)),
                "expected_rollouts": 80,
                "target_offset_m": 0.0,
                "target_speed_mps": 9.0,
                "git_commit": "fixturecommit",
                "execution_git_commits": ["oldfixturecommit", "fixturecommit"],
                "reactive_parameters": {
                    "caution_speed_mps": 4.5,
                    "minimum_speed_mps": 2.5,
                },
                "tuning_sha256": hashlib.sha256(tuning_path.read_bytes()).hexdigest(),
                "preflight_semantic_sha256": semantic_sha256(
                    preflight_semantics(json.loads(preflight_path.read_text()))
                ),
                "anchors_sha256": "anchorhash",
                "normalization": normalization,
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
            contract_path = root / "day10_run_contract.json"
            output = root / "day10_closed_loop_audit.json"
            write_json(contract_path, contract)
            write_json(
                root / "day10_contract_resume_provenance.json",
                {
                    "status": "pass",
                    "allowed_execution_git_commits": [
                        "oldfixturecommit",
                        "fixturecommit",
                    ],
                },
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "experimental/audit_day10_closed_loop.py"),
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
            self.assertEqual(audit["observed_cells"], 16)
            self.assertEqual(audit["observed_rollouts"], 80)


if __name__ == "__main__":
    unittest.main()
