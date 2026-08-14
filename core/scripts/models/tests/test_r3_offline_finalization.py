#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pickle
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

# The desktop test runtime intentionally ships a compact numerical stack.  The
# compatibility path exercised below does not call Hausdorff distance, so
# provide only the import surface needed by the historical metrics module when
# SciPy is absent.  The server finalizer still uses the real carla_modern SciPy.
try:
    import scipy.spatial.distance  # type: ignore  # noqa: F401
except ImportError:
    scipy_module = types.ModuleType("scipy")
    spatial_module = types.ModuleType("scipy.spatial")
    distance_module = types.ModuleType("scipy.spatial.distance")
    distance_module.directed_hausdorff = lambda *_args, **_kwargs: (0.0, 0, 0)
    spatial_module.distance = distance_module
    scipy_module.spatial = spatial_module
    sys.modules.setdefault("scipy", scipy_module)
    sys.modules.setdefault("scipy.spatial", spatial_module)
    sys.modules.setdefault("scipy.spatial.distance", distance_module)


MODELS_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = MODELS_DIR.parents[2]
sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(REPO_DIR))

import finalize_r3_offline as finalizer  # noqa: E402
from core.scripts.evaluation.closed_loop_metrics import load_scenario_result  # noqa: E402
from r3_attempt_manager import (  # noqa: E402
    RAW_REQUIRED_JSON,
    RAW_REQUIRED_JSONL,
    raw_evidence_sha256,
    refresh_ledger,
    write_receipt,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def trajectory_payload() -> dict:
    return {
        "state_trajectory": np.asarray(
            [[0.0, 0.0, 0.0, 0.0, 1.0], [0.1, 0.1, 0.0, 0.0, 1.0]],
            dtype=float,
        ),
        "input_trajectory": np.zeros((2, 2), dtype=float),
        "feasibility": np.ones(2, dtype=float),
        "solve_times": np.asarray([0.01, 0.01], dtype=float),
        "l_f": 1.2,
        "l_r": 1.3,
        "collision_probs": np.zeros(2, dtype=float),
        "actor_geometry": {
            "schema_version": "carla_spawned_actor_geometry_v1",
            "length_m": 4.5,
            "width_m": 1.8,
        },
    }


class ClosedLoopCompatibilityTest(unittest.TestCase):
    def test_appended_actor_geometry_is_ignored_without_mutating_raw_pickle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scenario_result.pkl"
            with path.open("wb") as handle:
                pickle.dump(
                    {"ego_0": trajectory_payload(), "target_2": trajectory_payload()},
                    handle,
                )
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            result = load_scenario_result(path)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(result.ego_closed_loop_trajectory.N, 2)
            self.assertEqual(len(result.tv_closed_loop_trajectories), 1)
            self.assertEqual(before, after)

    def test_unknown_nontelemetry_field_is_not_silently_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "scenario_result.pkl"
            payload = trajectory_payload()
            payload["misspelled_metric_input"] = 1
            with path.open("wb") as handle:
                pickle.dump({"ego_0": payload}, handle)
            with self.assertRaisesRegex(TypeError, "misspelled_metric_input"):
                load_scenario_result(path)


class OfflineFinalizerGuardTest(unittest.TestCase):
    def test_progress_requires_complete_quiescent_raw_collection(self) -> None:
        valid = {
            "expected_rollouts": 80,
            "accepted_rollouts": 80,
            "pending_rollouts": 0,
            "current_or_interrupted_attempts": [],
        }
        finalizer.validate_progress(valid)
        for field, value in (
            ("accepted_rollouts", 79),
            ("pending_rollouts", 1),
            ("current_or_interrupted_attempts", [{"attempt": 1}]),
        ):
            invalid = dict(valid)
            invalid[field] = value
            with self.assertRaises(RuntimeError):
                finalizer.validate_progress(invalid)

    def test_raw_marker_reverifies_receipt_and_records_no_new_rollout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cell_id = "B1_fixed_medium_assertive"
            init_id = 101
            cell = root / cell_id
            scenario = cell / f"scenario_uk_give_way_ego_init_{init_id}_smpc_fixed_risk"
            for relative in RAW_REQUIRED_JSON:
                payload = {"status": "pass"}
                if relative == "scenario_run_summary.json":
                    payload = {"ran_successfully": True}
                write_json(scenario / relative, payload)
            for relative in RAW_REQUIRED_JSONL:
                path = scenario / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            with (scenario / "scenario_result.pkl").open("wb") as handle:
                pickle.dump({"ego_0": trajectory_payload()}, handle)
            (scenario / "scenario_steps.csv").write_text("step,value\n0,1\n", encoding="utf-8")
            attempt = cell / "_attempts" / f"init_{init_id}" / "attempt_001"
            started = attempt / "attempt_started.json"
            record = attempt / "attempt_record.json"
            write_json(
                started,
                {"attempt": 1, "cell_id": cell_id, "ego_init_id": init_id},
            )
            write_json(
                record,
                {
                    "attempt": 1,
                    "cell_id": cell_id,
                    "ego_init_id": init_id,
                    "accepted": True,
                    "classification": "accepted",
                    "retry_allowed": False,
                    "raw_evidence_sha256_before_promotion": raw_evidence_sha256(
                        scenario
                    ),
                },
            )
            ledger = refresh_ledger(cell, cell_id, init_id, max_attempts=3)
            write_receipt(
                cell_dir=cell,
                cell_id=cell_id,
                init_id=init_id,
                scenario_dir=scenario,
                attempt_number=1,
                record_path=record,
                ledger_path=ledger,
                recovery=False,
            )
            contract = {
                "git_commit": "a" * 40,
                "execution_order": [{"cell_id": cell_id, "ego_init_id": init_id}],
            }
            progress = {"failed_attempts": 2}
            with mock.patch.object(finalizer, "EXPECTED_ROLLOUTS", 1):
                marker = finalizer.raw_collection_marker(root, contract, progress)
            self.assertEqual(marker["accepted_rollouts"], 1)
            self.assertEqual(marker["scientific_rollouts_launched_by_offline_finalizer"], 0)
            self.assertEqual(marker["failed_infrastructure_attempts_retained"], 2)

    def test_source_manifest_allows_only_declared_loader_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            loader = repo / "core/scripts/evaluation/closed_loop_metrics.py"
            other = repo / "core/scripts/models/audit_r3_corrected_matrix.py"
            loader.parent.mkdir(parents=True)
            other.parent.mkdir(parents=True)
            loader.write_text("collection loader\n", encoding="utf-8")
            other.write_text("frozen audit\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(repo), "config", "user.name", "R3 Test"], check=True)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "collection"], check=True)
            collection_commit = subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
            ).strip()
            manifest = {
                "status": "pass",
                "tracked_worktree_clean": True,
                "git_commit": collection_commit,
                "critical_sources": {
                    loader.relative_to(repo).as_posix(): {
                        "sha256": hashlib.sha256(loader.read_bytes()).hexdigest()
                    },
                    other.relative_to(repo).as_posix(): {
                        "sha256": hashlib.sha256(other.read_bytes()).hexdigest()
                    },
                },
            }
            loader.write_text("compatible loader\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "compatibility"], check=True)
            current, drift = finalizer.verify_original_source_manifest(
                repo, {"git_commit": collection_commit}, manifest
            )
            self.assertNotEqual(current, collection_commit)
            self.assertEqual([item["path"] for item in drift], [loader.relative_to(repo).as_posix()])

            other.write_text("prohibited audit drift\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "commit", "-qm", "bad drift"], check=True)
            with self.assertRaises(RuntimeError):
                finalizer.verify_original_source_manifest(
                    repo, {"git_commit": collection_commit}, manifest
                )


if __name__ == "__main__":
    unittest.main()
