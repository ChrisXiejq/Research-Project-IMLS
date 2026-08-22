#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODELS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODELS_DIR))

from capacity_study_v3_pipeline import (  # noqa: E402
    audit_fresh_evaluations,
    extension_execution_plan,
    select_and_audit_convergence,
)
from capacity_study_v3_runs import core_runs  # noqa: E402


def _completion(spec, *, best_epoch=40, epochs=80, run_id=None):
    return {
        "status": "pass",
        "run_id": run_id or spec.run_id,
        "rollout_macro_nll": 1.0 + spec.learning_rate,
        "best_epoch": best_epoch,
        "epochs_allowed": epochs,
        "checkpoint_selection_metric": "validation_rollout_macro_trajectory_mixture_NLL_per_step",
    }


class CapacityStudyV3PipelineTests(unittest.TestCase):
    def test_extension_completion_replaces_base_checkpoint_without_test_access(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for spec in core_runs():
                path = root / spec.run_id / "TRAINING_COMPLETE.json"
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps(_completion(spec)), encoding="utf-8")
            victim = next(
                spec
                for spec in core_runs()
                if spec.model_cell_id == "transformer-h1p0-small"
                and spec.learning_rate == 3.0e-5
                and spec.seed == 11
            )
            extension_id = victim.run_id + "__extended120"
            extension_dir = root / extension_id
            extension_dir.mkdir()
            (extension_dir / "TRAINING_COMPLETE.json").write_text(
                json.dumps(_completion(victim, best_epoch=50, epochs=120, run_id=extension_id)),
                encoding="utf-8",
            )
            (extension_dir / "run_config.json").write_text(
                json.dumps({"run_spec": {"extends_run_id": victim.run_id}}),
                encoding="utf-8",
            )
            with patch(
                "capacity_study_v3_execute.completion_is_valid", return_value=True
            ):
                selection, convergence, rows = select_and_audit_convergence(
                    root, extension_root=root
                )
            selected = next(
                row
                for row in selection["selected_cells"]
                if row["model_cell_id"] == "transformer-h1p0-small"
            )
            self.assertIn(extension_id, selected["retained_run_ids"])
            replaced = next(row for row in rows if row["run_id"] == victim.run_id)
            self.assertEqual(replaced["checkpoint_run_id"], extension_id)
            self.assertEqual(convergence["status"], "pass")

    def test_extension_plan_is_manifest_bound_and_resumable(self):
        convergence = {
            "status": "requires_extension",
            "extension_runs": [
                {"run_id": "extended-a", "extends_run_id": "base-a"},
                {"run_id": "extended-b", "extends_run_id": "base-b"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = extension_execution_plan(
                convergence,
                convergence_path=root / "convergence.json",
                merged_dir=root / "data",
                base_model=root / "base",
                anchors=root / "anchors.npy",
                output_root=root / "extended",
                python_bin="python-server",
            )
            self.assertEqual(plan["planned"], 2)
            self.assertEqual(plan["pending"], 2)
            self.assertEqual(len({job["command"] for job in plan["jobs"]}), 2)

    def test_fresh_audit_requires_identical_membership_and_correct_horizon(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = []
            for dataset, groups in (("general_test", 10), ("interaction_challenge", 20)):
                for cell, horizon in (("head-large", None), ("mlp-h0p4-large", 0.4)):
                    path = root / dataset / f"{cell}.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(
                        json.dumps(
                            {
                                "status": "pass",
                                "split": "test",
                                "calibration_fit_uses_test": False,
                                "requires_complete_interaction_history": True,
                                "independent_init_groups": groups,
                                "sample_membership_sha256": dataset + "-members",
                                "trained_history_horizon_s": horizon,
                                "calibrated": {"response_strata_v3": {}},
                            }
                        ),
                        encoding="utf-8",
                    )
                    jobs.append(
                        {
                            "job_id": dataset + cell,
                            "dataset": dataset,
                            "model_cell_id": cell,
                            "output": str(path),
                        }
                    )
            self.assertEqual(audit_fresh_evaluations(jobs)["status"], "pass")
            value = json.loads(Path(jobs[-1]["output"]).read_text(encoding="utf-8"))
            value["sample_membership_sha256"] = "wrong"
            Path(jobs[-1]["output"]).write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(audit_fresh_evaluations(jobs)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
