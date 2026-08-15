"""Regression tests for the SF4 post-collection model-hash bridge."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MODELS = ROOT / "core" / "scripts" / "models"


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


compat = load(
    "sf4_offline_hash_compatibility_tested",
    MODELS / "finalize_sf4_offline_hash_compatibility.py",
)


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


class Sf4HashCompatibilityTests(unittest.TestCase):
    def fixture(self, root: Path):
        repo = root / "repo"
        results = root / "results"
        model = root / "model"
        analyzer = repo / compat.FROZEN_ANALYZER_RELATIVE
        analyzer.parent.mkdir(parents=True)
        analyzer.write_text("# frozen analyser\n", encoding="utf-8")
        model.mkdir()
        (model / "saved_model.pb").write_bytes(b"model")
        variables = model / "variables"
        variables.mkdir()
        (variables / "variables.data").write_bytes(b"weights")
        dual = compat.model_tree_hashes(model)
        calibration_hash = "calibration"
        anchors_hash = "anchors"
        order = []
        for number in range(80):
            cell = "SF4_cell_%d" % (number % 8)
            init_id = 106 + number // 8
            order.append({"cell_id": cell, "ego_init_id": init_id})
            scenario_name = "scenario_%03d" % number
            receipt = results / cell / ("SF4_ROLLOUT_%d_COMPLETE.json" % init_id)
            write_json(
                receipt,
                {
                    "status": "pass",
                    "cell_id": cell,
                    "ego_init_id": init_id,
                    "scenario_dir": scenario_name,
                },
            )
            write_json(
                results / cell / scenario_name / "prediction_deployment_manifest.json",
                {
                    "status": "pass",
                    "warmup_passed": True,
                    "model_artifact": {
                        "sha256_tree": dual[
                            "runtime_concatenated_record_sha256_tree"
                        ]
                    },
                    "calibration_artifact": {"sha256": calibration_hash},
                    "anchors_artifact": {"sha256": anchors_hash},
                },
            )
        preflight = results / "sf4_b1_deployment_preflight.json"
        write_json(
            preflight,
            {
                "status": "pass",
                "selected_variant": "B1",
                "selected_seed": 37,
                "anchors": {"sha256": anchors_hash},
                "b1": {
                    "deployment": {
                        "model_artifact": {
                            "path": str(model),
                            "files": dual["files"],
                            "bytes": dual["bytes"],
                            "sha256_tree": dual[
                                "runtime_concatenated_record_sha256_tree"
                            ],
                        },
                        "calibration_model_artifact": {
                            "sha256_tree": dual[
                                "runtime_concatenated_record_sha256_tree"
                            ]
                        },
                        "calibration_artifact": {"sha256": calibration_hash},
                    }
                },
            },
        )
        contract = results / "sf4_supervisor_behavioural_authority_run_contract.json"
        write_json(
            contract,
            {
                "schema_version": "sf4_supervisor_behavioural_authority_run_contract_v1",
                "execution_order": order,
                "hashes": {
                    "deployment_preflight": compat.sha256(preflight),
                    "b1_model_tree": dual[
                        "contract_newline_record_sha256_tree"
                    ],
                    "b1_calibration": calibration_hash,
                    "anchors": anchors_hash,
                    "execution_sources": {
                        compat.FROZEN_ANALYZER_RELATIVE: compat.sha256(analyzer)
                    },
                },
            },
        )
        return repo, results, model, contract, preflight

    def test_dual_hash_bridge_accepts_same_model_bytes_and_all_80_manifests(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = self.fixture(Path(temporary))
            payload = compat.validate_identity_bridge(
                fixture[1], fixture[0], fixture[3], fixture[4], fixture[2]
            )
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["rollout_deployment_manifests_verified"], 80)
            proof = payload["model_tree_dual_hash_proof"]
            self.assertNotEqual(
                proof["contract_newline_record_sha256_tree"],
                proof["runtime_concatenated_record_sha256_tree"],
            )

    def test_tampered_preflight_binding_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, results, model, contract, preflight = self.fixture(Path(temporary))
            value = json.loads(preflight.read_text(encoding="utf-8"))
            value["extra"] = "tamper"
            write_json(preflight, value)
            with self.assertRaisesRegex(ValueError, "not bound"):
                compat.validate_identity_bridge(
                    results, repo, contract, preflight, model
                )

    def test_runtime_manifest_model_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, results, model, contract, preflight = self.fixture(Path(temporary))
            manifest = next(results.glob("SF4_*/scenario_*/prediction_deployment_manifest.json"))
            value = json.loads(manifest.read_text(encoding="utf-8"))
            value["model_artifact"]["sha256_tree"] = "different"
            write_json(manifest, value)
            with self.assertRaisesRegex(ValueError, "runtime deployment identity drift"):
                compat.validate_identity_bridge(
                    results, repo, contract, preflight, model
                )

    def test_current_model_byte_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo, results, model, contract, preflight = self.fixture(Path(temporary))
            (model / "saved_model.pb").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "do not bridge"):
                compat.validate_identity_bridge(
                    results, repo, contract, preflight, model
                )


if __name__ == "__main__":
    unittest.main()
