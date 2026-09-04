#!/usr/bin/env python3
"""Run the thesis-core integrity audit under the uniform 120-epoch amendment."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import capacity_study_v3_protocol as protocol
import audit_thesis_core_v3_training as audit_module


if protocol.EXTENDED_EPOCHS != 120:
    raise RuntimeError("The frozen extended budget must remain 120 epochs")

audit_module.CORE_EPOCHS = protocol.EXTENDED_EPOCHS


if __name__ == "__main__":
    audit_module.main()
