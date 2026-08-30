#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from capacity_study_v3_protocol import atomic_json, sha256_payload  # noqa: E402

try:  # The lightweight local CI image does not necessarily include Matplotlib.
    import plot_future_mask_v4_offline as plotting  # noqa: E402
except ModuleNotFoundError as error:  # pragma: no cover - exercised by minimal CI images
    if error.name != "matplotlib":
        raise
    plotting = None


def _contrasts(offset: float = 0.0):
    ids = (
        "H1_capacity_transformer_full_small_minus_large",
        "H2_information_mlp_snapshot_minus_full",
        "H2_information_transformer_snapshot_minus_full",
        "H3_attention_history_gain_difference_in_differences",
    )
    return [
        {
            "contrast_id": contrast_id,
            "effect": 0.001 * (index + 1) + offset,
            "cluster_interval_95": [
                0.001 * (index + 1) + offset - 0.0004,
                0.001 * (index + 1) + offset + 0.0004,
            ],
            "paired_init_effects": {
                str(init_id): 0.001 * (index + 1)
                + offset
                + (init_id - 43) * 0.00005
                for init_id in range(41, 46)
            },
        }
        for index, contrast_id in enumerate(ids)
    ]


def _payloads():
    if plotting is None:
        raise RuntimeError("Matplotlib test payload requested without Matplotlib")
    cells = []
    full_cells = []
    freeze_cells = []
    sequence_index = 0
    for cell_index, cell_id in enumerate(plotting.CELL_ORDER):
        per_seed = {
            str(seed): 3.9 + cell_index * 0.001 + seed_index * 0.0001
            for seed_index, seed in enumerate(plotting.SEEDS)
        }
        cells.append(
            {
                "model_cell_id": cell_id,
                "heldout_rollout_macro_nll_mean": sum(per_seed.values()) / 3.0,
                "per_seed": per_seed,
            }
        )
        full_seed = {str(seed): value + 0.01 for seed, value in per_seed.items()}
        full_cells.append(
            {
                "model_cell_id": cell_id,
                "full_horizon_rollout_macro_nll_mean": sum(full_seed.values()) / 3.0,
                "per_seed": full_seed,
            }
        )
        if cell_id == "head-large":
            freeze_cells.append(
                {
                    "model_cell_id": cell_id,
                    "median_validation_rollout_macro_nll": 4.0,
                    "seed_scores": {str(seed): 4.0 for seed in plotting.SEEDS},
                    "trainable_parameters": 1_000_000,
                    "median_warmed_batch_one_latency_ms": 10.0,
                    "latency_gate_pass": False,
                }
            )
            continue
        validation = 3.8 + sequence_index * 0.01
        freeze_cells.append(
            {
                "model_cell_id": cell_id,
                "median_validation_rollout_macro_nll": validation,
                "seed_scores": {
                    str(seed): validation + (seed_index - 1) * 0.0002
                    for seed_index, seed in enumerate(plotting.SEEDS)
                },
                "trainable_parameters": 200_000 + sequence_index * 100_000,
                "median_warmed_batch_one_latency_ms": 4.0 + sequence_index,
                "latency_gate_pass": True,
            }
        )
        sequence_index += 1

    freeze = {
        "schema_version": "capacity_history_thesis_core_selection_freeze_v3",
        "status": "pass",
        "selection_split": "groups_36_40",
        "heldout_split": "groups_41_45_retrospective",
        "heldout_access_authorized": True,
        "cells": freeze_cells,
        "P_star": {"model_cell_id": "mlp-h0p0-large"},
    }
    freeze["freeze_sha256"] = sha256_payload(freeze)
    offline = {
        "status": "pass",
        "selection_freeze_sha256": freeze["freeze_sha256"],
        "cell_summaries": cells,
        "three_axes": {"primary_contrasts": _contrasts()},
    }
    offline["synthesis_sha256"] = sha256_payload(offline)
    sensitivity = {
        "status": "pass",
        "cell_summaries": full_cells,
        "full_horizon_selection_recalibrated": {
            "three_axes": {"primary_contrasts": _contrasts(0.0002)}
        },
    }
    sensitivity["sensitivity_sha256"] = sha256_payload(sensitivity)
    impact = {
        "status": "pass",
        "rows": [
            {
                "model_cell_id": cell_id,
                "seed": seed,
                "old_uncalibrated_trajectory_mixture_NLL_per_step_mean": 4.1,
                "corrected_uncalibrated_trajectory_mixture_NLL_per_step_mean": 3.9,
                "old_uncalibrated_top1_ADE_mean": 1.1,
                "corrected_uncalibrated_top1_ADE_mean": 0.9,
                "old_uncalibrated_top1_FDE_mean": 2.0,
                "corrected_uncalibrated_top1_FDE_mean": 1.5,
            }
            for cell_id in plotting.CELL_ORDER
            for seed in plotting.SEEDS
        ],
    }
    impact["audit_sha256"] = sha256_payload(impact)
    return impact, offline, sensitivity, freeze


