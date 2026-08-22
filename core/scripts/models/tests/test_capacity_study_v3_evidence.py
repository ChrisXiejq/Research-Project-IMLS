#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODELS_DIR))

from capacity_study_v3_evidence import (  # noqa: E402
    claim_record,
    validate_claim_text,
    write_placeholder_package,
)


class CapacityStudyV3EvidenceTests(unittest.TestCase):
    def test_unsupported_claim_language_is_rejected(self) -> None:
        for text in (
            "This predictor guarantees safety.",
            "The two methods are equivalent.",
            "Foundation mismatch caused the original result.",
            "The Transformer is always better.",
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                validate_claim_text(text)

    def test_completed_claim_requires_axis_specific_evidence_and_locators(self) -> None:
        locator = {"artifact": "analysis.json", "field": "x.effect", "unit": "nats/step"}
        with self.assertRaisesRegex(ValueError, "lacks required evidence"):
            claim_record(
                claim_id="C1",
                axis="architecture",
                text="Attention had a larger history gain in this setting.",
                evidence_ids=["architecture_direct_full_mlp_minus_transformer"],
                source_fields=[locator],
                completion_status="pass",
            )
        ready = claim_record(
            claim_id="C1",
            axis="architecture",
            text="Attention had a larger history gain in this setting.",
            evidence_ids=[
                "architecture_direct_full_mlp_minus_transformer",
                "H3_attention_history_gain_difference_in_differences",
            ],
            source_fields=[locator],
            completion_status="pass",
        )
        self.assertEqual(ready["status"], "ready")

    def test_pre_execution_package_contains_only_explicit_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = write_placeholder_package(tmp)
            self.assertFalse(report["numeric_prose_allowed"])
            markdown = Path(report["placeholders_markdown"]).read_text(encoding="utf-8")
            self.assertIn("RESULT PENDING", markdown)
            self.assertNotIn("0.00", markdown)


if __name__ == "__main__":
    unittest.main()
