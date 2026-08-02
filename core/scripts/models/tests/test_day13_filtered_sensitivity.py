#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from analyze_day13_filtered_sensitivity import analyze
from prepare_day13_collision_filtered_dataset import build


VARIANTS = ("B1", "B2-M", "B2-D", "T1", "T2")
SEEDS = (11, 23, 37)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def sample(cell: str, subrun: str, value: float = 1.0) -> dict:
    return {
        "cell_id": cell,
        "source_cell": cell,
        "source_subrun": subrun,
        "interaction_sequence": [[value] * 12 for _ in range(6)],
        "interaction_sequence_mask": [1] * 6,
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class Day13FilteredDatasetTest(unittest.TestCase):
    def test_training_filter_preserves_holdouts_and_recomputes_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            day7 = root / "day7"
            day7.mkdir()
            write_json(day7 / "DAY7_COMPLETE.json", {"status": "pass"})
            write_json(
                day7 / "DAY7_MODEL_IMPLEMENTATION_COMPLETE.json",
                {"status": "pass", "model_smoke_report_sha256": "abc"},
            )
            excluded = [
                ("S1_FIXED", "scenario_uk_give_way_ego_init_08_smpc_fixed_risk"),
                ("S1_FIXED", "scenario_uk_give_way_ego_init_10_smpc_fixed_risk"),
                ("S1_ADAPTIVE", "scenario_uk_give_way_ego_init_07_smpc_var_risk"),
                ("S1_ADAPTIVE", "scenario_uk_give_way_ego_init_10_smpc_var_risk"),
                ("S1_ADAPTIVE", "scenario_uk_give_way_ego_init_19_smpc_var_risk"),
                ("S1_ADAPTIVE", "scenario_uk_give_way_ego_init_27_smpc_var_risk"),
            ]
            keep = sample("S0_FIXED", "scenario_uk_give_way_ego_init_01_smpc_fixed_risk", 2.0)
            train = [sample(cell, subrun) for cell, subrun in excluded] + [keep]
            val = [sample("S0_FIXED", "scenario_uk_give_way_ego_init_41_smpc_fixed_risk")]
            test = [sample("S0_FIXED", "scenario_uk_give_way_ego_init_46_smpc_fixed_risk")]
            write_jsonl(day7 / "train.jsonl", train)
            write_jsonl(day7 / "val.jsonl", val)
            write_jsonl(day7 / "test.jsonl", test)
            write_jsonl(day7 / "all.jsonl", train + val + test)

            audit_path = root / "collision.json"
            write_json(
                audit_path,
                {
                    "status": "pass",
                    "sensitivity_decision": {
                        "decision": "material_reactive_train_overlap_full_filtered_matrix_review"
                    },
                    "totals": {"affected_usable_windows": 6},
                },
            )
            rollouts_path = root / "rollouts.csv"
            with rollouts_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("cell", "scenario_dir", "split", "collision_callbacks"),
                )
                writer.writeheader()
                for cell, subrun in excluded:
                    writer.writerow(
                        {
                            "cell": cell,
                            "scenario_dir": subrun,
                            "split": "train",
                            "collision_callbacks": 1,
                        }
                    )
            output = root / "filtered"
            result = build(day7, audit_path, rollouts_path, output)
            self.assertEqual(result["status"], "pass")
            retained = list(json.loads(line) for line in (output / "train.jsonl").read_text().splitlines())
            self.assertEqual(len(retained), 1)
            self.assertEqual(retained[0]["source_subrun"], keep["source_subrun"])
            self.assertEqual((output / "val.jsonl").read_bytes(), (day7 / "val.jsonl").read_bytes())
            self.assertEqual((output / "test.jsonl").read_bytes(), (day7 / "test.jsonl").read_bytes())
            normalization = json.loads((output / "interaction_normalization_train.json").read_text())
            self.assertEqual(normalization["mean"], [2.0] * 12)


class Day13SensitivityAnalysisTest(unittest.TestCase):
    @staticmethod
    def summary(filtered: bool) -> dict:
        runs = []
        ranking = []
        for rank, variant in enumerate(VARIANTS, 1):
            base = float(rank) + (0.1 if filtered else 0.0)
            ranking.append(
                {
                    "variant": variant,
                    "median_validation_rollout_macro_NLL": base,
                    "representative_seed": 23,
                }
            )
            for seed in SEEDS:
                runs.append(
                    {
                        "variant": variant,
                        "seed": seed,
                        "subsets": {
                            "all": {
                                "uncalibrated_rollout_macro_trajectory_NLL_per_step": base
                            },
                            "reactive": {"top1_ADE_mean": base / 10.0},
                        },
                    }
                )
        return {
            "status": "pass",
            "test_accessed": False,
            "observed_runs": 15,
            "provisional_selected_variant": "B1",
            "variant_ranking": ranking,
            "runs": runs,
        }

    def test_matched_validation_only_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original = root / "original.json"
            filtered = root / "filtered.json"
            audit = root / "audit.json"
            write_json(original, self.summary(False))
            write_json(filtered, self.summary(True))
            write_json(
                audit,
                {
                    "status": "pass",
                    "test_accessed_for_selection": False,
                    "counts": {"excluded_train_usable": 6},
                },
            )
            result = analyze(original, filtered, audit, root / "analysis")
            self.assertTrue(result["selected_architecture_stable"])
            self.assertFalse(result["test_accessed"])
            self.assertEqual(result["matched_runs"], 15)


if __name__ == "__main__":
    unittest.main()
