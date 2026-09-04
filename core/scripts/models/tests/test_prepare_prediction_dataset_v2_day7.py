#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
PREPARE = SCRIPT_DIR / "experimental/prepare_prediction_dataset_v2_day7.py"
CELLS = ("S0_FIXED", "S0_ADAPTIVE", "S1_FIXED", "S1_ADAPTIVE")


class Day7PrepareTest(unittest.TestCase):
    def test_grouped_split_filter_and_train_only_normalization(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            day6 = root / "day6"
            day7 = root / "day7"
            day6.mkdir()
            (day6 / "DAY6_COMPLETE.json").write_text(
                json.dumps({"status": "pass", "rollout_count": 200})
            )
            for cell_index, cell in enumerate(CELLS):
                target_style = "assertive_constant_speed" if cell.startswith("S0_") else "defensive_reactive"
                ego_policy = "fixed_medium" if cell.endswith("FIXED") else "adaptive_floor_weak"
                policy = "smpc_fixed_risk" if cell.endswith("FIXED") else "smpc_var_risk"
                for init_id in range(1, 51):
                    subrun = f"scenario_uk_give_way_ego_init_{init_id:02d}_{policy}"
                    prediction = day6 / cell / subrun / "prediction_dataset"
                    rasters = prediction / "rasters"
                    rasters.mkdir(parents=True)
                    (rasters / "sample.png").write_bytes(b"fixture")
                    rows = []
                    for sample_id, future_mask in enumerate(
                        ([1] * 10, [1, 1, 1] + [0] * 7, [0] * 10)
                    ):
                        sequence = [
                            [float(token + feature + init_id + cell_index) for feature in range(12)]
                            for token in range(6)
                        ]
                        rows.append(
                            {
                                "dataset_version": "give_way_interaction_prediction_v2.0",
                                "protocol_id": "town05_give_way_2x2_200_rollouts_v1",
                                "cell_id": cell,
                                "ego_init_id": init_id,
                                "target_style": target_style,
                                "ego_policy": ego_policy,
                                "sample_id": sample_id,
                                "interaction_sequence": sequence,
                                "interaction_sequence_mask": [1] * 6,
                                "future_valid_mask": future_mask,
                                "raster_relpath": "rasters/sample.png",
                            }
                        )
                    (prediction / "prediction_dataset_labeled.jsonl").write_text(
                        "".join(json.dumps(row) + "\n" for row in rows)
                    )
            subprocess.run(
                [
                    sys.executable,
                    str(PREPARE),
                    "--day6-results",
                    str(day6),
                    "--output-dir",
                    str(day7),
                ],
                check=True,
                text=True,
                capture_output=True,
            )
            audit = json.loads((day7 / "day7_split_audit.json").read_text())
            self.assertEqual(audit["status"], "pass")
            self.assertEqual(audit["rollouts_by_split"], {"train": 160, "val": 20, "test": 20})
            self.assertEqual(audit["raw_sample_counts"]["all"], 600)
            self.assertEqual(audit["usable_any_label_counts"]["all"], 400)
            self.assertEqual(audit["full_horizon_counts"]["all"], 200)
            self.assertEqual(audit["partial_horizon_counts"]["all"], 200)
            self.assertEqual(audit["zero_label_excluded_counts"]["all"], 200)
            with (day7 / "train.jsonl").open() as handle:
                self.assertEqual(sum(1 for _ in handle), 320)
            normalization = json.loads(
                (day7 / "interaction_normalization_train.json").read_text()
            )
            self.assertEqual(normalization["fit_split"], "train")
            self.assertEqual(normalization["count_per_feature"], [1920] * 12)
            self.assertTrue((day7 / "DAY7_COMPLETE.json").is_file())


if __name__ == "__main__":
    unittest.main()
