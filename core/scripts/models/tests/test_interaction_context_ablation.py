#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from interaction_context_ablation import prepare_interaction_ablation


def fixture(init_id: int, sample_id: int) -> tuple:
    sample = {
        "cell_id": "fixture",
        "source_subrun": f"ego_init_{init_id:02d}",
        "sample_id": str(sample_id),
        "ego_init_id": init_id,
        "interaction_sequence": [[100.0 + init_id] * 12 for _ in range(6)],
        "interaction_sequence_mask": [1.0, 1.0, 1.0, 0.0, 0.0, 0.0],
    }
    return sample, "raster", "past", "future"


class InteractionContextAblationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.items = [fixture(init_id, sample_id) for init_id in (1, 2) for sample_id in range(3)]
        self.mean = [float(value) for value in range(12)]

    def test_zero_uses_train_mean_and_retains_mask(self) -> None:
        output, metadata = prepare_interaction_ablation(
            self.items, mode="zero", seed=7, normalization_mean=self.mean
        )
        self.assertEqual(output[0][0]["interaction_sequence"][0], self.mean)
        self.assertEqual(
            output[0][0]["interaction_sequence_mask"],
            self.items[0][0]["interaction_sequence_mask"],
        )
        self.assertEqual(output[0][1:], self.items[0][1:])
        self.assertTrue(metadata["applied"])

    def test_shuffle_is_deterministic_and_cross_init(self) -> None:
        first, first_metadata = prepare_interaction_ablation(
            self.items, mode="shuffle", seed=7, normalization_mean=self.mean
        )
        second, second_metadata = prepare_interaction_ablation(
            self.items, mode="shuffle", seed=7, normalization_mean=self.mean
        )
        self.assertEqual(first_metadata["mapping_sha256"], second_metadata["mapping_sha256"])
        self.assertEqual(first, second)
        for item in first:
            receiver_init = item[0]["ego_init_id"]
            donor_marker = item[0]["interaction_sequence"][0][0] - 100.0
            self.assertNotEqual(receiver_init, donor_marker)
        self.assertTrue(first_metadata["cross_init_donors"])


if __name__ == "__main__":
    unittest.main()
