"""Prediction and experiment tooling package."""

from __future__ import annotations

import sys
from pathlib import Path

_MODELS_DIR = Path(__file__).resolve().parent
for _package_name in (
    "analysis",
    "data",
    "experimental",
    "modeling",
    "training",
    "tools",
):
    _package_dir = _MODELS_DIR / _package_name
    _value = str(_package_dir)
    if _value not in sys.path:
        sys.path.insert(0, _value)
