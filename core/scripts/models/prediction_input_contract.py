#!/usr/bin/env python3
"""Shared raster input contract for online deployment and offline datasets.

The semantic rasterizer returns an in-memory uint8 array.  OpenCV writes and
reads that array without changing its byte order, so the same array can be
reconstructed offline.  Both paths must then call the same ResNet
preprocessing function below.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import cv2
import numpy as np


RASTER_CONTRACT_ID = "semantic_raster_cv2_bytes_resnet_caffe_v2"
RASTER_CHANNEL_SEMANTICS = "rasterizer in-memory byte order; cv2 PNG round-trip"


def canonical_raster_array(image: Any) -> np.ndarray:
    """Return a contiguous uint8 HxWx3 raster without changing channel order."""

    array = np.asarray(image)
    if array.ndim != 3 or array.shape[-1] != 3:
        raise ValueError(f"Expected raster shape [height, width, 3], got {array.shape}")
    if array.dtype != np.uint8:
        array = np.clip(array, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(array)


def save_logged_raster(path: str, image: Any) -> np.ndarray:
    """Persist an online raster and return the exact canonical bytes written."""

    array = canonical_raster_array(image)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output), array):
        raise OSError(f"OpenCV failed to write raster: {output}")
    return array


def load_logged_raster(path: str) -> np.ndarray:
    """Restore the exact in-memory byte order previously written by OpenCV."""

    array = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if array is None:
        raise ValueError(f"Unable to decode raster: {path}")
    return canonical_raster_array(array)


def raster_array_sha256(image: Any) -> str:
    array = canonical_raster_array(image)
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def preprocess_resnet_raster(image: Any) -> np.ndarray:
    """Apply the one frozen ResNet preprocessing path used by all V2 models."""

    import tensorflow as tf
    from tensorflow.keras.applications.resnet import preprocess_input

    raw = np.asarray(image)
    if raw.ndim == 3:
        array = canonical_raster_array(raw)[None, ...]
    elif raw.ndim == 4:
        array = np.stack([canonical_raster_array(item) for item in raw], axis=0)
    else:
        raise ValueError(
            f"Expected raster shape [height, width, 3] or [batch, height, width, 3], got {raw.shape}"
        )
    return np.asarray(preprocess_input(tf.cast(array, tf.float32)))


def raster_contract_metadata() -> dict:
    return {
        "raster_contract_id": RASTER_CONTRACT_ID,
        "storage_codec": "PNG",
        "writer": "cv2.imwrite",
        "reader": "cv2.imread(IMREAD_COLOR)",
        "channel_semantics": RASTER_CHANNEL_SEMANTICS,
        "model_preprocessing": "tensorflow.keras.applications.resnet.preprocess_input",
        "dtype": "uint8_before_preprocessing",
    }
