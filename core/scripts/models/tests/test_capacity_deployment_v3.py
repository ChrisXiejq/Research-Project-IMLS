#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import types
import unittest
from pathlib import Path

import numpy as np

MODELS_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = MODELS_DIR.parent
sys.path.insert(0, str(MODELS_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    import tensorflow as tf
except ModuleNotFoundError:
    tf = None


@unittest.skipUnless(tf is not None, "TensorFlow is required for deployment parity")
class CapacityDeploymentV3Tests(unittest.TestCase):
    def test_training_evaluation_and_deployment_share_tree_hash(self):
        from deploy_multipath_model import DeployMultiPath
        from evaluate_multipath_model_on_dataset import artifact_hash as evaluation_hash
        from train_prediction_model_v3 import artifact_hash as training_hash

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "variables").mkdir()
            (root / "saved_model.pb").write_bytes(b"graph")
            (root / "variables" / "weights").write_bytes(b"weights")
            expected = training_hash(root)["sha256_tree"]
            self.assertEqual(evaluation_hash(root)["sha256_tree"], expected)
            self.assertEqual(DeployMultiPath._artifact_hash(root)["sha256_tree"], expected)

    def test_mlp_and_transformer_have_offline_online_numerical_parity(self):
        # deploy_multipath_model imports the frozen OpenCV raster contract.  A
        # zero-image shim is sufficient here because no file I/O is exercised.
        from PIL import Image

        sys.modules.setdefault(
            "cv2",
            types.SimpleNamespace(
                IMREAD_COLOR=1,
                INTER_LINEAR=1,
                imread=lambda path, flag: np.asarray(Image.open(path)),
                resize=lambda image, shape, interpolation: np.asarray(
                    Image.fromarray(image).resize(shape)
                ),
            ),
        )
        from deploy_multipath_model import DeployMultiPath
        from interaction_adapter_v3 import build_capacity_interaction_adapter
        from multipath_gmm_utils import decode_multipath_raw
        from prediction_input_contract import preprocess_resnet_raster

        image_input = tf.keras.Input((500, 500, 3), name="image")
        state_input = tf.keras.Input((5, 4), name="past")
        image_features = tf.keras.layers.GlobalAveragePooling2D()(image_input)
        state_features = tf.keras.layers.Flatten()(state_input)
        features = tf.keras.layers.Dense(512)(
            tf.keras.layers.Concatenate()([image_features, state_features])
        )
        raw = tf.keras.layers.Dense(2016, name="prediction_head")(features)
        base = tf.keras.Model([image_input, state_input], raw)
        anchors = np.zeros((16, 25, 2), dtype=np.float32)
        image = np.zeros((500, 500, 3), dtype=np.uint8)
        past = np.zeros((5, 4), dtype=np.float32)
        sequence = np.arange(72, dtype=np.float32).reshape(6, 12)
        mask = np.ones(6, dtype=np.float32)
        for family in ("mlp", "transformer"):
            model, _ = build_capacity_interaction_adapter(
                base,
                anchors,
                {"mean": [0.0] * 12, "std": [1.0] * 12},
                family,
                "small",
                1.0,
                dropout=0.0,
            )
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / f"{family}.keras"
                model.save(path)
                deployed = DeployMultiPath(
                    path,
                    anchors,
                    calibration={
                        "fit_split": "validation" if family == "transformer" else "val",
                        "parameters": {"temperature": 1.0, "covariance_scale": 1.0},
                    },
                )
                offline_raw = np.asarray(
                    deployed.model.predict_on_batch(
                        [
                            preprocess_resnet_raster(image),
                            past[None, ...],
                            sequence[None, ...],
                            mask[None, ...],
                        ]
                    )
                )
                offline = decode_multipath_raw(offline_raw, anchors)
                online = deployed.predict_instance(
                    image, past, interaction_context=(sequence, mask)
                )
                np.testing.assert_allclose(
                    offline.probabilities[0], online.mode_probabilities, atol=1e-7
                )
                np.testing.assert_allclose(offline.means[0], online.mus, atol=1e-6)
                np.testing.assert_allclose(
                    offline.covariances[0], online.sigmas, atol=1e-5
                )
                self.assertEqual(deployed.sequence_model_family, family)
                self.assertTrue(np.isfinite(online.mode_probabilities).all())
                self.assertTrue((np.linalg.eigvalsh(online.sigmas) > 0.0).all())


if __name__ == "__main__":
    unittest.main()
