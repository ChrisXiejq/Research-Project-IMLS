#!/usr/bin/env python3

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import json
import tempfile
import unittest
from pathlib import Path

from core.scripts.models.experimental.build_r3_paper_synthesis import build


class R3PaperSynthesisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo = Path(__file__).resolve().parents[4]
        cls.r3 = cls.repo / "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/server_runs/r3_corrected_formal_v3"

    def test_frozen_r3_builds_deterministic_paper_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first_path, second_path = Path(first), Path(second)
            first_payload = build(self.repo, self.r3, first_path)
            second_payload = build(self.repo, self.r3, second_path)
            self.assertEqual(first_payload, second_payload)
            self.assertEqual(first_payload["status"], "pass")
            self.assertFalse(first_payload["additional_large_scale_carla_required"])
            self.assertEqual(first_payload["prediction_manipulation"], {"all_init_better_checks": 40, "checks": 40})
            self.assertEqual(first_payload["h3"]["directionally_supported_cells"], 2)
            self.assertEqual(first_payload["h3"]["prespecified_cells"], 8)
            self.assertEqual(first_payload["h4"]["dominance_cells"], 3)
            self.assertEqual(first_payload["h4"]["prespecified_cells"], 12)
            self.assertEqual(first_payload["binary_failure_total_across_contrasts"], 0)
            for filename in (*first_payload["artifacts"], "A2_COMPLETE.json"):
                self.assertEqual((first_path / filename).read_bytes(), (second_path / filename).read_bytes())
            marker = json.loads((first_path / "A2_COMPLETE.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["study_stop_decision"], "stop_formal_large_scale_collection")


if __name__ == "__main__":
    unittest.main()
