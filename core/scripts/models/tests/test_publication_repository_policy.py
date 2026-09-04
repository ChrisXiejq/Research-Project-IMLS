from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from publication_repository_policy import audit_markdown_links, audit_paths  # noqa: E402


class PublicationRepositoryPolicyTest(unittest.TestCase):
    def test_rejects_internal_and_raw_paths(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "core/scripts/carla/run_all_scenarios.py",
                "artifacts/raw/smpc_debug_steps.jsonl",
                "openspec/changes/x/tasks.md",
            ],
            file_sizes={"artifacts/raw/smpc_debug_steps.jsonl": 1024},
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["forbidden_tracked_paths"],
            [
                "artifacts/raw/smpc_debug_steps.jsonl",
                "openspec/changes/x/tasks.md",
            ],
        )

    def test_accepts_core_repository(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "REPRODUCIBILITY.md",
                "CITATION.cff",
                "THIRD_PARTY_NOTICES.md",
                "core/scripts/carla/run_all_scenarios.py",
                "core/scripts/carla/policies/smpc_agent.py",
                "core/scripts/models/evaluate_prediction_model.py",
            ],
            file_sizes={},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["missing_required_paths"], [])
        self.assertEqual(report["forbidden_tracked_paths"], [])

    def test_rejects_paper_materials(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "REPRODUCIBILITY.md",
                "CITATION.cff",
                "THIRD_PARTY_NOTICES.md",
                "core/scripts/carla/run_all_scenarios.py",
                "core/scripts/carla/policies/smpc_agent.py",
                "core/scripts/models/evaluate_prediction_model.py",
                "docs/paper/generated/result.json",
            ],
            file_sizes={},
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["forbidden_tracked_paths"],
            ["docs/paper/generated/result.json"],
        )

    def test_accepts_public_demonstration_video(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "REPRODUCIBILITY.md",
                "CITATION.cff",
                "THIRD_PARTY_NOTICES.md",
                "core/scripts/carla/run_all_scenarios.py",
                "core/scripts/carla/policies/smpc_agent.py",
                "core/scripts/models/evaluate_prediction_model.py",
                "docs/paper/CARLA_video.mp4",
            ],
            file_sizes={"docs/paper/CARLA_video.mp4": 2_078_047},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["forbidden_tracked_paths"], [])

    def test_rejects_other_videos(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "REPRODUCIBILITY.md",
                "CITATION.cff",
                "THIRD_PARTY_NOTICES.md",
                "core/scripts/carla/run_all_scenarios.py",
                "core/scripts/carla/policies/smpc_agent.py",
                "core/scripts/models/evaluate_prediction_model.py",
                "docs/paper/raw_rollout.mp4",
            ],
            file_sizes={"docs/paper/raw_rollout.mp4": 1024},
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["forbidden_tracked_paths"],
            ["docs/paper/raw_rollout.mp4"],
        )

    def test_rejects_generated_evidence_outside_public_allowlist(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "REPRODUCIBILITY.md",
                "CITATION.cff",
                "THIRD_PARTY_NOTICES.md",
                "core/scripts/carla/run_all_scenarios.py",
                "core/scripts/carla/policies/smpc_agent.py",
                "core/scripts/models/evaluate_prediction_model.py",
                "docs/paper/generated/day6/internal_audit.json",
            ],
            file_sizes={},
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["forbidden_tracked_paths"],
            ["docs/paper/generated/day6/internal_audit.json"],
        )

    def test_rejects_redistributed_literature_pdf(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "REPRODUCIBILITY.md",
                "CITATION.cff",
                "THIRD_PARTY_NOTICES.md",
                "core/scripts/carla/run_all_scenarios.py",
                "core/scripts/carla/policies/smpc_agent.py",
                "core/scripts/models/evaluate_prediction_model.py",
                "docs/literature/source_paper.pdf",
            ],
            file_sizes={},
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["forbidden_tracked_paths"],
            ["docs/literature/source_paper.pdf"],
        )

    def test_rejects_private_assessment_pdf(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "REPRODUCIBILITY.md",
                "CITATION.cff",
                "THIRD_PARTY_NOTICES.md",
                "core/scripts/carla/run_all_scenarios.py",
                "core/scripts/carla/policies/smpc_agent.py",
                "core/scripts/models/evaluate_prediction_model.py",
                "docs/dissertation/Marking Rubric.pdf",
            ],
            file_sizes={},
        )

        self.assertEqual(report["status"], "fail")
        self.assertEqual(
            report["forbidden_tracked_paths"],
            ["docs/dissertation/Marking Rubric.pdf"],
        )

    def test_manifest_bytes_are_counted(self) -> None:
        tracked_paths = [
            "README.md",
            "REPRODUCIBILITY.md",
            "CITATION.cff",
            "THIRD_PARTY_NOTICES.md",
            "core/scripts/carla/run_all_scenarios.py",
            "core/scripts/carla/policies/smpc_agent.py",
            "core/scripts/models/evaluate_prediction_model.py",
            "docs/REPOSITORY_CONTENT_MANIFEST.json",
        ]
        file_sizes = {path: 10 for path in tracked_paths}
        file_sizes["docs/REPOSITORY_CONTENT_MANIFEST.json"] = 999

        report = audit_paths(tracked_paths=tracked_paths, file_sizes=file_sizes)

        self.assertEqual(report["tracked_path_count"], len(tracked_paths))
        self.assertEqual(report["tracked_bytes"], 1069)
        self.assertEqual(report["tracked_bytes_excluded_paths"], [])

    def test_reports_missing_local_markdown_links_and_repository_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "docs").mkdir()
            (root / "docs" / "guide.md").write_text(
                "[present](../README.md)\n"
                "[missing](missing.md)\n"
                "Run `core/scripts/real.py`.\n"
                "Do not require `/path/to/CARLA`.\n",
                encoding="utf-8",
            )
            (root / "README.md").write_text("# Project\n", encoding="utf-8")
            (root / "core" / "scripts").mkdir(parents=True)
            (root / "core" / "scripts" / "real.py").write_text(
                "pass\n", encoding="utf-8"
            )

            findings = audit_markdown_links(root, ("docs/guide.md",))

            self.assertEqual(
                findings,
                [
                    {
                        "document": "docs/guide.md",
                        "target": "missing.md",
                        "kind": "markdown_link",
                    }
                ],
            )


if __name__ == "__main__":
    unittest.main()
