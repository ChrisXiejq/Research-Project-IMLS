#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import contextlib
import io
import json
import pickle
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


MODELS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(MODELS_DIR / "experimental"))

from capture_r3_execution_provenance import assert_no_sensitive_text
from package_closed_loop_snapshot import (
    R3_REQUIRED_FROZEN_CONTRACTS,
    R3_REQUIRED_ROOT_FILES,
    build_snapshot,
    sha256,
    verify_snapshot,
)
from r3_attempt_manager import (
    command_finalize,
    command_prepare,
    command_verify,
    is_experiment_actor_type,
    stale_actor_records,
)
from summarize_r3_progress import build_summary


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def valid_scenario(root: Path, init_id: int = 101) -> Path:
    scenario = root / f"scenario_uk_give_way_ego_init_{init_id}_smpc_fixed_risk"
    write_json(scenario / "scenario_run_summary.json", {"ran_successfully": True, "extra": {}})
    write_json(scenario / "scenario_rollout_config.json", {"carla_params": {"fps": 20}})
    write_json(scenario / "smpc_debug_setup.json", {"status": "pass"})
    write_json(scenario / "prediction_deployment_manifest.json", {"status": "pass"})
    write_json(scenario / "prediction_dataset/prediction_dataset_config.json", {"enabled": True})
    write_json(scenario / "prediction_dataset/prediction_dataset_manifest.json", {"sample_count": 1})
    (scenario / "smpc_debug_steps.jsonl").write_text("{}\n", encoding="utf-8")
    (scenario / "prediction_dataset/prediction_dataset_raw.jsonl").write_text("{}\n", encoding="utf-8")
    (scenario / "prediction_dataset/prediction_dataset_labeled.jsonl").write_text("{}\n", encoding="utf-8")
    (scenario / "scenario_steps.csv").write_text("step,value\n0,1\n", encoding="utf-8")
    with (scenario / "scenario_result.pkl").open("wb") as handle:
        pickle.dump({"ego": {"state_trajectory": [[0.0, 0.0, 0.0]]}}, handle)
    return scenario


class FakeActor:
    def __init__(self, actor_id: int, type_id: str, role: str = "") -> None:
        self.id = actor_id
        self.type_id = type_id
        self.attributes = {"role_name": role}


