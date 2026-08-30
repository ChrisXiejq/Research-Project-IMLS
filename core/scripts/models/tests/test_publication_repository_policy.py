from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from publication_repository_policy import audit_paths  # noqa: E402


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

    def test_accepts_core_and_compact_evidence(self) -> None:
        report = audit_paths(
            tracked_paths=[
                "README.md",
                "REPRODUCIBILITY.md",
                "CITATION.cff",
                "THIRD_PARTY_NOTICES.md",
                "core/scripts/carla/run_all_scenarios.py",
                "core/scripts/carla/policies/smpc_agent.py",
                "core/scripts/models/evaluate_thesis_core_cached_v3.py",
                "docs/paper/generated/future_mask_v4e_120/offline_synthesis.json",
            ],
            file_sizes={},
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["missing_required_paths"], [])
        self.assertEqual(report["forbidden_tracked_paths"], [])


if __name__ == "__main__":
    unittest.main()
