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
import sys
import tempfile
import unittest
from pathlib import Path


MODELS_DIR = Path(__file__).resolve().parents[1]
if str(MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(MODELS_DIR))
    sys.path.insert(0, str(MODELS_DIR / "experimental"))

from capacity_study_v3_collection import (  # noqa: E402
    audit_collection_outputs,
    build_collection_manifest,
    materialize_init_files,
    seal_fresh_dataset,
    validate_collection_manifest,
)
from capacity_study_v3_protocol import build_group_registry  # noqa: E402


def _write_rollout(root: Path, row: dict, sample_time: float = 2.0) -> None:
    dataset_dir = (
        root
        / row["cell_id"]
        / f"scenario_uk_give_way_ego_init_{row['ego_init_id']:02d}"
        / "prediction_dataset"
    )
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "prediction_dataset_manifest.json").write_text(
        json.dumps(
            {
                "cell_id": row["cell_id"],
                "ego_init_id": row["ego_init_id"],
                "status": "pass",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    reactive = row["target_style"] == "defensive_reactive"
    sample = {
        "sample_id": row["rollout_id"] + "_0001",
        "cell_id": row["cell_id"],
        "ego_init_id": row["ego_init_id"],
        "target_style": row["target_style"],
        "simulation_time_s": sample_time,
        "target_reactive_diagnostics": {
            "trigger_time_s": 2.0 if reactive else None,
            "active": reactive,
        },
    }
    (dataset_dir / "prediction_dataset_labeled.jsonl").write_text(
        json.dumps(sample) + "\n", encoding="utf-8"
    )


class CapacityStudyV3CollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = build_group_registry()

    def test_frozen_manifests_have_exact_paired_counts(self) -> None:
        general = build_collection_manifest(self.registry, "general_test")
        challenge = build_collection_manifest(self.registry, "interaction_challenge")
        self.assertEqual(validate_collection_manifest(general)["rollouts"], 40)
        self.assertEqual(validate_collection_manifest(challenge)["rollouts"], 80)
        self.assertEqual(validate_collection_manifest(general)["independent_groups"], 10)
        self.assertEqual(validate_collection_manifest(challenge)["independent_groups"], 20)
        self.assertEqual(challenge["offset_strata"]["negative"], 10)
        self.assertEqual(challenge["offset_strata"]["positive"], 10)
        self.assertFalse(challenge["admission_rule"]["response_trigger_is_guaranteed"])
        self.assertTrue(challenge["admission_rule"]["candidate_model_outputs_forbidden"])
        tampered = json.loads(json.dumps(general))
        tampered["rollouts"][0]["ego_policy"] = "post_result_policy"
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_collection_manifest(tampered)

    def test_materialized_init_files_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = materialize_init_files(self.registry, tmp)
            self.assertEqual(report["init_files"], 40)
            first = Path(report["records"][0]["path"])
            self.assertTrue(first.is_file())
            first.write_text("{}\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Frozen init drift"):
                materialize_init_files(self.registry, tmp)

    def test_audit_rejects_missing_and_accepts_exact_matrix(self) -> None:
        manifest = build_collection_manifest(self.registry, "general_test")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for row in manifest["rollouts"][:-1]:
                _write_rollout(root, row)
            failed = audit_collection_outputs(manifest, root)
            self.assertEqual(failed["status"], "fail")
            self.assertEqual(len(failed["missing"]), 1)
            _write_rollout(root, manifest["rollouts"][-1])
            passed = audit_collection_outputs(manifest, root)
            self.assertEqual(passed["status"], "pass")
            self.assertEqual(passed["observed_rollouts"], 40)

    def test_seal_proves_group_disjointness_and_stratum_support(self) -> None:
        manifest = build_collection_manifest(self.registry, "general_test")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = root / "results"
            for row in manifest["rollouts"]:
                _write_rollout(results, row)
            completion = seal_fresh_dataset(manifest, results, root / "sealed")
            self.assertEqual(completion["rollouts"], 40)
            self.assertEqual(completion["independent_groups"], 10)
            self.assertEqual(completion["historical_group_overlap"], [])
            self.assertEqual(completion["response_stratum_windows"]["assertive"], 20)
            self.assertEqual(completion["response_stratum_windows"]["response_onset"], 20)
            self.assertEqual(completion["response_stratum_windows"]["response_active"], 0)
            self.assertEqual(len(completion["response_stratum_windows"]), 4)
            self.assertTrue((root / "sealed" / "test.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