@unittest.skipUnless(plotting is not None, "Matplotlib is not installed")
class FutureMaskV4PlotTest(unittest.TestCase):
    def test_figures_are_dense_and_bound_to_validation_selection(self):
        impact, offline, sensitivity, freeze = _payloads()
        figures = []

        def capture(fig, _output, stem):
            figures.append((stem, fig))

        with mock.patch.object(plotting, "_save", side_effect=capture):
            plotting.plot_mask_impact(impact, Path("unused"))
            plotting.plot_corrected_cia(offline, sensitivity, Path("unused"))
            plotting.plot_selection_stability(offline, freeze, Path("unused"))

        by_name = dict(figures)
        impact_text = " ".join(text.get_text() for text in by_name["figure_mask_correction_impact"].texts)
        self.assertIn("Impact diagnosis only", impact_text)
        cia_axes = by_name["figure_corrected_capacity_information_architecture"].axes
        self.assertEqual(len(cia_axes), 4)
        self.assertTrue(all(len(axis.lines) >= 4 for axis in cia_axes[:3]))
        self.assertGreaterEqual(len(cia_axes[3].collections), 4)
        selection_axes = by_name["figure_selection_stability_v4_validation_frozen"].axes
        self.assertGreaterEqual(len(selection_axes[0].lines), 4)
        self.assertEqual(len(selection_axes[1].lines), 8)

        for _, figure in figures:
            plotting.plt.close(figure)

    def test_cli_generates_hash_bound_matplotlib_release(self):
        impact, offline, sensitivity, freeze = _payloads()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, payload in (
                ("impact.json", impact),
                ("offline.json", offline),
                ("sensitivity.json", sensitivity),
                ("freeze.json", freeze),
            ):
                atomic_json(root / name, payload)
            output = root / "figures"
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "plot_future_mask_v4_offline.py"),
                    "--impact-audit",
                    str(root / "impact.json"),
                    "--offline-synthesis",
                    str(root / "offline.json"),
                    "--full-horizon-sensitivity",
                    str(root / "sensitivity.json"),
                    "--selection-freeze",
                    str(root / "freeze.json"),
                    "--output-dir",
                    str(output),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            manifest = json.loads((output / "FIGURE_MANIFEST.json").read_text())
            self.assertEqual(manifest["generation_method"], "Python/Matplotlib")
            self.assertEqual(
                manifest["source_artifacts"]["selection_freeze_sha256"],
                freeze["freeze_sha256"],
            )
            self.assertEqual(len(manifest["files"]), 6)
            self.assertTrue(all((output / name).stat().st_size > 0 for name in manifest["files"]))

    def test_heldout_cannot_change_or_reconstruct_pstar(self):
        _, offline, _, freeze = _payloads()
        freeze["selection_split"] = "groups_41_45_retrospective"
        freeze["freeze_sha256"] = sha256_payload(
            {key: value for key, value in freeze.items() if key != "freeze_sha256"}
        )
        offline["selection_freeze_sha256"] = freeze["freeze_sha256"]
        with self.assertRaisesRegex(ValueError, "validation-only"):
            plotting._selection_candidates(offline, freeze)

    def test_selection_recomputation_respects_frozen_latency_gate(self):
        _, offline, _, freeze = _payloads()
        selected = "mlp-h0p4-large"
        for cell in freeze["cells"]:
            cell["latency_gate_pass"] = cell["model_cell_id"] == selected
        freeze["P_star"]["model_cell_id"] = selected
        freeze["freeze_sha256"] = sha256_payload(
            {key: value for key, value in freeze.items() if key != "freeze_sha256"}
        )
        offline["selection_freeze_sha256"] = freeze["freeze_sha256"]

        candidates, recomputed = plotting._selection_candidates(offline, freeze)

        self.assertEqual(recomputed, selected)
        self.assertEqual(sum(row["latency_gate_pass"] for row in candidates), 1)


if __name__ == "__main__":
    unittest.main()
