#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np


SCRIPT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from capacity_study_v3_runs import (  # noqa: E402
    convergence_extension_plan,
    core_runs,
    run_manifest,
    select_learning_rates,
)
from capacity_study_v3_protocol import LEARNING_RATES  # noqa: E402
from train_prediction_model_v3 import (  # noqa: E402
    assert_resume_compatible,
    audit_training_data,
    build_model,
    load_run_spec,
    make_dataset,
    make_finite_weights_callback,
    make_optimizer,
    make_rollout_macro_checkpoint,
    sample_generator,
    tf,
)


class TrainPredictionModelV3ContractTest(unittest.TestCase):
    def test_formal_data_audit_requires_disjoint_complete_group_cell_support(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raster = root / "raster.png"
            raster.write_bytes(b"fixture")

            def row(group, cell, sample_id):
                return {
                    "sample_id": sample_id,
                    "ego_init_id": group,
                    "cell_id": cell,
                    "raster_abspath": str(raster),
                    "past_states_local": [[0.0, 0.0, 0.0, 0.0]],
                    "interaction_sequence": np.zeros((6, 12)).tolist(),
                    "interaction_sequence_mask": [1] * 6,
                    "target_to_world_R": [[1.0, 0.0], [0.0, 1.0]],
                    "target_to_world_t": [0.0, 0.0],
                    "future_xy_world": [[float(i), 0.0] for i in range(10)],
                    "future_valid_mask": [1] * 10,
                }

            cells = ("S0_FIXED", "S0_ADAPTIVE", "S1_FIXED", "S1_ADAPTIVE")
            train_rows = [row(1, cell, index) for index, cell in enumerate(cells)]
            val_rows = [
                row(group, cell, index)
                for group in range(41, 46)
                for index, cell in enumerate(cells)
            ]
            train = root / "train.jsonl"
            val = root / "val.jsonl"
            train.write_text(
                "".join(json.dumps(value) + "\n" for value in train_rows),
                encoding="utf-8",
            )
            val.write_text(
                "".join(json.dumps(value) + "\n" for value in val_rows),
                encoding="utf-8",
            )
            report = audit_training_data(
                train,
                val,
                train_groups=[1],
                label_horizon=10,
                strict_formal=True,
            )
            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["splits"]["validation"]["eligible_samples"], 20)

            train.write_text(
                "".join(json.dumps(value) + "\n" for value in train_rows + [train_rows[0]]),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate_sample_keys"):
                audit_training_data(
                    train,
                    val,
                    train_groups=[1],
                    label_horizon=10,
                    strict_formal=True,
                )

    def test_run_spec_resolves_core_duplicate_and_fraction_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "runs.json"
            path.write_text(json.dumps(run_manifest()), encoding="utf-8")
            core, _ = load_run_spec(path, "v3__head-large__lr3e-5__s11__data100")
            self.assertEqual(core["model_cell_id"], "head-large")
            self.assertFalse(core["is_additional_fraction_run"])
            fraction, _ = load_run_spec(path, "v3__mlp-h1p0-large__lr1e-4__s23__data025")
            self.assertEqual(fraction["data_fraction"], 0.25)
            self.assertTrue(fraction["is_additional_fraction_run"])
            with self.assertRaisesRegex(ValueError, "one semantic spec"):
                load_run_spec(path, "unknown")

    def test_extension_spec_requires_hash_bound_authorisation(self):
        rows = []
        for spec in core_runs():
            lr_rank = LEARNING_RATES.index(spec.learning_rate)
            rows.append(
                {
                    "run_id": spec.run_id,
                    "model_cell_id": spec.model_cell_id,
                    "learning_rate": spec.learning_rate,
                    "seed": spec.seed,
                    "split": "validation",
                    "status": "pass",
                    "rollout_macro_nll": 1.0 + 0.1 * lr_rank,
                    "best_epoch": (
                        79
                        if spec.model_cell_id == "transformer-h1p0-small"
                        and lr_rank == 0
                        else 40
                    ),
                    "epochs_allowed": 80,
                }
            )
        selection = select_learning_rates(rows)
        extension = convergence_extension_plan(selection, rows)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "extension.json"
            path.write_text(json.dumps(extension), encoding="utf-8")
            identifier = extension["extension_runs"][0]["run_id"]
            spec, _ = load_run_spec(path, identifier)
            self.assertEqual(spec["epochs"], 120)
            self.assertTrue(spec["extends_run_id"])
            extension["extension_runs"][0]["seed"] = 999
            path.write_text(json.dumps(extension), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                load_run_spec(path, identifier)

    def test_resume_rejects_any_semantic_change(self):
        config = {"seed": 11, "family": "mlp", "source_sha256": {"a": "1"}}
        assert_resume_compatible(config, dict(config))
        changed = dict(config)
        changed["seed"] = 23
        with self.assertRaisesRegex(ValueError, "seed"):
            assert_resume_compatible(config, changed)

    def test_sample_generator_uses_complete_history_and_group_fraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raster = root / "raster.png"
            raster.write_bytes(b"fixture")
            rows = []
            for sample_id, group, mask in (
                ("keep", 1, [1] * 6),
                ("wrong_group", 2, [1] * 6),
                ("partial_history", 1, [0, 1, 1, 1, 1, 1]),
            ):
                rows.append(
                    {
                        "sample_id": sample_id,
                        "ego_init_id": group,
                        "raster_abspath": str(raster),
                        "past_states_local": [[0.0, 0.0, 0.0, 0.0]],
                        "interaction_sequence": np.arange(72).reshape(6, 12).tolist(),
                        "interaction_sequence_mask": mask,
                        "target_to_world_R": [[1.0, 0.0], [0.0, 1.0]],
                        "target_to_world_t": [0.0, 0.0],
                        "future_xy_world": [[float(i), 0.0] for i in range(10)],
                        "future_valid_mask": [1] * 10,
                    }
                )
            jsonl = root / "train.jsonl"
            jsonl.write_text("".join(json.dumps(row) + "\n" for row in rows))
            emitted = list(
                sample_generator(
                    jsonl,
                    family="mlp",
                    history_horizon_s=0.0,
                    label_horizon=10,
                    allowed_train_groups={1},
                    maximum=None,
                )
            )
            self.assertEqual(len(emitted), 1)
            _, _, sequence, mask, label = emitted[0]
            self.assertEqual(mask.tolist(), [0.0, 0.0, 0.0, 0.0, 0.0, 1.0])
            self.assertTrue(np.all(sequence[:5] == 0.0))
            self.assertEqual(label.shape, (10, 3))

    @unittest.skipUnless(tf is not None, "TensorFlow is required for the trainer smoke test")
    def test_frozen_optimizer_and_finite_weight_guard(self):
        optimizer = make_optimizer(1.0e-4)
        config = optimizer.get_config()
        self.assertAlmostEqual(float(config["weight_decay"]), 1.0e-5)
        self.assertAlmostEqual(float(config["clipnorm"]), 10.0)
        model = tf.keras.Sequential([tf.keras.layers.Dense(1, input_shape=(1,))])
        callback = make_finite_weights_callback()
        callback.set_model(model)
        callback.on_epoch_end(0)
        model.trainable_weights[0].assign([[float("nan")]])
        with self.assertRaisesRegex(RuntimeError, "Non-finite trainable weight"):
            callback.on_epoch_end(1)

    @unittest.skipUnless(tf is not None, "TensorFlow is required for the trainer smoke test")
    def test_one_batch_smoke_training_uses_manifest_model_and_dataset_contract(self):
        import types
        from PIL import Image
        from interaction_adapter_v2 import masked_multipath_loss

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raster = root / "raster.png"
            Image.fromarray(np.zeros((500, 500, 3), dtype=np.uint8)).save(raster)
            # The lightweight local TensorFlow environment omits OpenCV.  The
            # production environment uses the real cv2 byte-order contract;
            # zeros let this smoke test exercise tf.data without changing it.
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
            sample = {
                "sample_id": "smoke",
                "ego_init_id": 1,
                "raster_abspath": str(raster),
                "past_states_local": np.zeros((5, 4), dtype=float).tolist(),
                "interaction_sequence": np.zeros((6, 12), dtype=float).tolist(),
                "interaction_sequence_mask": [1] * 6,
                "target_to_world_R": [[1.0, 0.0], [0.0, 1.0]],
                "target_to_world_t": [0.0, 0.0],
                "future_xy_world": [[0.1 * index, 0.0] for index in range(10)],
                "future_valid_mask": [1] * 10,
            }
            (root / "train.jsonl").write_text(json.dumps(sample) + "\n", encoding="utf-8")
            image = tf.keras.Input((500, 500, 3), name="image")
            past = tf.keras.Input((5, 4), name="past")
            image_features = tf.keras.layers.GlobalAveragePooling2D()(image)
            state_features = tf.keras.layers.Flatten()(past)
            features = tf.keras.layers.Dense(512, activation="relu", name="features")(
                tf.keras.layers.Concatenate()([image_features, state_features])
            )
            output = tf.keras.layers.Dense(2016, name="prediction_head")(features)
            base = tf.keras.Model([image, past], output)
            base_path = root / "base.keras"
            base.save(base_path)
            anchors = np.zeros((16, 25, 2), dtype=np.float32)
            spec = run_manifest()["core_runs"][0]
            model, capacity = build_model(spec, root, base_path, anchors)
            self.assertEqual(
                sum(int(np.prod(weight.shape)) for weight in model.trainable_weights),
                capacity.trainable_parameters,
            )
            dataset = make_dataset(
                root / "train.jsonl",
                spec=spec,
                label_horizon=10,
                batch_size=1,
                shuffle=False,
                shuffle_buffer=1,
                maximum=1,
                expected_samples=1,
            )
            model.compile(optimizer="adam", loss=masked_multipath_loss(anchors, 10))
            history = model.fit(dataset, epochs=1, verbose=0)
            self.assertTrue(np.isfinite(history.history["loss"][0]))

    @unittest.skipUnless(tf is not None, "TensorFlow is required for checkpoint resume")
    def test_checkpoint_resume_rejects_history_weight_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            weights = Path(temporary) / "best.weights.h5"
            weights.write_bytes(b"partial")
            with self.assertRaisesRegex(ValueError, "checkpoint/history mismatch"):
                make_rollout_macro_checkpoint(
                    validation_dataset=[],
                    validation_samples=[],
                    anchors=np.zeros((16, 25, 2), dtype=np.float32),
                    label_horizon=10,
                    best_weights=weights,
                    existing_history={},
                )


if __name__ == "__main__":
    unittest.main()
