from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from evaluate_multipath_model_on_dataset import (  # noqa: E402
    evaluate_decoded,
    fit_validation_calibration,
    resolve_future_valid_mask,
)
from multipath_gmm_utils import GMMDecodeResult  # noqa: E402


def decoded_fixture() -> GMMDecodeResult:
    probabilities = np.asarray([[0.7, 0.3], [0.6, 0.4]], dtype=np.float64)
    means = np.asarray(
        [
            [
                [[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]],
                [[0.0, 1.0], [0.0, 2.0], [0.0, 3.0]],
            ],
            [
                [[1.2, 0.0], [2.2, 0.0], [3.2, 0.0]],
                [[0.0, 1.2], [0.0, 2.2], [0.0, 3.2]],
            ],
        ],
        dtype=np.float64,
    )
    covariances = np.broadcast_to(np.eye(2), (2, 2, 3, 2, 2)).copy()
    raw_parameters = np.zeros((2, 2, 3, 5), dtype=np.float64)
    axis_stds = np.ones((2, 2, 3, 2), dtype=np.float64)
    return GMMDecodeResult(
        probabilities=probabilities,
        means=means,
        covariances=covariances,
        logits=np.log(probabilities),
        raw_trajectory_parameters=raw_parameters,
        axis_standard_deviations=axis_stds,
    )


def samples_fixture():
    masks = ([1, 1, 1], [1, 1, 0])
    return [
        {
            "sample_id": f"sample-{index}",
            "cell_id": "cell",
            "source_subrun": f"run-{index}",
            "ego_init_id": index + 1,
            "future_valid_mask": list(mask),
            "future_times_s": [0.2, 0.4, 0.6],
            "target_to_world_R": [[1.0, 0.0], [0.0, 1.0]],
            "target_to_world_t": [0.0, 0.0],
            "target_style": "assertive_constant_speed",
            "sim_time_s": 0.0,
        }
        for index, mask in enumerate(masks)
    ]


def labels_fixture(invalid_tail: float = 0.0) -> np.ndarray:
    return np.asarray(
        [
            [[1.1, 0.0, 1.0], [2.1, 0.0, 1.0], [3.1, 0.0, 1.0]],
            [[1.1, 0.0, 1.0], [2.1, 0.0, 1.0], [invalid_tail, -invalid_tail, 0.0]],
        ],
        dtype=np.float64,
    )


def raw_prediction_fixture() -> tuple[np.ndarray, np.ndarray]:
    anchors = np.asarray(
        [
            [[1.0, 0.0], [2.0, 0.0], [3.0, 0.0]],
            [[0.0, 1.0], [0.0, 2.0], [0.0, 3.0]],
        ],
        dtype=np.float64,
    )
    raw = np.zeros((2, 2 * 3 * 5 + 2), dtype=np.float64)
    raw[:, -2:] = np.log(np.asarray([[0.7, 0.3], [0.6, 0.4]]))
    return raw, anchors


