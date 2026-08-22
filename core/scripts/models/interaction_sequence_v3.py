#!/usr/bin/env python3
"""History-horizon controls layered over the frozen V2 interaction schema."""

from __future__ import annotations

from typing import Any, Iterable, Iterator

import numpy as np

from capacity_study_v3_protocol import HISTORY_HORIZONS_S, HISTORY_MASKS


def has_complete_interaction_history(mask: Iterable[float]) -> bool:
    values = np.asarray(list(mask), dtype=np.float32)
    return values.shape == (6,) and bool(np.all(values == 1.0))


def apply_history_horizon(
    sequence: Any,
    mask: Any,
    history_horizon_s: float,
    *,
    require_complete: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply a frozen horizon without changing the six-slot tensor contract."""

    if history_horizon_s not in HISTORY_HORIZONS_S:
        raise ValueError(f"Unsupported history horizon: {history_horizon_s}")
    values = np.asarray(sequence, dtype=np.float32)
    valid = np.asarray(mask, dtype=np.float32)
    if values.shape != (6, 12) or valid.shape != (6,):
        raise ValueError(
            f"Expected sequence (6,12) and mask (6,), got {values.shape}/{valid.shape}"
        )
    if not np.all(np.isin(valid, [0.0, 1.0])):
        raise ValueError("Interaction mask must be binary")
    if require_complete and not has_complete_interaction_history(valid):
        raise ValueError("V3 matched-horizon study requires complete six-token history")
    fixed = np.asarray(HISTORY_MASKS[history_horizon_s], dtype=np.float32)
    horizon_mask = valid * fixed
    return values * horizon_mask[:, None], horizon_mask


def eligible_sample_ids(samples: Iterable[dict[str, Any]]) -> list[str]:
    identifiers = []
    for sample in samples:
        if has_complete_interaction_history(sample.get("interaction_sequence_mask", [])):
            identifiers.append(str(sample["sample_id"]))
    return identifiers


def horizon_samples(
    samples: Iterable[dict[str, Any]], history_horizon_s: float
) -> Iterator[dict[str, Any]]:
    for sample in samples:
        if not has_complete_interaction_history(sample.get("interaction_sequence_mask", [])):
            continue
        sequence, mask = apply_history_horizon(
            sample["interaction_sequence"],
            sample["interaction_sequence_mask"],
            history_horizon_s,
        )
        result = dict(sample)
        result["interaction_sequence"] = sequence.tolist()
        result["interaction_sequence_mask"] = mask.tolist()
        result["history_horizon_s"] = history_horizon_s
        yield result
