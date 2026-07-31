import json
import os
import sys
import numpy as np
import tensorflow as tf

scriptdir = os.path.abspath(__file__).split('scripts')[0] + 'scripts/'
sys.path.append(scriptdir)
from evaluation.gmm_prediction import GMMPrediction
from models.multipath_gmm_utils import decode_multipath_raw
from models.prediction_input_contract import preprocess_resnet_raster

class DeployMultiPath:
    """ Class to serve a pretrained MultiPath model for online trajectory prediction.
        Training code found: https://github.com/govvijaycal/confidence_aware_predictions/blob/main/scripts/models/multipath.py
    """

    def __init__(self, saved_model_h5, anchors, calibration=None):
        try:
            self.model = tf.keras.models.load_model(saved_model_h5, compile=False)
        except Exception as e:
            print(f"Could not load the saved model!  Error: {e}")
        self.uses_interaction_context = len(getattr(self.model, "inputs", [])) >= 3

        self.anchors = np.asarray(anchors, dtype=np.float32)

        # Check shape: should be N_A x N_T x 2.
        assert (len(self.anchors.shape) == 3 and self.anchors.shape[-1] == 2)
        self.num_anchors, self.num_timesteps, _ = self.anchors.shape
        self.calibration = self._load_calibration(calibration)

    @staticmethod
    def _load_calibration(calibration):
        if calibration is None:
            return {"temperature": 1.0, "covariance_scale": 1.0}
        if isinstance(calibration, (str, os.PathLike)):
            with open(calibration, "r", encoding="utf-8") as handle:
                calibration = json.load(handle)
        if not isinstance(calibration, dict):
            raise TypeError("calibration must be None, a dict, or a JSON path")
        parameters = calibration.get("parameters", calibration)
        return {
            "temperature": float(parameters.get("temperature", 1.0)),
            "covariance_scale": float(parameters.get("covariance_scale", 1.0)),
        }

    def predict_instance(self, image_raw, past_states, interaction_context=None):
        img = preprocess_resnet_raster(image_raw)

        if len(past_states.shape) == 2:
            past_states = np.expand_dims(past_states, 0)
        past_states = tf.cast(past_states, dtype=tf.float32)

        if self.uses_interaction_context:
            if interaction_context is None:
                interaction_context = np.zeros((8,), dtype=np.float32)
            interaction_context = np.asarray(interaction_context, dtype=np.float32)
            if interaction_context.ndim == 1:
                interaction_context = np.expand_dims(interaction_context, 0)
            interaction_context = tf.cast(interaction_context, dtype=tf.float32)
            pred = self.model.predict_on_batch([img, past_states, interaction_context])
        else:
            pred = self.model.predict_on_batch([img, past_states])  # raw prediction tensor
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
