#!/usr/bin/env python3
from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_TEST_ROOT = _Path(__file__).resolve().parents[1]
for _package_name in ("analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_TEST_ROOT / _package_name
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import copy
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "experimental"))

from capacity_model_config_v3 import (  # noqa: E402
    capacity_manifest,
    config_for_cell,
    low_rank_head_parameter_count,
    mlp_parameter_count,
    transformer_parameter_count,
)
from capacity_study_v3_protocol import (  # noqa: E402
    CAPACITY_TARGETS,
    CAPACITY_TOLERANCE_FRACTION,
    HISTORY_HORIZONS_S,
)
from interaction_sequence_v3 import (  # noqa: E402
    apply_history_horizon,
    eligible_sample_ids,
    has_complete_interaction_history,
    horizon_samples,
)


class CapacityModelConfigV3Test(unittest.TestCase):
    def test_parameter_formulas_reproduce_historical_v2_counts(self):
        self.assertEqual(mlp_parameter_count(80), 176_096)
        self.assertEqual(transformer_parameter_count(64, 4, 1, 128), 165_728)
        self.assertEqual(low_rank_head_parameter_count(66), 168_864)
        with self.assertRaises(ValueError):
            low_rank_head_parameter_count(0)
        with self.assertRaisesRegex(ValueError, "divisible"):
            transformer_parameter_count(25, 4, 1, 50)
        with self.assertRaisesRegex(ValueError, "Head cell history"):
            config_for_cell("head", "small", 0.0)

    def test_capacity_manifest_matches_all_tiers_and_histories(self):
        manifest = capacity_manifest()
        self.assertEqual(manifest["status"], "frozen")
        self.assertEqual(len(manifest["head_configs"]), 3)
        self.assertEqual(len(manifest["encoder_configs"]), 18)
        self.assertEqual(len(manifest["matched_pair_audits"]), 9)
        for row in manifest["encoder_configs"]:
            target = CAPACITY_TARGETS[row["capacity_tier"]]
            self.assertLessEqual(
                abs(row["trainable_parameters"] - target) / target,
                CAPACITY_TOLERANCE_FRACTION,
            )
        self.assertTrue(all(row["status"] == "pass" for row in manifest["matched_pair_audits"]))

    def test_horizon_masks_preserve_shape_labels_and_complete_sample_membership(self):
        sequence = np.arange(72, dtype=np.float32).reshape(6, 12)
        samples = [
            {
                "sample_id": "complete",
                "interaction_sequence": sequence.tolist(),
                "interaction_sequence_mask": [1, 1, 1, 1, 1, 1],
                "label": [[1.0, 2.0]],
                "past_states_local": [[3.0, 4.0, 5.0, 6.0]],
            },
            {
                "sample_id": "partial",
                "interaction_sequence": sequence.tolist(),
                "interaction_sequence_mask": [0, 1, 1, 1, 1, 1],
                "label": [[9.0, 9.0]],
                "past_states_local": [[1.0, 1.0, 1.0, 1.0]],
            },
        ]
        self.assertEqual(eligible_sample_ids(samples), ["complete"])
        identifiers = []
        for horizon_s in HISTORY_HORIZONS_S:
            rows = list(horizon_samples(copy.deepcopy(samples), horizon_s))
            self.assertEqual(len(rows), 1)
            identifiers.append(rows[0]["sample_id"])
            self.assertEqual(rows[0]["label"], samples[0]["label"])
            self.assertEqual(rows[0]["past_states_local"], samples[0]["past_states_local"])
            self.assertEqual(np.asarray(rows[0]["interaction_sequence"]).shape, (6, 12))
            self.assertEqual(np.asarray(rows[0]["interaction_sequence_mask"]).shape, (6,))
        self.assertEqual(identifiers, ["complete"] * 3)

    def test_exact_horizon_masks_and_invalid_inputs(self):
        sequence = np.ones((6, 12), dtype=np.float32)
        expected = {
            0.0: [0, 0, 0, 0, 0, 1],
            0.4: [0, 0, 0, 1, 1, 1],
            1.0: [1, 1, 1, 1, 1, 1],
        }
        for horizon_s, mask_expected in expected.items():
            values, mask = apply_history_horizon(sequence, np.ones(6), horizon_s)
            self.assertEqual(mask.tolist(), mask_expected)
            self.assertTrue(np.all(values[np.asarray(mask) == 0.0] == 0.0))
        self.assertTrue(has_complete_interaction_history([1] * 6))
        self.assertFalse(has_complete_interaction_history([0, 1, 1, 1, 1, 1]))
        with self.assertRaisesRegex(ValueError, "complete six-token"):
            apply_history_horizon(sequence, [0, 1, 1, 1, 1, 1], 1.0)


