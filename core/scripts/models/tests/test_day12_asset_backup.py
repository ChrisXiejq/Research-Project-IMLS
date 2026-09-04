#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from package_day12_critical_assets import atomic_copy, atomic_tar, valid_existing


class Day12AssetBackupTest(unittest.TestCase):
    def test_atomic_bundle_is_checksum_guarded_and_resumable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_text("immutable evidence\n", encoding="utf-8")
            archive = root / "bundle.tar.gz"
            atomic_tar(archive, [(source, "evidence/source.txt")])
            self.assertTrue(valid_existing(archive))
            first_hash = archive.with_suffix(archive.suffix + ".sha256").read_text()
            atomic_tar(archive, [(source, "evidence/source.txt")])
            self.assertEqual(first_hash, archive.with_suffix(archive.suffix + ".sha256").read_text())

    def test_atomic_copy_has_matching_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.bin"
            source.write_bytes(b"snapshot")
            destination = root / "copied.bin"
            atomic_copy(source, destination)
            self.assertTrue(valid_existing(destination))
            self.assertEqual(destination.read_bytes(), b"snapshot")


if __name__ == "__main__":
    unittest.main()
