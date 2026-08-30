#!/usr/bin/env python3
"""Run the thesis-core integrity audit under the uniform 120-epoch amendment."""

from __future__ import annotations

import capacity_study_v3_protocol as protocol
import audit_thesis_core_v3_training as audit_module


if protocol.EXTENDED_EPOCHS != 120:
    raise RuntimeError("The frozen extended budget must remain 120 epochs")

audit_module.CORE_EPOCHS = protocol.EXTENDED_EPOCHS


if __name__ == "__main__":
    audit_module.main()
