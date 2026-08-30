#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from materialize_future_mask_v4_paper_outputs import (  # noqa: E402
    PAPER_OUTPUTS_MANIFEST,
    produced_output_files,
)


class PaperOutputManifestIdempotencyTest(unittest.TestCase):
    def test_stale_manifest_is_never_included_in_its_own_files_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            output_dir = Path(temporary)
            (output_dir / "claim_decisions.csv").write_text("claim,status\n", encoding="utf-8")
            (output_dir / PAPER_OUTPUTS_MANIFEST).write_text("{}\n", encoding="utf-8")

            self.assertEqual(produced_output_files(output_dir), ["claim_decisions.csv"])


if __name__ == "__main__":
    unittest.main()
