#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import copy
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from thesis_core_v3_runs import (  # noqa: E402
    DOSE_RESPONSE_CELL_IDS,
    ENDPOINT_CELL_IDS,
    missing_thesis_runs,
    shard_runs,
    thesis_core_manifest,
    thesis_core_runs,
    validate_thesis_core_manifest,
)


class ThesisCoreV3RunsTest(unittest.TestCase):
    def test_exact_grid_and_primary_coverage(self):
        runs = thesis_core_runs()
        self.assertEqual(len(runs), 27)
        self.assertEqual(len({row.run_id for row in runs}), 27)
        self.assertEqual({row.learning_rate for row in runs}, {1.0e-4})
        self.assertEqual({row.seed for row in runs}, {11, 23, 37})
        self.assertEqual({row.model_cell_id for row in runs}, set(ENDPOINT_CELL_IDS + DOSE_RESPONSE_CELL_IDS))
        self.assertEqual(sum(row.model_cell_id in ENDPOINT_CELL_IDS for row in runs), 21)
        self.assertEqual(sum(row.model_cell_id in DOSE_RESPONSE_CELL_IDS for row in runs), 6)

    def test_manifest_and_six_shards_are_deterministic_and_disjoint(self):
        payload = thesis_core_manifest()
        self.assertEqual(validate_thesis_core_manifest(payload)["planned_runs"], 27)
        altered = copy.deepcopy(payload)
        altered["runs"][0]["seed"] = 99
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_thesis_core_manifest(altered)
        runs = thesis_core_runs()
        shards = [shard_runs(runs, index, 6) for index in range(6)]
        flattened = [row.run_id for shard in shards for row in shard]
        self.assertEqual(len(flattened), 27)
        self.assertEqual(len(set(flattened)), 27)
        self.assertEqual(set(flattened), {row.run_id for row in runs})

    def test_resume_rejects_unknown_and_returns_only_missing(self):
        runs = thesis_core_runs()
        completed = [row.run_id for row in runs[:4]]
        self.assertEqual(len(missing_thesis_runs(runs, completed)), 23)
        with self.assertRaisesRegex(ValueError, "unknown thesis run"):
            missing_thesis_runs(runs, ["unknown"])


if __name__ == "__main__":
    unittest.main()
