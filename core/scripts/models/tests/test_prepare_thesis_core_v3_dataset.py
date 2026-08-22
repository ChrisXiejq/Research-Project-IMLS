#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from capacity_study_v3_protocol import THESIS_FIT_GROUPS, sha256_payload  # noqa: E402
from prepare_thesis_core_v3_dataset import (  # noqa: E402
    audit_rows,
    load_thesis_normalization,
    sample_key,
)


def row(group: int, cell: str, sample: int):
    return {"ego_init_id": group, "cell_id": cell, "sample_id": sample}


class PrepareThesisCoreDatasetTest(unittest.TestCase):
    def test_group_complete_split_is_disjoint(self):
        cells = ("S0_FIXED", "S0_ADAPTIVE", "S1_FIXED", "S1_ADAPTIVE")
        rows = {
            "fit": [row(group, cell, index) for group in range(1, 36) for index, cell in enumerate(cells)],
            "selection": [row(group, cell, index) for group in range(36, 41) for index, cell in enumerate(cells)],
            "heldout": [row(group, cell, index) for group in range(41, 46) for index, cell in enumerate(cells)],
        }
        report = audit_rows(rows)
        self.assertEqual(report["status"], "pass")
        self.assertTrue(all(value == 0 for value in report["sample_overlaps"].values()))
        self.assertEqual(sample_key(rows["fit"][0]), "1|S0_FIXED|0")

    def test_missing_cell_fails(self):
        cells = ("S0_FIXED", "S0_ADAPTIVE", "S1_FIXED", "S1_ADAPTIVE")
        rows = {
            "fit": [row(group, cell, index) for group in range(1, 36) for index, cell in enumerate(cells)],
            "selection": [row(group, cell, index) for group in range(36, 41) for index, cell in enumerate(cells)],
            "heldout": [row(group, cell, index) for group in range(41, 46) for index, cell in enumerate(cells)],
        }
        rows["heldout"].pop()
        with self.assertRaisesRegex(ValueError, "four-cell support"):
            audit_rows(rows)

    def test_normalization_loader_rejects_hash_or_group_drift(self):
        value = {
            "schema_version": "interaction_normalization_thesis_core_v3",
            "fit_groups": list(THESIS_FIT_GROUPS),
            "valid_token_count": 10,
            "minimum_std": 1.0e-6,
            "mean": [0.0] * 12,
            "std": [1.0] * 12,
        }
        payload = {**value, "normalization_sha256": sha256_payload(value)}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "normalization.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(load_thesis_normalization(path), payload)
            payload["fit_groups"] = list(range(2, 37))
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_thesis_normalization(path)


if __name__ == "__main__":
    unittest.main()
