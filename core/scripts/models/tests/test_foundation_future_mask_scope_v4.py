from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import json
import tempfile
import unittest
from pathlib import Path

from audit_foundation_future_mask_scope_v4 import audit
from capacity_study_v3_protocol import sha256_file


class FoundationMaskScopeAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.validation = self.root / "val.jsonl"
        self.test = self.root / "test.jsonl"
        self._write_split(self.validation, full=326, partial_each=20)
        self._write_split(self.test, full=315, partial_each=20)
        self.source = self.root / "legacy.py"
        self.source.write_text(
            "if not has_full_horizon(sample, horizon=horizon):\n"
            "    continue\n",
            encoding="utf-8",
        )
        self.b0_validation = self.root / "b0_validation.json"
        self.b0_test = self.root / "b0_test.json"
        self.b1_test = self.root / "b1_test.json"
        self._write_evaluation(self.b0_validation, self.validation, 326, calibration=True)
        self._write_evaluation(self.b0_test, self.test, 315)
        self._write_evaluation(self.b1_test, self.test, 315)
        self.summary = self.root / "summary.json"
        self._write_summary()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_split(path: Path, *, full: int, partial_each: int) -> None:
        rows = [{"future_valid_mask": [1] * 10} for _ in range(full)]
        for length in range(1, 10):
            rows.extend(
                {"future_valid_mask": [1] * length + [0] * (10 - length)}
                for _ in range(partial_each)
            )
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )

    @staticmethod
    def _write_evaluation(
        path: Path, jsonl: Path, samples: int, *, calibration: bool = False
    ) -> None:
        payload = {
            "status": "pass",
            "horizon": 10,
            "samples": samples,
            "subset": "all",
            "jsonl": {
                "path": str(jsonl),
                "bytes": jsonl.stat().st_size,
                "sha256": sha256_file(jsonl),
            },
            "top1_ADE_mean": 1.0,
            "top1_FDE_mean": 2.0,
            "uncalibrated": {"trajectory_mixture_NLL_per_step_mean": 3.0},
        }
        if calibration:
            payload["calibration"] = {"samples": samples}
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _write_summary(self) -> None:
        payload = {
            "status": "pass",
            "test_used_for_selection": False,
            "source_sha256": {"b0_test_all": sha256_file(self.b0_test)},
            "subsets": {
                "all": {"B0": {"samples": 315}, "B1": {"samples": 315}}
            },
        }
        self.summary.write_text(json.dumps(payload), encoding="utf-8")

    def _args(self) -> argparse.Namespace:
        return argparse.Namespace(
            validation_jsonl=self.validation,
            test_jsonl=self.test,
            b0_validation_evaluation=self.b0_validation,
            b0_test_evaluation=self.b0_test,
            b1_test_evaluation=self.b1_test,
            b0_summary=self.summary,
            legacy_evaluator_source=self.source,
            output=self.root / "audit.json",
        )

    def test_full_horizon_foundation_is_outside_bug_scope(self) -> None:
        result = audit(self._args())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            result["evaluated_membership"]["partial_windows_entered_foundation_metrics"],
            0,
        )

    def test_partial_window_inclusion_fails_closed(self) -> None:
        self._write_evaluation(self.b1_test, self.test, 495)
        with self.assertRaisesRegex(ValueError, "B1 test"):
            audit(self._args())


if __name__ == "__main__":
    unittest.main()
