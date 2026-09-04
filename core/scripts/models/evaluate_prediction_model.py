#!/usr/bin/env python3
"""Maintained entry point for predictor evaluation."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent
EXPERIMENTAL_DIR = MODELS_DIR / "experimental"
sys.path.insert(0, str(EXPERIMENTAL_DIR))
sys.path.insert(0, str(MODELS_DIR))

runpy.run_path(
    str(EXPERIMENTAL_DIR / "evaluate_thesis_core_cached_v3.py"),
    run_name="__main__",
)