try:
    import tensorflow as tf
except ModuleNotFoundError:  # Local writing environment; server tests run these.
    tf = None


@unittest.skipUnless(tf is not None, "TensorFlow is required for Keras integration tests")
class CapacityKerasModelsV3Test(unittest.TestCase):
    def setUp(self):
        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(7)
        image = tf.keras.Input((2,), name="image")
        past = tf.keras.Input((3,), name="past")
        features = tf.keras.layers.Dense(512, activation="relu", name="features")(
            tf.keras.layers.Concatenate()([image, past])
        )
        output = tf.keras.layers.Dense(2016, name="prediction_head")(features)
        self.base = tf.keras.Model([image, past], output)
        self.anchors = np.zeros((16, 25, 2), dtype=np.float32)
        self.normalization = {"mean": [0.0] * 12, "std": [1.0] * 12}

    def test_low_rank_heads_are_zero_identity_and_own_all_gradients(self):
        from interaction_adapter_v3 import build_capacity_head_adapter

        inputs = [np.ones((2, 2), np.float32), np.ones((2, 3), np.float32)]
        baseline = self.base(inputs, training=False).numpy()
        for tier in ("small", "medium"):
            model, config = build_capacity_head_adapter(self.base, tier)
            np.testing.assert_allclose(model(inputs, training=False).numpy(), baseline, atol=1e-6)
            actual = sum(int(np.prod(value.shape)) for value in model.trainable_weights)
            self.assertEqual(actual, config.trainable_parameters)
            self.assertTrue(
                all("v3_" in getattr(value, "path", value.name) for value in model.trainable_weights)
            )
            self.assertEqual(self.base.trainable_weights, [])
            with tf.GradientTape() as tape:
                loss = tf.reduce_sum(model(inputs, training=True))
            gradients = tape.gradient(loss, model.trainable_weights)
            self.assertEqual(len(gradients), len(model.trainable_weights))
            self.assertTrue(any(value is not None for value in gradients))

    def test_cached_b1_head_is_explicitly_trainable_after_base_freeze(self):
        from train_thesis_core_cached_v3 import _cached_head_model, gradient_audit

        self.base.trainable = False
        model, _ = _cached_head_model(self.base, 512)
        self.assertEqual(len(model.trainable_weights), 2)
        inputs = np.ones((2, 512), dtype=np.float32)
        labels = np.zeros((2, 2016), dtype=np.float32)
        report = gradient_audit(
            model,
            inputs,
            labels,
            lambda truth, prediction: tf.reduce_mean(tf.square(truth - prediction), axis=-1),
        )
        self.assertEqual(report["status"], "pass")
        self.assertGreater(report["gradient_global_norm"], 0.0)

    def test_cached_adapter_inputs_form_a_tensorflow_multi_input_structure(self):
        from train_thesis_core_cached_v3 import cached_inputs, make_dataset

        spec = {"family": "transformer", "seed": 11}
        arrays = {
            "base_raw": np.zeros((3, 2016), dtype=np.float32),
            "sequence": np.zeros((3, 6, 12), dtype=np.float32),
            "mask": np.ones((3, 6), dtype=np.float32),
            "labels": np.zeros((3, 10, 3), dtype=np.float32),
        }
        self.assertIsInstance(cached_inputs(spec, arrays), tuple)
        inputs, labels = next(iter(make_dataset(spec, arrays, 2, shuffle=False)))
        self.assertEqual(len(inputs), 3)
        self.assertEqual(tuple(labels.shape), (2, 10, 3))

    def test_all_encoder_cells_match_formula_and_zero_residual(self):
        from interaction_adapter_v3 import build_capacity_interaction_adapter

        image = np.ones((1, 2), np.float32)
        past = np.ones((1, 3), np.float32)
        sequence = np.arange(72, dtype=np.float32).reshape(1, 6, 12)
        mask = np.ones((1, 6), np.float32)
        baseline = self.base([image, past], training=False).numpy()
        for family in ("mlp", "transformer"):
            for horizon_s in HISTORY_HORIZONS_S:
                for tier in CAPACITY_TARGETS:
                    model, config = build_capacity_interaction_adapter(
                        self.base,
                        self.anchors,
                        self.normalization,
                        family,
                        tier,
                        horizon_s,
                        dropout=0.0,
                    )
                    actual = sum(int(np.prod(value.shape)) for value in model.trainable_weights)
                    self.assertEqual(actual, config.trainable_parameters)
                    np.testing.assert_allclose(
                        model([image, past, sequence, mask], training=False).numpy(),
                        baseline,
                        atol=1e-6,
                    )
                    tf.keras.backend.clear_session()

    def test_one_token_layer_masks_older_tokens_and_serializes(self):
        from interaction_adapter_v3 import FixedHistoryHorizon

        layer = FixedHistoryHorizon(0.0)
        sequence = tf.reshape(tf.range(72, dtype=tf.float32), (1, 6, 12))
        values, mask = layer([sequence, tf.ones((1, 6))])
        self.assertEqual(mask.numpy().tolist(), [[0.0, 0.0, 0.0, 0.0, 0.0, 1.0]])
        self.assertTrue(np.all(values.numpy()[:, :5, :] == 0.0))
        config = layer.get_config()
        restored = FixedHistoryHorizon.from_config(config)
        self.assertEqual(restored.history_horizon_s, 0.0)

    def test_masked_tokens_are_invariant_deterministic_and_full_models_serialize(self):
        from interaction_adapter_v3 import build_capacity_interaction_adapter

        image = np.ones((1, 2), np.float32)
        past = np.ones((1, 3), np.float32)
        first = np.arange(72, dtype=np.float32).reshape(1, 6, 12)
        changed = first.copy()
        changed[:, :5, :] += 10_000.0
        mask = np.ones((1, 6), np.float32)
        for family in ("mlp", "transformer"):
            model, _ = build_capacity_interaction_adapter(
                self.base,
                self.anchors,
                self.normalization,
                family,
                "small",
                0.0,
                dropout=0.0,
            )
            before = model([image, past, first, mask], training=False).numpy()
            after = model([image, past, changed, mask], training=False).numpy()
            repeated = model([image, past, first, mask], training=False).numpy()
            np.testing.assert_allclose(before, after, atol=1e-6)
            np.testing.assert_array_equal(before, repeated)
            with tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / f"{family}.keras"
                model.save(path)
                loaded = tf.keras.models.load_model(path, compile=False)
                np.testing.assert_allclose(
                    loaded([image, past, first, mask], training=False).numpy(),
                    before,
                    atol=1e-6,
                )

    def test_v2_builders_remain_compatible_after_v3_registration(self):
        from interaction_adapter_v2 import build_interaction_adapter

        image = np.ones((1, 2), np.float32)
        past = np.ones((1, 3), np.float32)
        sequence = np.ones((1, 6, 12), np.float32)
        mask = np.ones((1, 6), np.float32)
        baseline = self.base([image, past], training=False).numpy()
        for variant in ("B2-D", "T2"):
            model = build_interaction_adapter(
                self.base,
                self.anchors,
                self.normalization,
                variant,
                dropout=0.0,
            )
            self.assertEqual(len(model.inputs), 4)
            np.testing.assert_allclose(
                model([image, past, sequence, mask], training=False).numpy(),
                baseline,
                atol=1e-6,
            )


if __name__ == "__main__":
    unittest.main()