class FutureValidMaskContractTests(unittest.TestCase):
    def evaluate(self, labels):
        return evaluate_decoded(
            decoded_fixture(),
            labels,
            samples_fixture(),
            3,
            temperature=1.0,
            covariance_scale=1.0,
        )

    def test_invalid_tail_coordinates_cannot_change_metrics(self):
        baseline = self.evaluate(labels_fixture(0.0))
        perturbed = self.evaluate(labels_fixture(1.0e6))
        for key in (
            "top1_ADE_mean",
            "minADE_mean",
            "trajectory_mixture_NLL_per_step_mean",
            "pointwise_mixture_NLL_mean",
            "top1_FDE_mean",
        ):
            self.assertAlmostEqual(baseline[key], perturbed[key], places=12)
        self.assertEqual(baseline["future_validity"], perturbed["future_validity"])
        self.assertEqual(baseline["FDE_full_horizon_samples"], 1)
        self.assertIsNone(baseline["sample_metrics_v3"][1]["top1_FDE"])

    def test_full_horizon_matches_direct_legacy_formula(self):
        labels = labels_fixture(3.1)
        labels[1, 2, 2] = 1.0
        samples = samples_fixture()
        samples[1]["future_valid_mask"] = [1, 1, 1]
        report = evaluate_decoded(
            decoded_fixture(), labels, samples, 3,
            temperature=1.0, covariance_scale=1.0,
        )
        decoded = decoded_fixture()
        displacement = np.linalg.norm(
            decoded.means - labels[:, None, :, :2], axis=-1
        )
        top = np.argmax(decoded.probabilities, axis=1)
        expected_ade = np.mean(
            [np.mean(displacement[index, mode]) for index, mode in enumerate(top)]
        )
        expected_fde = np.mean(
            [displacement[index, mode, -1] for index, mode in enumerate(top)]
        )
        self.assertAlmostEqual(report["top1_ADE_mean"], expected_ade, places=6)
        self.assertAlmostEqual(report["top1_FDE_mean"], expected_fde, places=6)
        self.assertEqual(report["FDE_full_horizon_samples"], 2)

    def test_missing_zero_or_disagreeing_mask_fails_closed(self):
        labels = labels_fixture()
        with self.assertRaisesRegex(ValueError, "at least one valid"):
            zero = labels.copy()
            zero[0, :, 2] = 0.0
            samples = samples_fixture()
            samples[0]["future_valid_mask"] = [0, 0, 0]
            resolve_future_valid_mask(zero, samples, 3)
        with self.assertRaisesRegex(ValueError, "disagreement"):
            resolve_future_valid_mask(labels, samples_fixture(), 3, np.ones((2, 3)))
        with self.assertRaisesRegex(ValueError, "required"):
            resolve_future_valid_mask(labels[..., :2], [{}, {}], 3)

    def test_calibration_is_invariant_to_invalid_tail(self):
        raw, anchors = raw_prediction_fixture()
        grid = SimpleNamespace(
            temperature_min=0.5,
            temperature_max=2.0,
            temperature_count=3,
            covariance_scale_min=0.5,
            covariance_scale_max=2.0,
            covariance_scale_count=3,
        )
        baseline = fit_validation_calibration(
            raw, anchors, labels_fixture(0.0), samples_fixture(), 3, grid
        )
        perturbed = fit_validation_calibration(
            raw, anchors, labels_fixture(1.0e6), samples_fixture(), 3, grid
        )
        self.assertEqual(baseline["parameters"], perturbed["parameters"])
        self.assertEqual(baseline["search"], perturbed["search"])
        self.assertEqual(baseline["future_validity"], perturbed["future_validity"])
        self.assertTrue(math.isfinite(baseline["search"]["best_validation_NLL_per_step"]))

    def test_training_and_cached_evaluation_do_not_drop_mask_channel(self):
        training_source = (SCRIPT_DIR / "train_prediction_model_v3.py").read_text()
        cached_source = (SCRIPT_DIR / "evaluate_thesis_core_cached_v3.py").read_text()
        macro_body = training_source.split("def evaluate_rollout_macro_nll", 1)[1].split(
            "def make_rollout_macro_checkpoint", 1
        )[0]
        self.assertNotIn("[..., :2]", macro_body)
        self.assertNotIn('arrays["labels"][..., :2]', cached_source)

    def test_full_horizon_freeze_binding_precedes_heldout_io(self):
        cached_source = (SCRIPT_DIR / "evaluate_thesis_core_cached_v3.py").read_text()
        body = cached_source.split(
            "def evaluate_full_horizon_sensitivity", 1
        )[1].split("def main", 1)[0]
        binding = body.index("_validate_frozen_training_binding")
        heldout_io = body.index('_load_npz(args.cache_dir / "heldout.npz")')
        self.assertLess(binding, heldout_io)


if __name__ == "__main__":
    unittest.main()
