#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


MODELS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = MODELS_DIR.parent
sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from audit_r3_corrected_matrix import CORRECTED, MODE_MAP, debug_audit
from postcarla_trajectory_gate import (
    _fixed_conflict_points_from_debug,
    _fixed_geometry_yield_rule,
)


class R3CorrectedGateTest(unittest.TestCase):
    def test_route_geometry_is_stable_and_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rows = [
                {
                    "yield_stop_supervisor": {
                        "conflict_point": [10.0, 0.0],
                        "target_conflict_point": [10.0, 0.1],
                    }
                },
                {
                    "yield_stop_supervisor": {
                        "conflict_point": [10.0, 0.0],
                        "target_conflict_point": [10.0, 0.1],
                    }
                },
            ]
            (root / "smpc_debug_steps.jsonl").write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
            points = _fixed_conflict_points_from_debug(str(root))
            self.assertEqual(points, ((10.0, 0.0), (10.0, 0.1)))
            ego = {"state_trajectory": np.asarray([[0.0, 0.0, 0.0, 0.0], [2.0, 10.0, 0.0, 0.0]])}
            target = {"state_trajectory": np.asarray([[0.0, 10.0, -10.0, 0.0], [1.0, 10.0, 0.1, 0.0], [2.0, 10.0, 10.0, 0.0]])}
            rule = _fixed_geometry_yield_rule("target_2", ego, target, points, 1.0, 0.2)
            self.assertEqual(rule.geometry_source, "controller_route_projection")
            self.assertTrue(rule.target_clears_before_ego_enters)

    def test_route_geometry_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "smpc_debug_steps.jsonl").write_text(
                json.dumps({"yield_stop_supervisor": {"conflict_point": [1, 2], "target_conflict_point": [3, 4]}})
                + "\n"
                + json.dumps({"yield_stop_supervisor": {"conflict_point": [2, 2], "target_conflict_point": [3, 4]}})
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                _fixed_conflict_points_from_debug(str(root))

    def test_corrected_debug_audit_requires_three_distinct_consumed_modes(self) -> None:
        summary = {"finite_frac": 1.0, "nan_count": 0}
        joint_modes = []
        for mode in range(3):
            joint_modes.append(
                {
                    "joint_mode_index": mode,
                    "per_vehicle": [
                        {
                            "vehicle_index": 0,
                            "spatial_mode_index": mode,
                            "mean_sha256": f"{mode + 1:064x}",
                            "covariance_sha256": f"{mode + 11:064x}",
                        }
                    ],
                }
            )
        row = {
            "prediction_valid": [True],
            "prediction": {
                "mode_probs": summary,
                "mus": summary,
                "sigmas": summary,
                "mode_consumption": {
                    "implementation_version": CORRECTED,
                    "mapping": MODE_MAP,
                    "joint_modes": joint_modes,
                },
            },
            "yield_stop_supervisor": {},
            "solver": {"optimal": True},
            "solver_problem": {},
            "applied": {
                "u0": [0.0, 0.0],
                "u_control": [0.0, 0.0],
                "v_des": [1.0],
                "control_prev_after": [0.0, 0.0],
                "solve_time": 0.05,
            },
        }
        failures, stats = debug_audit([row], 0.5)
        self.assertEqual(failures, [])
        self.assertEqual(stats["distinct_consumed_mode_steps"], 1)
        row["prediction"]["mode_consumption"]["joint_modes"][2]["per_vehicle"][0]["mean_sha256"] = f"{1:064x}"
        failures, _ = debug_audit([row], 0.5)
        self.assertIn("collapsed_consumed_modes", failures)


if __name__ == "__main__":
    unittest.main()
