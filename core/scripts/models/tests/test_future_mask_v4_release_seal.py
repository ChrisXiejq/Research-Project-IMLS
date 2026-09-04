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
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from capacity_study_v3_protocol import (  # noqa: E402
    atomic_json,
    sha256_file,
    sha256_payload,
)
from seal_future_mask_v4_release import (  # noqa: E402
    REQUIRED_FIGURE_FILES,
    REQUIRED_PAPER_FILES,
)


class FutureMaskV4ReleaseSealTest(unittest.TestCase):
    def payloads(self, root: Path):
        gates = {
            "cache_and_mask_audit_sha256": "cache",
            "historical_impact_audit_sha256": "impact",
            "training_curve_audit_sha256": "training",
            "full_horizon_sensitivity_sha256": "full",
            "formal_report_contract_audit_sha256": "formal",
            "pipeline_receipt_sha256": "pipeline",
            "pipeline_stage_receipt_sha256": "pipeline-stage",
            "selection_freeze_sha256": "freeze",
            "corrected_synthesis_sha256": "synthesis",
            "extension_protocol_sha256": "extension",
        }
        evidence = {
            "schema_version": "capacity_history_future_mask_v4_offline_evidence_release",
            "status": "pass",
            "corrected_runs": 27,
            "future_validity_contract": "future_valid_mask_fail_closed_v4",
            "gate_artifacts": gates,
            "claim_consistency_audit_sha256": "claims",
            "carla_deployment_decision_sha256": "carla",
            "carla_was_launched": False,
        }
        evidence["release_sha256"] = sha256_payload(evidence)
        figures = {
            "schema_version": "capacity_history_future_mask_v4_figure_manifest",
            "status": "pass",
            "source_artifacts": {
                "impact_audit_sha256": "impact",
                "offline_synthesis_sha256": "synthesis",
                "full_horizon_sensitivity_sha256": "full",
                "selection_freeze_sha256": "freeze",
            },
            "files": {},
        }
        paper = {
            "schema_version": "capacity_history_future_mask_v4_paper_outputs",
            "status": "pass",
            "corrected_runs": 27,
            "future_validity_contract": "future_valid_mask_fail_closed_v4",
            "paper_source_modified": False,
            "source_artifacts": {
                "selection_freeze_sha256": "freeze",
                "synthesis_sha256": "synthesis",
                "cache_audit_sha256": "cache",
                "full_horizon_sensitivity_sha256": "full",
                "claim_consistency_audit_sha256": "claims",
                "carla_deployment_decision_sha256": "carla",
                "offline_evidence_release_sha256": evidence["release_sha256"],
                "foundation_mask_scope_audit_sha256": "foundation",
                "extension_protocol_sha256": "extension",
            },
            "files": {},
        }
        foundation = {
            "schema_version": "capacity_history_foundation_future_mask_scope_audit_v4",
            "status": "pass",
            "evaluated_membership": {
                "partial_windows_entered_foundation_metrics": 0,
            },
        }
        foundation["audit_sha256"] = sha256_payload(foundation)
        paper["source_artifacts"]["foundation_mask_scope_audit_sha256"] = foundation[
            "audit_sha256"
        ]
        for name in sorted(REQUIRED_FIGURE_FILES):
            path = root / name
            path.write_bytes(f"figure:{name}\n".encode("utf-8"))
            figures["files"][name] = sha256_file(path)
        figures["manifest_sha256"] = sha256_payload(figures)
        for name in sorted(REQUIRED_PAPER_FILES):
            path = root / name
            path.write_bytes(f"paper:{name}\n".encode("utf-8"))
            paper["files"][name] = sha256_file(path)
        paper["manifest_sha256"] = sha256_payload(paper)
        return evidence, figures, paper, foundation

    def run_seal(self, root: Path):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "experimental/seal_future_mask_v4_release.py"),
                "--evidence", str(root / "evidence.json"),
                "--figures", str(root / "figures.json"),
                "--paper-outputs", str(root / "paper.json"),
                "--foundation-scope", str(root / "foundation.json"),
                "--output", str(root / "release.json"),
            ],
            capture_output=True,
            text=True,
        )

    def test_valid_cross_linked_manifests_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, figures, paper, foundation = self.payloads(root)
            atomic_json(root / "evidence.json", evidence)
            atomic_json(root / "figures.json", figures)
            atomic_json(root / "paper.json", paper)
            atomic_json(root / "foundation.json", foundation)
            result = self.run_seal(root)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_schema_or_cross_link_fails_even_when_self_hashed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, figures, paper, foundation = self.payloads(root)
            evidence["schema_version"] = "wrong-but-self-hashed"
            evidence["release_sha256"] = sha256_payload(
                {key: value for key, value in evidence.items() if key != "release_sha256"}
            )
            atomic_json(root / "evidence.json", evidence)
            atomic_json(root / "figures.json", figures)
            atomic_json(root / "paper.json", paper)
            atomic_json(root / "foundation.json", foundation)
            self.assertNotEqual(self.run_seal(root).returncode, 0)

            evidence, figures, paper, foundation = self.payloads(root)
            paper["source_artifacts"]["synthesis_sha256"] = "different"
            paper["manifest_sha256"] = sha256_payload(
                {key: value for key, value in paper.items() if key != "manifest_sha256"}
            )
            atomic_json(root / "evidence.json", evidence)
            atomic_json(root / "figures.json", figures)
            atomic_json(root / "paper.json", paper)
            atomic_json(root / "foundation.json", foundation)
            self.assertNotEqual(self.run_seal(root).returncode, 0)

    def test_deleted_or_tampered_release_file_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, figures, paper, foundation = self.payloads(root)
            atomic_json(root / "evidence.json", evidence)
            atomic_json(root / "figures.json", figures)
            atomic_json(root / "paper.json", paper)
            atomic_json(root / "foundation.json", foundation)

            deleted = root / sorted(REQUIRED_FIGURE_FILES)[0]
            deleted.unlink()
            self.assertNotEqual(self.run_seal(root).returncode, 0)

            evidence, figures, paper, foundation = self.payloads(root)
            atomic_json(root / "evidence.json", evidence)
            atomic_json(root / "figures.json", figures)
            atomic_json(root / "paper.json", paper)
            atomic_json(root / "foundation.json", foundation)
            tampered = root / sorted(REQUIRED_PAPER_FILES)[0]
            tampered.write_bytes(tampered.read_bytes() + b"tampered\n")
            self.assertNotEqual(self.run_seal(root).returncode, 0)

    def test_empty_files_or_missing_required_file_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence, figures, paper, foundation = self.payloads(root)
            figures["files"] = {}
            figures["manifest_sha256"] = sha256_payload(
                {key: value for key, value in figures.items() if key != "manifest_sha256"}
            )
            atomic_json(root / "evidence.json", evidence)
            atomic_json(root / "figures.json", figures)
            atomic_json(root / "paper.json", paper)
            atomic_json(root / "foundation.json", foundation)
            self.assertNotEqual(self.run_seal(root).returncode, 0)

            evidence, figures, paper, foundation = self.payloads(root)
            paper["files"].pop(sorted(REQUIRED_PAPER_FILES)[0])
            paper["manifest_sha256"] = sha256_payload(
                {key: value for key, value in paper.items() if key != "manifest_sha256"}
            )
            atomic_json(root / "evidence.json", evidence)
            atomic_json(root / "figures.json", figures)
            atomic_json(root / "paper.json", paper)
            atomic_json(root / "foundation.json", foundation)
            self.assertNotEqual(self.run_seal(root).returncode, 0)


if __name__ == "__main__":
    unittest.main()
