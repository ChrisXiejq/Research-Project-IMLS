#!/usr/bin/env python3
"""Uniform 120-epoch amendment for the masked thesis-core matrix.

This wrapper deliberately changes only the maximum epoch budget.  It records
its own source hash in every run config and reuses the original trainer's
optimizer, loss, mask, early-stopping and checkpoint-selection semantics.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

from pathlib import Path

import capacity_study_v3_protocol as protocol


if protocol.EXTENDED_EPOCHS != 120:
    raise RuntimeError("The frozen extended budget must remain 120 epochs")

import train_thesis_core_cached_v3 as trainer  # noqa: E402


# Keep ``protocol.CORE_EPOCHS`` at the original frozen value (80).  The
# manifest validator constructs the original 27-run grid from that value, so
# mutating the protocol module would incorrectly redefine the frozen manifest.
# The signed extension protocol amends only the trainer's execution budget.
trainer.CORE_EPOCHS = protocol.EXTENDED_EPOCHS
trainer.TRAINING_SOURCE_FILES = tuple(
    dict.fromkeys((*trainer.TRAINING_SOURCE_FILES, Path(__file__).name))
)


if __name__ == "__main__":
    trainer.main()
