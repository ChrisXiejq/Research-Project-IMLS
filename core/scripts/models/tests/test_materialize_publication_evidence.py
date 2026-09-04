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


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from materialize_publication_evidence import (  # noqa: E402
    PUBLICATION_EVIDENCE_MANIFEST,
    materialize_collection,
)


class PublicationEvidenceMaterializerTest(unittest.TestCase):
    def test_copies_allowlist_and_excludes_unlisted_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            output = root / "published"
            (source / "figures").mkdir(parents=True)
            (source / "logs").mkdir()
            (source / "figures" / "FIGURE_MANIFEST.json").write_text(
                "{}\n", encoding="utf-8"
            )
            (source / "logs" / "offline_pipeline.log").write_text(
                "private\n", encoding="utf-8"
            )

            report = materialize_collection(
                source,
                output,
                allowlist=("figures/",),
                collection_id="fixture",
            )

            self.assertEqual(report["status"], "pass")
            self.assertTrue((output / "figures" / "FIGURE_MANIFEST.json").is_file())
            self.assertFalse((output / "logs").exists())
            self.assertTrue((output / PUBLICATION_EVIDENCE_MANIFEST).is_file())
            self.assertEqual(len(report["files"]), 1)
            self.assertEqual(
                report["files"][0]["target_path"],
                "figures/FIGURE_MANIFEST.json",
            )

    def test_missing_allowlisted_path_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()

            with self.assertRaises(FileNotFoundError):
                materialize_collection(
                    source,
                    root / "published",
                    allowlist=("OFFLINE_AUDIT_COMPLETE.json",),
                    collection_id="fixture",
                )

    def test_rejects_symlink_inside_allowlisted_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "figures").mkdir(parents=True)
            external = root / "external.json"
            external.write_text(json.dumps({"private": True}), encoding="utf-8")
            (source / "figures" / "linked.json").symlink_to(external)

            with self.assertRaises(ValueError):
                materialize_collection(
                    source,
                    root / "published",
                    allowlist=("figures/",),
                    collection_id="fixture",
                )


if __name__ == "__main__":
    unittest.main()
