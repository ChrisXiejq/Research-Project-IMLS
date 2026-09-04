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

from analyze_day10_closed_loop import describe_contrast


class Day10ClusterAnalysisTest(unittest.TestCase):
    def test_repeated_styles_are_aggregated_within_five_inits(self) -> None:
        deltas = [1.0] * 5 + [3.0] * 5
        init_ids = list(range(46, 51)) + list(range(46, 51))
        result = describe_contrast(
            "fixture",
            "fixture_scope",
            "pooled_styles",
            "metric",
            deltas,
            init_ids,
            "left",
            "right",
        )
        self.assertEqual(result["condition_pairs"], 10)
        self.assertEqual(result["independent_init_groups"], 5)
        self.assertEqual(result["mean_delta_a_minus_b"], 2.0)
        self.assertEqual(result["exact_init_cluster_sign_flip_p"], 0.0625)


if __name__ == "__main__":
    unittest.main()
