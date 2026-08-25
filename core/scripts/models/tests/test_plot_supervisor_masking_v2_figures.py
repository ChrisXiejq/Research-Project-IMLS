from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

from core.scripts.models.plot_supervisor_masking_v2_figures import AuditedEvidence, build_release


ROOT = Path(__file__).resolve().parents[4]


class SupervisorMaskingV2FigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.output = Path(cls._tmp.name) / "release"
        cls.manifest = build_release(ROOT, cls.output)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_required_figures_and_comparators(self) -> None:
        self.assertEqual(self.manifest["status"], "pass")
        self.assertEqual(len(self.manifest["figures"]), 4)
        self.assertTrue(self.manifest["checks"]["h3_all_12_comparators_visible"])
        self.assertTrue(self.manifest["checks"]["shadow_figure_omitted_without_aligned_evidence"])
        for figure in self.manifest["figures"]:
            self.assertGreaterEqual(figure["legend_count"], 1)
            self.assertTrue(figure["units"])
            self.assertEqual({Path(row["path"]).suffix for row in figure["files"]}, {".pdf", ".png"})

    def test_figure_audit_covers_rendering_contract(self) -> None:
        audit = json.loads((self.output / "FIGURE_AUDIT.json").read_text(encoding="utf-8"))
        self.assertEqual(audit["status"], "pass")
        for name in (
            "raster_width_at_least_manuscript_width",
            "vector_font_embedding_requested",
            "single_declared_font_family",
            "restrained_colour_palette",
            "explicit_legend_each_figure",
            "explicit_units_each_figure",
        ):
            self.assertTrue(audit["checks"][name], name)

    def test_scalar_tables_are_provenance_complete(self) -> None:
        self.assertEqual(len(self.manifest["tables"]), 7)
        for filename in ("table_predictor_transfer.csv", "table_risk_transfer.csv", "table_solver_paths.csv"):
            with (self.output / "tables" / filename).open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertTrue(rows)
            self.assertTrue(all(row["source_locator"] for row in rows))
            self.assertTrue(all(row["aggregation_unit"] for row in rows))
            self.assertTrue(all(row["unit"] for row in rows))

    def test_unmanifested_raw_source_fails_closed(self) -> None:
        store = AuditedEvidence(ROOT)
        with self.assertRaisesRegex(ValueError, "not in the audited evidence manifest"):
            store.source("README.md", "unlicensed test input")


if __name__ == "__main__":
    unittest.main()
