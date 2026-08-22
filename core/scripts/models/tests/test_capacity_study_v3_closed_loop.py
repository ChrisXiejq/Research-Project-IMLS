#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODELS_DIR))

from capacity_study_v3_closed_loop import (  # noqa: E402
    RISK_POLICIES,
    TARGET_STYLES,
    analyze_predictor_by_risk,
    audit_closed_loop_outputs,
    build_closed_loop_manifest,
    validate_closed_loop_manifest,
    validate_dual_predictor_preflight,
)
from capacity_study_v3_protocol import build_group_registry, sha256_payload  # noqa: E402


def freeze_fixture():
    payload = {
        "schema_version": "capacity_history_selection_freeze_v3",
        "status": "pass",
        "fresh_test_access_allowed": True,
        "selection_uses_fresh_test": False,
        "B1": {"model_cell_id": "head-large", "representative_run_id": "b1"},
        "P_star": {
            "family": "mlp",
            "model_cell_id": "mlp-h1p0-large",
            "representative_run_id": "pstar",
        },
    }
    payload["freeze_sha256"] = sha256_payload(payload)
    return payload


def nuisance_fixture():
    return {
        "town": "Town05",
        "scenario": "scenario_uk_give_way.json",
        "tuning_sha256": "tuning",
        "anchors_sha256": "anchors",
        "supervisor_authority": "enabled",
        "target_speed_mps": 9.0,
        "target_offset_m": 0.0,
    }


def thesis_core_freeze_fixture():
    payload = {
        "schema_version": "capacity_history_thesis_core_selection_freeze_v3",
        "status": "pass",
        "evidence_status": "retrospective_held_out",
        "heldout_access_authorized": True,
        "B1": {"model_cell_id": "head-large", "representative_run_id": "b1"},
        "P_star": {
            "model_cell_id": "transformer-h1p0-large",
            "representative_run_id": "pstar",
        },
    }
    payload["freeze_sha256"] = sha256_payload(payload)
    return payload


class CapacityStudyV3ClosedLoopTests(unittest.TestCase):
    def test_thesis_core_selection_freeze_drives_exact_80_matrix(self) -> None:
        freeze = thesis_core_freeze_fixture()
        manifest = build_closed_loop_manifest(
            freeze, build_group_registry(), nuisance_settings=nuisance_fixture()
        )
        self.assertEqual(validate_closed_loop_manifest(manifest, freeze)["rollouts"], 80)
        self.assertEqual(manifest["risk_policies"], ["fixed_medium", "adaptive"])

    def test_exact_80_matrix_and_selection_binding(self) -> None:
        freeze = freeze_fixture()
        manifest = build_closed_loop_manifest(
            freeze, build_group_registry(), nuisance_settings=nuisance_fixture()
        )
        self.assertEqual(validate_closed_loop_manifest(manifest, freeze)["rollouts"], 80)
        altered = copy.deepcopy(manifest)
        altered["rollouts"].pop()
        altered["manifest_sha256"] = sha256_payload(
            {key: value for key, value in altered.items() if key != "manifest_sha256"}
        )
        with self.assertRaisesRegex(ValueError, "80-cell"):
            validate_closed_loop_manifest(altered, freeze)

    def test_preflight_accepts_mlp_or_transformer_and_rejects_parity_failure(self) -> None:
        freeze = freeze_fixture()
        manifest = build_closed_loop_manifest(
            freeze, build_group_registry(), nuisance_settings=nuisance_fixture()
        )
        records = {}
        for predictor, run in (("B1", "b1"), ("P_star", "pstar")):
            records[predictor] = {
                "representative_run_id": run,
                "model_identity": predictor + "-model",
                "calibration_model_identity": predictor + "-model",
                "calibration_identity": predictor + "-calibration",
                "calibration_fit_split": "validation",
                "output_shape_valid": True,
                "probabilities_valid": True,
                "covariances_valid": True,
                "joint_mode_mapping_valid": True,
                "solver_smoke_valid": True,
                "offline_online_max_abs_diff": 1.0e-7,
                "warmed_batch_one_latency_ms": 5.0,
                "latency_limit_ms": 50.0,
            }
        report = validate_dual_predictor_preflight(
            manifest, freeze, records, {"status": "pass", "gurobi": True}
        )
        self.assertEqual(report["status"], "pass")
        records["P_star"]["offline_online_max_abs_diff"] = 0.1
        with self.assertRaisesRegex(ValueError, "numerical_parity"):
            validate_dual_predictor_preflight(
                manifest, freeze, records, {"status": "pass", "gurobi": True}
            )

    def test_known_model_by_risk_interaction_is_recovered(self) -> None:
        rows = []
        risk_effect = {"fixed_medium": 1.0, "adaptive": -1.0}
        for group in range(81, 91):
            for risk in RISK_POLICIES:
                for style in TARGET_STYLES:
                    for predictor in ("B1", "P_star"):
                        rows.append(
                            {
                                "ego_init_id": group,
                                "risk_policy": risk,
                                "target_style": style,
                                "predictor": predictor,
                                "failure_rate": (
                                    risk_effect[risk] if predictor == "P_star" else 0.0
                                ),
                            }
                        )
        report = analyze_predictor_by_risk(rows, ["failure_rate"])
        within = {
            row["contrast_id"]: row["effect_P_star_minus_B1"]
            for row in report["within_risk_contrasts"]
        }
        interaction = {
            row["contrast_id"]: row["effect_P_star_minus_B1"]
            for row in report["model_by_risk_interactions"]
        }
        self.assertEqual(within["failure_rate__P_star_minus_B1__fixed_medium"], 1.0)
        self.assertEqual(
            interaction[
                "failure_rate__model_by_risk__adaptive_minus_fixed_medium"
            ],
            -2.0,
        )
        rows[0]["undefined_metric"] = None
        guarded = analyze_predictor_by_risk(rows, ["undefined_metric"])
        self.assertEqual(len(guarded["null_or_under_supported_metrics"]), 1)
        self.assertFalse(guarded["null_or_under_supported_metrics"][0]["claim_allowed"])

    def test_completion_audit_rejects_missing_or_drifted_rollout(self) -> None:
        freeze = freeze_fixture()
        manifest = build_closed_loop_manifest(
            freeze, build_group_registry(), nuisance_settings=nuisance_fixture()
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index, row in enumerate(manifest["rollouts"]):
                path = root / f"rollout_{index:03d}" / "ROLLOUT_COMPLETE.json"
                path.parent.mkdir(parents=True)
                path.write_text(
                    json.dumps(
                        {
                            "status": "pass",
                            "rollout_id": row["rollout_id"],
                            "manifest_sha256": manifest["manifest_sha256"],
                        }
                    ),
                    encoding="utf-8",
                )
            self.assertEqual(
                audit_closed_loop_outputs(manifest, freeze, root)["status"], "pass"
            )
            victim = root / "rollout_000" / "ROLLOUT_COMPLETE.json"
            payload = json.loads(victim.read_text(encoding="utf-8"))
            payload["manifest_sha256"] = "contaminated"
            victim.write_text(json.dumps(payload), encoding="utf-8")
            failed = audit_closed_loop_outputs(manifest, freeze, root)
            self.assertEqual(failed["status"], "incomplete")
            self.assertEqual(len(failed["invalid_rollout_ids"]), 1)


if __name__ == "__main__":
    unittest.main()