class AttemptIsolationTest(unittest.TestCase):
    def args(self, cell: Path, **extra):
        values = {
            "cell_dir": cell,
            "cell_id": "B1_fixed_medium_assertive",
            "init_id": 101,
            "max_attempts": 3,
        }
        values.update(extra)
        return SimpleNamespace(**values)

    def test_success_is_promoted_and_receipt_survives_derived_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cell = Path(temporary) / "cell"
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(command_prepare(self.args(cell)), 0)
            prepared = json.loads(output.getvalue())
            attempt = Path(prepared["attempt_dir"])
            valid_scenario(attempt)
            (attempt / "runner_attempt.log").write_text("successful\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    command_finalize(self.args(cell, attempt_dir=attempt, exit_code=0)),
                    0,
                )
            canonical = next(cell.glob("scenario_*/scenario_run_summary.json")).parent
            receipt_path = cell / "R3_ROLLOUT_101_COMPLETE.json"
            self.assertTrue(receipt_path.is_file())
            receipt = json.loads(receipt_path.read_text())
            ledger_path = cell / receipt["attempt_ledger"]
            ledger_hash = receipt["attempt_ledger_sha256_at_receipt"]
            self.assertFalse(any(attempt.glob("scenario_*")))
            # Later post-processing may add derived files; immutable raw hashes
            # in the receipt must remain valid.
            write_json(canonical / "derived_postprocess.json", {"value": 1})
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(command_verify(self.args(cell)), 0)
            self.assertEqual(sha256(ledger_path), ledger_hash)

    def test_incomplete_zero_exit_is_not_promoted_or_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cell = Path(temporary) / "cell"
            with contextlib.redirect_stdout(io.StringIO()) as output:
                command_prepare(self.args(cell))
            attempt = Path(json.loads(output.getvalue())["attempt_dir"])
            scenario = valid_scenario(attempt)
            (scenario / "prediction_dataset/prediction_dataset_labeled.jsonl").unlink()
            (attempt / "runner_attempt.log").write_text("process returned zero\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as outcome:
                self.assertEqual(command_finalize(self.args(cell, attempt_dir=attempt, exit_code=0)), 5)
            self.assertEqual(json.loads(outcome.getvalue())["classification"], "integrity_failure_after_zero_exit")
            self.assertFalse(any(cell.glob("scenario_*")))
            with contextlib.redirect_stdout(io.StringIO()) as blocked:
                self.assertEqual(command_prepare(self.args(cell)), 5)
            self.assertEqual(json.loads(blocked.getvalue())["status"], "blocked_nonretryable")

    def test_known_infrastructure_failure_is_retryable_and_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cell = Path(temporary) / "cell"
            with contextlib.redirect_stdout(io.StringIO()) as output:
                command_prepare(self.args(cell))
            first = Path(json.loads(output.getvalue())["attempt_dir"])
            (first / "runner_attempt.log").write_text(
                "RuntimeError: Spawn failed because of collision at spawn position\n",
                encoding="utf-8",
            )
            with contextlib.redirect_stdout(io.StringIO()) as outcome:
                self.assertEqual(command_finalize(self.args(cell, attempt_dir=first, exit_code=1)), 0)
            self.assertTrue(json.loads(outcome.getvalue())["retry_allowed"])
            with contextlib.redirect_stdout(io.StringIO()) as output:
                command_prepare(self.args(cell))
            second = Path(json.loads(output.getvalue())["attempt_dir"])
            self.assertNotEqual(first, second)
            self.assertTrue((first / "attempt_record.json").is_file())

    def test_resume_recovers_successful_orphan_before_promotion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cell = Path(temporary) / "cell"
            with contextlib.redirect_stdout(io.StringIO()) as output:
                command_prepare(self.args(cell))
            attempt = Path(json.loads(output.getvalue())["attempt_dir"])
            valid_scenario(attempt)
            # Simulate power loss after CARLA completed all immutable raw files
            # but before finalize/promote wrote a terminal record.
            with contextlib.redirect_stdout(io.StringIO()) as resumed:
                self.assertEqual(command_prepare(self.args(cell)), 0)
            self.assertEqual(json.loads(resumed.getvalue())["status"], "complete")
            receipt = json.loads((cell / "R3_ROLLOUT_101_COMPLETE.json").read_text())
            record = json.loads((cell / receipt["attempt_record"]).read_text())
            self.assertTrue(receipt["recovered_after_interruption"])
            self.assertEqual(record["classification"], "accepted_recovered_before_promotion")
            self.assertEqual(
                sum(path.is_dir() for path in cell.glob("_attempts/init_101/attempt_*")),
                1,
            )

    def test_resume_recovers_atomic_promotion_before_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            cell = Path(temporary) / "cell"
            with contextlib.redirect_stdout(io.StringIO()) as output:
                command_prepare(self.args(cell))
            attempt = Path(json.loads(output.getvalue())["attempt_dir"])
            scenario = valid_scenario(attempt)
            # Simulate power loss immediately after the atomic os.replace that
            # promotes the accepted scenario, before record/ledger/receipt.
            scenario.rename(cell / scenario.name)
            with contextlib.redirect_stdout(io.StringIO()) as resumed:
                self.assertEqual(command_prepare(self.args(cell)), 0)
            self.assertEqual(json.loads(resumed.getvalue())["status"], "complete")
            receipt = json.loads((cell / "R3_ROLLOUT_101_COMPLETE.json").read_text())
            record = json.loads((cell / receipt["attempt_record"]).read_text())
            self.assertTrue(receipt["recovered_after_interruption"])
            self.assertEqual(record["classification"], "accepted_recovered_after_promotion")
            self.assertEqual(
                sum(path.is_dir() for path in cell.glob("_attempts/init_101/attempt_*")),
                1,
            )

    def test_actor_hygiene_selects_only_vehicle_and_sensor(self) -> None:
        actors = [
            FakeActor(1, "vehicle.audi.tt", "ego"),
            FakeActor(2, "sensor.other.collision"),
            FakeActor(3, "traffic.traffic_light"),
            FakeActor(4, "static.prop.streetbarrier"),
        ]
        self.assertTrue(is_experiment_actor_type("vehicle.audi.tt"))
        self.assertFalse(is_experiment_actor_type("traffic.traffic_light"))
        self.assertEqual([item["id"] for item in stale_actor_records(actors)], [1, 2])


class SnapshotHardeningTest(unittest.TestCase):
    def fixture(self, root: Path) -> Path:
        contract = {
            "status": "frozen",
            "expected_rollouts": 1,
            "ego_init_ids": [101],
            "execution_order": [{"cell_id": "B1_fixed_medium_assertive", "ego_init_id": 101}],
        }
        write_json(root / "r3_run_contract.json", contract)
        for relative in R3_REQUIRED_ROOT_FILES:
            path = root / relative
            if relative == "r3_run_contract.json":
                continue
            write_json(path, {"status": "pass", "additional_large_scale_carla_required": False})
        frozen = root / "_frozen_contracts"
        for name in R3_REQUIRED_FROZEN_CONTRACTS:
            write_json(frozen / name, {"status": "pass", "name": name})
        write_json(root / "_frozen_inits_101_105/ego_init_101.json", {"id": 101})
        cell = root / "B1_fixed_medium_assertive"
        scenario = valid_scenario(cell)
        write_json(cell / "R3_ROLLOUT_101_COMPLETE.json", {"status": "pass"})
        write_json(cell / "_attempts/init_101/attempt_ledger.json", {"status": "accepted"})
        return scenario

    def test_r3_archive_is_repeatable_verified_and_excludes_stale_sidecars(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            write_json(root / "R3_COMPLETE.json", {"status": "pass", "archive_sha256": "stale"})
            output = root / "r3_corrected_formal_snapshot.tar.gz"
            kwargs = dict(
                root=root,
                contract_name="r3_run_contract.json",
                audit_name="r3_corrected_matrix_audit.json",
                complete_name="R3_DATA_COMPLETE.json",
                output=output,
                profile="r3-final",
                evidence=[],
            )
            with contextlib.redirect_stdout(io.StringIO()):
                first = build_snapshot(**kwargs)
            first_hash = first["archive_sha256"]
            with contextlib.redirect_stdout(io.StringIO()):
                second = build_snapshot(**kwargs)
                verified = verify_snapshot(output)
            self.assertEqual(first_hash, second["archive_sha256"])
            self.assertEqual(verified["status"], "pass")
            files = json.loads(Path(str(output) + ".files.json").read_text())["files"]
            names = {item["path"] for item in files}
            self.assertIn(
                "B1_fixed_medium_assertive/scenario_uk_give_way_ego_init_101_smpc_fixed_risk/scenario_result.pkl",
                names,
            )
            self.assertNotIn(output.name + ".json", names)
            self.assertNotIn(output.name + ".files.json", names)
            self.assertNotIn("R3_COMPLETE.json", names)

    def test_r3_archive_rejects_symlinked_frozen_init(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            init = root / "_frozen_inits_101_105/ego_init_101.json"
            external = root.parent / f"{root.name}_external_init.json"
            external.write_text("{}\n", encoding="utf-8")
            init.unlink()
            init.symlink_to(external)
            try:
                with self.assertRaises(ValueError):
                    build_snapshot(
                        root=root,
                        contract_name="r3_run_contract.json",
                        audit_name="r3_corrected_matrix_audit.json",
                        complete_name="R3_DATA_COMPLETE.json",
                        output=root / "r3_corrected_formal_snapshot.tar.gz",
                        profile="r3-final",
                        evidence=[],
                    )
            finally:
                external.unlink(missing_ok=True)

    def test_progress_counts_accepted_and_pending(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            payload = build_summary(root)
            self.assertEqual(payload["accepted_rollouts"], 1)
            self.assertEqual(payload["pending_rollouts"], 0)


class ProvenanceSecurityTest(unittest.TestCase):
    def test_credential_pattern_is_rejected(self) -> None:
        assert_no_sensitive_text({"git_commit": "a" * 40, "versions": {"numpy": "1.0"}})
        with self.assertRaises(ValueError):
            assert_no_sensitive_text({"password": "do-not-record"})


class RunnerShellRegressionTest(unittest.TestCase):
    def test_cell_directory_does_not_reference_an_unbound_local(self) -> None:
        runner = MODELS_DIR.parent / "carla" / "experimental/run_r3_corrected_formal_matrix.sh"
        source = runner.read_text(encoding="utf-8")
        self.assertNotIn(
            'local cell_id="${predictor}_${policy}_${style}" cell_dir="${R3_RESULTS}/${cell_id}"',
            source,
        )
        self.assertIn('local cell_id="${predictor}_${policy}_${style}"\n', source)
        self.assertIn('local cell_dir="${R3_RESULTS}/${cell_id}"\n', source)


if __name__ == "__main__":
    unittest.main()
