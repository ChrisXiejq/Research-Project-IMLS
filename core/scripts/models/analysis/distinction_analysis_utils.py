"""Small, dependency-light helpers for the distinction evidence pipeline.

The functions in this module deliberately use the Python standard library where
possible.  This makes provenance and regression gates runnable on both the
local laptop and the CARLA/GPU server.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import csv
import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


def sha256_file(path: os.PathLike[str] | str, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_write_json(path: os.PathLike[str] | str, payload: Any) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_csv(path: os.PathLike[str] | str, rows: Iterable[Mapping[str, Any]], fields: Sequence[str]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_command(command: Sequence[str], cwd: os.PathLike[str] | str) -> str:
    process = subprocess.run(
        list(command), cwd=str(cwd), check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return process.stdout.strip()


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    """Resolve an RFC 6901 JSON pointer, raising on a missing locator."""
    if pointer == "":
        return document
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with '/': {pointer!r}")
    current = document
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if token == "-":
                raise KeyError("'-' is not a readable array index")
            current = current[int(token)]
        elif isinstance(current, dict):
            current = current[token]
        else:
            raise KeyError(f"Cannot descend through {type(current).__name__} at {token!r}")
    return current


def collision_episodes(frames: Iterable[int], maximum_gap: int = 1) -> list[list[int]]:
    """Collapse duplicated collision callbacks into frame-contiguous episodes."""
    unique = sorted({int(frame) for frame in frames})
    if not unique:
        return []
    episodes: list[list[int]] = [[unique[0]]]
    for frame in unique[1:]:
        if frame - episodes[-1][-1] <= maximum_gap:
            episodes[-1].append(frame)
        else:
            episodes.append([frame])
    return episodes


def assert_equal_lengths(named_sequences: Mapping[str, Sequence[Any]]) -> int:
    lengths = {name: len(sequence) for name, sequence in named_sequences.items()}
    if not lengths:
        return 0
    if len(set(lengths.values())) != 1:
        raise ValueError(f"Mismatched sequence lengths: {lengths}")
    return next(iter(lengths.values()))


def assert_single_result_generation(records: Iterable[Mapping[str, Any]]) -> str:
    """Reject accidental aggregation of legacy and remediated evidence."""
    generations = {str(record["result_generation"]) for record in records}
    if len(generations) != 1:
        raise ValueError(f"Mixed result generations are forbidden: {sorted(generations)}")
    return next(iter(generations))
