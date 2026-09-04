
import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))
import json
import pickle
import tempfile
import unittest
from pathlib import Path

import numpy as np

from core.scripts.models.experimental.prepare_r3_integrity_recovery import (
    EXPECTED_CELL_ID,
    EXPECTED_INTEGRITY_FAILURES,
    apply_recovery,
    build_recovery_plan,
    read_json,
    sha256,
)


class R3IntegrityRecoveryTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> None:
        peer_cells = [f"peer_{index:02d}" for index in range(15)]
        cells = peer_cells + [EXPECTED_CELL_ID]
        evaluations = []
        scenario_name = "scenario_uk_give_way_ego_init_103_smpc_fixed_risk"

        for index, cell_id in enumerate(cells):
            cell_dir = root / cell_id
            cell_dir.mkdir(parents=True)
            candidate = cell_id == EXPECTED_CELL_ID
            ego_x = 14.25593 if candidate else 14.72814 + index * 1e-6
            target_x = 43.08658 + index * 1e-6
            gate = {
                "evaluations": [
                    {
                        "scenario_dir": str(cell_dir / scenario_name),
                        "fixed_geometry_yield_rules": [
                            {
                                "geometry_source": "controller_route_projection",
                                "ego_conflict_point_xy": (
                                    [28.63957, 3.64148]
                                    if candidate
                                    else [28.884879, 4.036249]
                                ),
                                "target_conflict_point_xy": (
                                    [28.63957, 3.69977]
                                    if candidate
                                    else [28.884884, 3.69978 + index * 1e-7]
                                ),
                            }
                        ],
                    }
                ]
            }
            (cell_dir / "postcarla_trajectory_gate.json").write_text(
                json.dumps(gate), encoding="utf-8"
            )

            receipt_hash = None
            if candidate:
                for init_id in (101, 102, 103, 104, 105):
                    name = f"scenario_uk_give_way_ego_init_{init_id}_smpc_fixed_risk"
                    scenario_dir = cell_dir / name
                    scenario_dir.mkdir()
                    (cell_dir / "_attempts" / f"init_{init_id}").mkdir(parents=True)
                    receipt = {
                        "status": "pass",
                        "cell_id": cell_id,
                        "ego_init_id": init_id,
                        "scenario_dir": name,
                        "raw_evidence_sha256": f"raw-{init_id}",
                    }
                    receipt_path = cell_dir / f"R3_ROLLOUT_{init_id}_COMPLETE.json"
                    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                    if init_id == 103:
                        with (scenario_dir / "scenario_result.pkl").open("wb") as handle:
                            pickle.dump(
                                {
                                    "ego_3": {
                                        "state_trajectory": np.asarray(
                                            [
                                                [1.0, 14.25593, -3.25, 0.0, 9.5461],
                                                [1.05, 14.72815, -3.25, 0.0, 9.37659],
                                            ]
                                        )
                                    }
                                },
                                handle,
                            )
                        receipt_hash = sha256(receipt_path)

            rollout = {
                "scenario": scenario_name,
                "ego_init_id": 103,
                "status": "pass",
                "integrity_status": "pass",
                "failures": [],
                "attempt_provenance": {"receipt_sha256": receipt_hash},
                "control_variables": {
                    "first_states_txyyawspeed": {
                        "ego": [1.0, ego_x, -3.25, 0.0, 9.5461 if candidate else 9.37659],
                        "target": [1.0, target_x, 3.7, -3.14157, 8.66563],
                    }
                },
            }
            evaluations.append({"cell_id": cell_id, "rollouts": [rollout]})

        audit = {
            "status": "fail",
            "integrity_status": "fail",
            "observed_rollouts": 80,
            "passing_integrity_rollouts": 80,
            "integrity_failures": sorted(EXPECTED_INTEGRITY_FAILURES),
            "evaluations": evaluations,
        }
        (root / "r3_corrected_matrix_audit.json").write_text(
            json.dumps(audit), encoding="utf-8"
        )
        candidate_receipt = root / EXPECTED_CELL_ID / "R3_ROLLOUT_103_COMPLETE.json"
        previous_entries = [
            {
                "cell_id": EXPECTED_CELL_ID,
                "ego_init_id": 103,
                "receipt_sha256": sha256(candidate_receipt),
                "raw_evidence_sha256": "raw-103",
            }
        ] + [
            {
                "cell_id": f"old_{index:02d}",
                "ego_init_id": 101,
                "receipt_sha256": f"receipt-{index}",
                "raw_evidence_sha256": f"raw-{index}",
            }
            for index in range(79)
        ]
        previous_raw_marker = {
            "status": "pass",
            "accepted_rollouts": 80,
            "receipt_manifest_sha256": "old-manifest",
            "entries": previous_entries,
        }
        (root / "R3_RAW_COLLECTION_COMPLETE.json").write_text(
            json.dumps(previous_raw_marker), encoding="utf-8"
        )
        (root / "r3_offline_finalization_provenance.json").write_text(
            "{}", encoding="utf-8"
        )

    def test_exact_one_tick_signature_is_prepared_and_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_fixture(root)
            plan = build_recovery_plan(root)
            self.assertEqual(plan["cell_id"], EXPECTED_CELL_ID)
            self.assertEqual(plan["ego_init_id"], 103)
            self.assertGreater(plan["diagnostics"]["candidate_first_xy_offset_m"], 0.25)
            self.assertLess(
                plan["diagnostics"][
                    "candidate_second_state_max_abs_deviation_from_peer_first_state"
                ],
                0.1,
            )

            marker_path = apply_recovery(root, plan)
            marker = read_json(marker_path)
            self.assertEqual(marker["status"], "prepared")
            cell_dir = root / EXPECTED_CELL_ID
            self.assertFalse((cell_dir / "R3_ROLLOUT_103_COMPLETE.json").exists())
            self.assertFalse((cell_dir / "_attempts" / "init_103").exists())
            for init_id in (101, 102, 104, 105):
                self.assertTrue((cell_dir / f"R3_ROLLOUT_{init_id}_COMPLETE.json").is_file())
                self.assertTrue((cell_dir / "_attempts" / f"init_{init_id}").is_dir())
            quarantine = root / marker["quarantine"] / "quarantined_cell"
            self.assertTrue((quarantine / "R3_ROLLOUT_103_COMPLETE.json").is_file())
            self.assertTrue(
                (
                    root
                    / marker["quarantine"]
                    / "root_derived_before_recovery"
                    / "r3_corrected_matrix_audit.json"
                ).is_file()
            )

            # A repeated --apply after interruption/completion is idempotent.
            second_marker = apply_recovery(root, marker)
            self.assertEqual(second_marker, marker_path)

    def test_unexpected_failure_scope_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_fixture(root)
            audit_path = root / "r3_corrected_matrix_audit.json"
            audit = read_json(audit_path)
            audit["integrity_failures"].append("matrix:unexpected")
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "exact two init103"):
                build_recovery_plan(root)


if __name__ == "__main__":
    unittest.main()
