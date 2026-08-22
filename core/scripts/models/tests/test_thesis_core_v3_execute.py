#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from thesis_core_v3_runs import shard_runs, thesis_core_runs  # noqa: E402


class ThesisCoreV3ExecuteTest(unittest.TestCase):
    def test_six_shards_cover_without_duplicates_and_resume_order_is_stable(self):
        runs = thesis_core_runs()
        shards = [shard_runs(runs, index, 6) for index in range(6)]
        identifiers = [row.run_id for shard in shards for row in shard]
        self.assertEqual(len(identifiers), 27)
        self.assertEqual(len(set(identifiers)), 27)
        for index, shard in enumerate(shards):
            self.assertEqual(shard, shard_runs(runs, index, 6))


if __name__ == "__main__":
    unittest.main()
