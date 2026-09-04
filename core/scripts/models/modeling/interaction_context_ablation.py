#!/usr/bin/env python3
"""Deterministic, context-only ablations independent of TensorFlow."""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import collections
import hashlib
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np


def _infer_init_id(source_subrun: str) -> Optional[int]:
    match = re.search(r"ego_init_(\d+)", source_subrun)
    return int(match.group(1)) if match else None


def _init_group_key(sample: Mapping[str, Any]) -> str:
    init_id = sample.get("ego_init_id")
    if init_id is None:
        init_id = _infer_init_id(str(sample.get("source_subrun", "")))
    return f"ego_init_{int(init_id):02d}" if init_id is not None else "<missing-init>"


def _sample_key(sample: Mapping[str, Any]) -> str:
    return "::".join(
        (
            str(sample.get("cell_id", "<missing-cell>")),
            str(sample.get("source_subrun", "<missing-subrun>")),
            str(sample.get("sample_id", "<missing-sample>")),
        )
    )


def prepare_interaction_ablation(
    items: Sequence[Tuple[Any, ...]],
    *,
    mode: str,
    seed: int,
    normalization_mean: Optional[Sequence[float]],
) -> Tuple[List[Tuple[Any, ...]], Dict[str, Any]]:
    """Apply a deterministic context-only diagnostic before raster loading."""

    materialized = list(items)
    if mode == "none":
        return materialized, {
            "mode": "none",
            "applied": False,
            "seed": None,
            "semantics": "unaltered frozen interaction sequence and mask",
        }
    if not materialized:
        return materialized, {"mode": mode, "applied": True, "seed": seed, "samples": 0}
    if normalization_mean is None or len(normalization_mean) != 12:
        raise ValueError("Interaction ablation requires the frozen 12-feature normalization mean")

    mappings: List[str] = []
    output: List[Tuple[Any, ...]] = []
    if mode == "zero":
        neutral = np.asarray(normalization_mean, dtype=np.float32)
        for item in materialized:
            sample = dict(item[0])
            sequence = np.asarray(sample.get("interaction_sequence"), dtype=np.float32)
            if sequence.shape != (6, 12):
                raise ValueError(f"Invalid interaction sequence for zero ablation: {sequence.shape}")
            sample["interaction_sequence"] = np.broadcast_to(neutral, sequence.shape).tolist()
            output.append((sample, *item[1:]))
            mappings.append(f"{_sample_key(sample)}->train_normalization_mean")
        semantics = (
            "each raw valid token is replaced by the train-only normalization mean, "
            "which becomes an exact zero feature vector after MaskedZScore; the original mask is retained"
        )
        cross_init = None
    elif mode == "shuffle":
        by_init: Dict[str, List[int]] = collections.defaultdict(list)
        for index, item in enumerate(materialized):
            by_init[_init_group_key(item[0])].append(index)
        init_groups = sorted(by_init)
        if len(init_groups) < 2:
            raise ValueError("Shuffle ablation requires at least two independent init groups")
        next_group = {
            group: init_groups[(position + 1) % len(init_groups)]
            for position, group in enumerate(init_groups)
        }
        for item in materialized:
            receiver = dict(item[0])
            receiver_group = _init_group_key(receiver)
            donor_group = next_group[receiver_group]
            candidates = by_init[donor_group]
            digest = hashlib.sha256(f"{seed}|{_sample_key(receiver)}".encode("utf-8")).digest()
            donor_index = candidates[int.from_bytes(digest[:8], "big") % len(candidates)]
            donor = materialized[donor_index][0]
            receiver["interaction_sequence"] = donor.get("interaction_sequence")
            receiver["interaction_sequence_mask"] = donor.get("interaction_sequence_mask")
            output.append((receiver, *item[1:]))
            mappings.append(f"{_sample_key(receiver)}->{_sample_key(donor)}")
        semantics = (
            "receiver raster/history/label are unchanged; sequence and mask are deterministically "
            "borrowed from a different ego-init group within the same evaluated subset"
        )
        cross_init = True
    else:
        raise ValueError(f"Unsupported interaction ablation mode: {mode}")

    mapping_sha256 = hashlib.sha256("\n".join(mappings).encode("utf-8")).hexdigest()
    return output, {
        "mode": mode,
        "applied": True,
        "seed": int(seed),
        "samples": len(output),
        "semantics": semantics,
        "cross_init_donors": cross_init,
        "mapping_sha256": mapping_sha256,
    }
