"""Regression tests for the provenance-preserving SF4 recovery amendment."""

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[4]
MODELS = ROOT / "core" / "scripts" / "models"
sys.path.insert(0, str(MODELS))


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


recovery = load(
    "sf4_infrastructure_recovery_tested",
    MODELS / "prepare_sf4_infrastructure_recovery.py",
)


class RecoveryEligibilityTests(unittest.TestCase):
    def make_exhausted(self, root: Path, *, scientific_summaries: int = 0) -> Path:
        attempts = root / "SF4_cell" / "_attempts" / "init_112"
        for number in range(1, 11):
            directory = attempts / f"attempt_{number:03d}"
            directory.mkdir(parents=True)
            record = {
                "attempt": number,
                "accepted": False,
                "classification": "infrastructure_failure",
                "retry_allowed": True,
                "exit_code": 1,
                "classifier_matches": ["carla_timeout", "scenario_setup"],
                "scenario_summaries_found": scientific_summaries,
                "successful_scenarios_found": 0,
            }
            (directory / "attempt_record.json").write_text(
                json.dumps(record) + "\n", encoding="utf-8"
            )
            (directory / "runner_attempt.log").write_text(
                "CARLA timeout\n", encoding="utf-8"
            )
        return attempts

    def test_exactly_ten_carla_only_failures_are_eligible(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            attempts = self.make_exhausted(root)
            result = recovery.find_exhausted(
                root, {("SF4_cell", 112)}, original_max=10
            )
            self.assertEqual(result[0:2], ("SF4_cell", 112))
            self.assertEqual(result[2], attempts)
            self.assertEqual(len(result[3]), 10)
            self.assertEqual(result[4], 0)

    def test_any_scientific_summary_blocks_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_exhausted(root, scientific_summaries=1)
            with self.assertRaisesRegex(ValueError, "not eligible"):
                recovery.find_exhausted(
                    root, {("SF4_cell", 112)}, original_max=10
                )

    def test_existing_receipt_is_verified_and_never_selected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            receipt = root / "SF4_done" / "SF4_ROLLOUT_106_COMPLETE.json"
            receipt.parent.mkdir(parents=True)
            receipt.write_text("{}\n", encoding="utf-8")
            self.make_exhausted(root)
            with mock.patch.object(recovery, "valid_receipt", return_value=True):
                result = recovery.find_exhausted(
                    root,
                    {("SF4_done", 106), ("SF4_cell", 112)},
                    original_max=10,
                )
            self.assertEqual(result[0:2], ("SF4_cell", 112))
            self.assertEqual(result[4], 1)

    def test_runner_keeps_original_git_identity_and_per_key_cap(self):
        source = (
            ROOT / "core" / "scripts" / "carla"
            / "run_sf4_infrastructure_recovery.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('--prediction_git_commit "${CONTRACT_COMMIT}"', source)
        self.assertIn('max_attempts="$(max_attempts_for', source)
        self.assertIn('--amendment "${AMENDMENT}"', source)
        self.assertNotIn("rm -rf", source)

    def test_prepare_freezes_and_idempotently_revalidates_amendment(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            root = workspace / "results"
            repo = workspace / "repo"
            repo.mkdir()
            source = repo / "frozen_source.py"
            recovery_runner = repo / "recovery.sh"
            recovery_source = repo / "prepare_recovery.py"
            source.write_text("frozen\n", encoding="utf-8")
            recovery_runner.write_text("runner\n", encoding="utf-8")
            recovery_source.write_text("helper\n", encoding="utf-8")

            order = [
                {"cell_id": "SF4_cell", "ego_init_id": 112},
                *[
                    {"cell_id": f"SF4_other_{index}", "ego_init_id": index}
                    for index in range(79)
                ],
            ]
            contract = root / "contract.json"
            contract.parent.mkdir(parents=True)
            contract.write_text(
                json.dumps(
                    {
                        "schema_version": (
                            "sf4_supervisor_behavioural_authority_run_contract_v1"
                        ),
                        "git_commit": "frozen-commit",
                        "execution_order": order,
                        "retry_policy": {"max_attempts": 10},
                        "hashes": {
                            "execution_sources": {
                                "frozen_source.py": recovery.sha256(source)
                            }
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            contract_hash = recovery.sha256(contract)
            preflight = root / "preflight.json"
            preflight.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "formal_rollouts_launched": 0,
                        "contract_sha256": contract_hash,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            smoke = root / "smoke.json"
            smoke.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "formal_rollouts_observed": 0,
                        "contract_sha256": contract_hash,
                        "records": [
                            {"label": label, "status": "pass"}
                            for label in (
                                "fixed_on", "fixed_off",
                                "adaptive_on", "adaptive_off",
                            )
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            attempts = self.make_exhausted(root)
            args = Namespace(
                results_dir=root,
                repo=repo,
                contract=contract,
                preflight=preflight,
                smoke=smoke,
                recovery_runner=recovery_runner,
                extended_max=20,
            )
            with (
                mock.patch.object(recovery, "__file__", str(recovery_source)),
                mock.patch.object(
                    recovery.subprocess,
                    "check_output",
                    return_value="recovery-commit\n",
                ),
            ):
                with contextlib.redirect_stdout(io.StringIO()) as first:
                    recovery.prepare(args)
                with contextlib.redirect_stdout(io.StringIO()) as second:
                    recovery.prepare(args)
            first_payload = json.loads(first.getvalue())
            second_payload = json.loads(second.getvalue())
            self.assertEqual(first_payload["amendment_sha256"], second_payload["amendment_sha256"])
            amendment = attempts / "SF4_INFRASTRUCTURE_RECOVERY_AMENDMENT.json"
            self.assertTrue(amendment.is_file())
            value = json.loads(amendment.read_text())
            self.assertFalse(
                value["complete_scientific_scenario_outputs_observed"]
            )
            self.assertEqual(value["extended_max_attempts_for_target_only"], 20)


if __name__ == "__main__":
    unittest.main()
