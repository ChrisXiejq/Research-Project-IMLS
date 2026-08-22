import json
import hashlib
import os
import sys
import numpy as np
import tensorflow as tf

scriptdir = os.path.abspath(__file__).split('scripts')[0] + 'scripts/'
sys.path.append(scriptdir)
from evaluation.gmm_prediction import GMMPrediction
from models.multipath_gmm_utils import decode_multipath_raw
from models.prediction_input_contract import preprocess_resnet_raster
# Imports register both historical V2 and capacity/history V3 serialisable
# custom layers before load_model. V3 P* may be either an MLP or Transformer.
from models import interaction_adapter_v2  # noqa: F401
from models import interaction_adapter_v3  # noqa: F401

class DeployMultiPath:
    """ Class to serve a pretrained MultiPath model for online trajectory prediction.
        Training code found: https://github.com/govvijaycal/confidence_aware_predictions/blob/main/scripts/models/multipath.py
    """

    def __init__(self, saved_model_h5, anchors, calibration=None):
        self.model_path = os.path.abspath(os.fspath(saved_model_h5))
        try:
            self.model = tf.keras.models.load_model(saved_model_h5, compile=False)
        except Exception as e:
            raise RuntimeError(f"Could not load the saved model {self.model_path}: {e}") from e
        self.model_input_count = len(getattr(self.model, "inputs", []))
        self.uses_interaction_context = self.model_input_count >= 3
        self.sequence_model_family = self._sequence_model_family()

        self.anchors = np.asarray(anchors, dtype=np.float32)

        # Check shape: should be N_A x N_T x 2.
        assert (len(self.anchors.shape) == 3 and self.anchors.shape[-1] == 2)
        self.num_anchors, self.num_timesteps, _ = self.anchors.shape
        self.model_artifact = self._artifact_hash(self.model_path)
        self.calibration_source = (
            os.path.abspath(os.fspath(calibration))
            if isinstance(calibration, (str, os.PathLike))
            else None
        )
        self.calibration_artifact = (
            self._artifact_hash(self.calibration_source) if self.calibration_source else None
        )
        self.calibration, self.calibration_metadata = self._load_calibration(calibration)
        expected_model = self.calibration_metadata.get("model_artifact") or {}
        expected_tree = expected_model.get("sha256_tree")
        if expected_tree and expected_tree != self.model_artifact.get("sha256_tree"):
            raise ValueError(
                "Calibration/model artifact mismatch: "
                f"calibration expects {expected_tree}, loaded {self.model_artifact.get('sha256_tree')}"
            )

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @classmethod
    def _artifact_hash(cls, path):
        path = os.path.abspath(os.fspath(path))
        if os.path.isfile(path):
            return {
                "path": path,
                "bytes": os.path.getsize(path),
                "sha256": cls._sha256_file(path),
            }
        files = []
        for root, _, names in os.walk(path):
            for name in names:
                files.append(os.path.join(root, name))
        files.sort()
        digest = hashlib.sha256()
        total_bytes = 0
        for item in files:
            relative = os.path.relpath(item, path)
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(cls._sha256_file(item).encode("ascii"))
            total_bytes += os.path.getsize(item)
        return {
            "path": path,
            "files": len(files),
            "bytes": total_bytes,
            "sha256_tree": digest.hexdigest(),
        }

    @staticmethod
    def _load_calibration(calibration):
        if calibration is None:
            return (
                {"temperature": 1.0, "covariance_scale": 1.0},
                {"source": "identity_no_calibration_artifact", "fit_split": None},
            )
        if isinstance(calibration, (str, os.PathLike)):
            with open(calibration, "r", encoding="utf-8") as handle:
                calibration = json.load(handle)
        if not isinstance(calibration, dict):
            raise TypeError("calibration must be None, a dict, or a JSON path")
        if calibration.get("fit_split") != "val":
            raise ValueError(
                "Deployment calibration must be frozen on validation; "
                f"got fit_split={calibration.get('fit_split')!r}"
            )
        parameters = calibration.get("parameters", calibration)
        parsed = {
            "temperature": float(parameters.get("temperature", 1.0)),
            "covariance_scale": float(parameters.get("covariance_scale", 1.0)),
        }
        if not all(np.isfinite(value) and value > 0.0 for value in parsed.values()):
            raise ValueError(f"Invalid deployment calibration parameters: {parsed}")
        return parsed, dict(calibration)

    def _sequence_model_family(self):
        layer_names = {layer.name for layer in getattr(self.model, "layers", [])}
        if any("transformer" in name for name in layer_names):
            return "transformer"
        if self.model_input_count == 4 and any("mlp" in name for name in layer_names):
            return "mlp"
        if self.model_input_count == 4:
            return "four_input_sequence_model"
        return None

    def deployment_metadata(self):
        return {
            "schema_version": "multipath_online_deployment_v1",
            "model_artifact": self.model_artifact,
            "model_input_count": self.model_input_count,
            "uses_interaction_context": self.uses_interaction_context,
            "sequence_model_family": self.sequence_model_family,
            "calibration_source": self.calibration_source,
            "calibration_artifact": self.calibration_artifact,
            "calibration_fit_split": self.calibration_metadata.get("fit_split"),
            "calibration_parameters": dict(self.calibration),
            "calibration_model_artifact": self.calibration_metadata.get("model_artifact"),
        }

    def predict_instance(
        self,
        image_raw,
        past_states,
        interaction_context=None,
        interaction_mask=None,
    ):
        img = preprocess_resnet_raster(image_raw)

        if len(past_states.shape) == 2:
            past_states = np.expand_dims(past_states, 0)
        past_states = tf.cast(past_states, dtype=tf.float32)

        if self.model_input_count == 4:
            if isinstance(interaction_context, (tuple, list)) and len(interaction_context) == 2:
                interaction_context, interaction_mask = interaction_context
            if interaction_context is None:
                interaction_context = np.zeros((6, 12), dtype=np.float32)
            interaction_context = np.asarray(interaction_context, dtype=np.float32)
            if interaction_context.ndim == 2:
                interaction_context = np.expand_dims(interaction_context, 0)
            if interaction_context.shape[1:] != (6, 12):
                raise ValueError(
                    "Sequence model requires interaction_sequence shape [batch, 6, 12], "
                    f"got {interaction_context.shape}"
                )
            if interaction_mask is None:
                interaction_mask = np.ones(interaction_context.shape[:2], dtype=np.float32)
            interaction_mask = np.asarray(interaction_mask, dtype=np.float32)
            if interaction_mask.ndim == 1:
                interaction_mask = np.expand_dims(interaction_mask, 0)
            pred = self.model.predict_on_batch(
                [
                    img,
                    past_states,
                    tf.cast(interaction_context, dtype=tf.float32),
                    tf.cast(interaction_mask, dtype=tf.float32),
                ]
            )
        elif self.model_input_count == 3:
            if interaction_context is None:
                interaction_context = np.zeros((8,), dtype=np.float32)
            interaction_context = np.asarray(interaction_context, dtype=np.float32)
            if interaction_context.ndim == 1:
                interaction_context = np.expand_dims(interaction_context, 0)
            interaction_context = tf.cast(interaction_context, dtype=tf.float32)
            pred = self.model.predict_on_batch([img, past_states, interaction_context])
        elif self.model_input_count == 2:
            pred = self.model.predict_on_batch([img, past_states])  # raw prediction tensor
        else:
            raise ValueError(f"Unsupported MultiPath model input count: {self.model_input_count}")
        gmm_pred = self._make_gmm(pred)                         # convert to GMM format
        return gmm_pred

    def _make_gmm(self, pred):
        assert(len(pred) == 1)
        decoded = decode_multipath_raw(
            np.asarray(pred)[0],
            self.anchors,
            temperature=self.calibration["temperature"],
            covariance_scale=self.calibration["covariance_scale"],
        )
        return GMMPrediction(
            self.num_anchors,
            self.num_timesteps,
            decoded.probabilities,
            decoded.means,
            decoded.covariances,
        )
