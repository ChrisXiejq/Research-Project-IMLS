"""Historical experiment-process modules kept for reproducibility."""

from __future__ import annotations

import sys
from pathlib import Path

_EXPERIMENTAL_DIR = Path(__file__).resolve().parent
_MODELS_DIR = _EXPERIMENTAL_DIR.parent

for _directory in (_EXPERIMENTAL_DIR, _MODELS_DIR):
    _value = str(_directory)
    if _value not in sys.path:
        sys.path.insert(0, _value)
