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
import sys
import tempfile
import unittest
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(MODELS_DIR / "experimental"))

from generate_capacity_history_v3_results import (  # noqa: E402
    build_offline_tables,
    build_scalar_index,
    validate_evidence_chain,
    write_capacity_svg,
    write_final_package,
)


class GenerateCapacityHistoryV3ResultsTests(unittest.TestCase):
    def test_real_evidence_chain_rebuilds_every_final_figure(self) -> None:
        repo = Path(__file__).resolve().parents[4]
        results_root = repo / "docs/paper/generated/capacity_history_v3/results"
        expected_figures = {
            "figure_capacity_curve.svg",
            "figure_history_architecture.svg",
            "figure_model_by_risk.svg",
            "figure_history_gain_interaction.svg",
            "figure_latency_pareto.svg",
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            report = write_final_package(results_root=results_root, output_dir=output)
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["figures"], len(expected_figures))
            self.assertEqual(
                {path.name for path in output.glob("figure_*.svg")}, expected_figures
            )
            for filename in expected_figures:
                self.assertGreater((output / filename).stat().st_size, 1_000)
            history_svg = (output / "figure_history_architecture.svg").read_text(
                encoding="utf-8"
            )
            latency_svg = (output / "figure_latency_pareto.svg").read_text(
                encoding="utf-8"
            )
            self.assertIn("History horizon and encoder comparison", history_svg)
            self.assertIn("Accuracy latency Pareto plot", latency_svg)
            self.assertNotIn("History horizon and encoder comparison", latency_svg)

    def test_offline_table_preserves_evidence_status_and_seed_values(self) -> None:
        payload = {
            "evidence_status": "retrospective_held_out",
            "cell_summaries": [
                {
                    "model_cell_id": "transformer-h1p0-small",
                    "history_horizon_s": 1.0,
                    "trainable_parameters": 167384,
                    "selection_median_rollout_macro_nll": 4.5,
                    "heldout_rollout_macro_nll_mean": 3.9,
                    "heldout_rollout_macro_nll_seed_sd": 0.01,
                    "per_seed": {"11": 3.89, "23": 3.90, "37": 3.91},
                }
            ],
            "three_axes": {"primary_contrasts": []},
            "direct_architecture_contrasts": [],
            "supporting_contrasts": [],
        }
        table = build_offline_tables(payload)["cells"]
        self.assertEqual(table[0]["seed_23_nll"], 3.90)
        self.assertEqual(table[0]["evidence_status"], "retrospective_held_out")

    def test_capacity_svg_is_line_only_and_declares_non_monotonic_result(self) -> None:
        cells = []
        for tier, parameters, mean in (
            ("small", 167384, 3.9168),
            ("medium", 497840, 3.9154),
            ("large", 1026816, 3.9163),
        ):
            cells.append(
                {
                    "model_cell_id": f"transformer-h1p0-{tier}",
                    "trainable_parameters": parameters,
                    "heldout_rollout_macro_nll_mean": mean,
                    "heldout_rollout_macro_nll_seed_sd": 0.0008,
                }
            )
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "capacity.svg"
            write_capacity_svg(output, cells)
            svg = output.read_text(encoding="utf-8")
            self.assertIn('class="transformer series-line"', svg)
            self.assertIn("non-monotonic", svg)
            self.assertNotIn("<polygon", svg)

    def test_scalar_index_assigns_source_unit_and_independent_units(self) -> None:
        rows = {
            "offline_contrasts": [
                {
                    "contrast_id": "H1",
                    "metric": "rollout_macro_nll",
                    "effect": 0.01,
                    "independent_groups": 5,
                    "evidence_status": "retrospective_held_out",
                }
            ]
        }
        indexed = build_scalar_index(rows)
        effect = next(row for row in indexed if row["field"] == "effect")
        self.assertEqual(effect["unit"], "nats per valid prediction step")
        self.assertEqual(effect["independent_unit_count"], 5)
        self.assertIn("offline_synthesis.json", effect["source_artifact"])

    def test_completion_gate_hash_drift_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {name: root / f"{name}.json" for name in ("offline", "audit", "freeze", "closed", "rows", "gate")}
            primary = [
                {"contrast_id": identifier}
                for identifier in (
                    "H1_capacity_transformer_full_small_minus_large",
                    "H2_information_mlp_snapshot_minus_full",
                    "H2_information_transformer_snapshot_minus_full",
                    "H3_attention_history_gain_difference_in_differences",
                )
            ]
            payloads = {
                "offline": {
                    "status": "pass",
                    "evidence_status": "retrospective_held_out",
                    "selection_freeze_sha256": "freeze",
                    "evaluated_runs": 27,
                    "independent_init_groups": 5,
                    "three_axes": {"primary_contrasts": primary},
                },
                "audit": {
                    "status": "pass",
                    "planned_runs": 27,
                    "valid_runs": 27,
                    "invalid_runs_or_gates": [],
                    "audit_sha256": "audit",
                },
                "freeze": {
                    "status": "pass",
                    "heldout_access_authorized": True,
                    "freeze_sha256": "freeze",
                    "training_audit_sha256": "audit",
                },
                "closed": {"status": "pass", "independent_groups": 10},
                "rows": [{} for _ in range(80)],
                "gate": {
                    "status": "pass",
                    "formal_evidence": True,
                    "observed_rollouts": 80,
                    "artifact_sha256": {"synthesis": "wrong", "rows": "wrong"},
                },
            }
            for name, payload in payloads.items():
                paths[name].write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "synthesis hash"):
                validate_evidence_chain(
                    offline_path=paths["offline"],
                    audit_path=paths["audit"],
                    freeze_path=paths["freeze"],
                    closed_loop_path=paths["closed"],
                    closed_loop_rows_path=paths["rows"],
                    closed_loop_gate_path=paths["gate"],
                )


if __name__ == "__main__":
    unittest.main()
