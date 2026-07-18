# CARLA-Domain MultiPath Fine-Tuning Plan

## Goal

The model-side extension is to adapt the existing deployed MultiPath predictor to the CARLA give-way intersection domain. This keeps the SMPC interface unchanged while adding a concrete prediction-model contribution.

The short-term target is not to introduce a new architecture. The target is:

- evaluate the pretrained MultiPath predictor on CARLA-domain prediction data;
- fine-tune the existing model on the fixed CARLA dataset split;
- compare pretrained vs fine-tuned prediction quality;
- optionally run a small closed-loop SMPC check with the fine-tuned model.

## Dataset Node

Current 50-init prediction dataset:

```text
core/results/20260717_232553_prediction_dataset_collection
```

Merged split:

```text
core/results/20260717_232553_prediction_dataset_collection/prediction_dataset_merged
```

Fixed split rule:

```text
train: ego_init_01-40
val:   ego_init_41-45
test:  ego_init_46-50
```

Current split size:

| Split | Samples | Valid labeled samples |
| --- | ---: | ---: |
| train | 8154 | 3880 |
| val | 1034 | 485 |
| test | 1030 | 485 |
| all | 10218 | 4850 |

## Scripts

All scripts are under:

```text
core/scripts/models/
```

| Script | Purpose |
| --- | --- |
| `prepare_prediction_dataset_split.py` | rebuild fixed train/val/test JSONL files |
| `evaluate_prediction_dataset.py` | evaluate logged pretrained predictions |
| `finetune_multipath_carla.py` | fine-tune current SavedModel on CARLA data |
| `evaluate_multipath_model_on_dataset.py` | evaluate a SavedModel by rerunning predictions |
| `run_finetune_multipath_carla.sh` | one-command GPU workflow |

## Recommended GPU Command

Run on the GPU server after syncing the repository and dataset:

```bash
cd /root/autodl-tmp/Research-Project-IMLS/core/scripts/models

RESULT_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/20260717_232553_prediction_dataset_collection \
EPOCHS=10 \
BATCH_SIZE=16 \
LEARNING_RATE=1e-4 \
FREEZE=head \
./run_finetune_multipath_carla.sh
```

The default mode trains only the final prediction head. This is the lowest-risk first experiment because the deployed model interface remains unchanged.

If the head-only result improves validation/test metrics, optionally run a second stage:

```bash
RESULT_DIR=/root/autodl-tmp/Research-Project-IMLS/core/results/20260717_232553_prediction_dataset_collection \
OUTPUT_MODEL=/root/autodl-tmp/Research-Project-IMLS/core/scripts/models/l5kit_multipath_10_carla_finetuned_full \
EPOCHS=5 \
BATCH_SIZE=8 \
LEARNING_RATE=1e-5 \
FREEZE=none \
./run_finetune_multipath_carla.sh
```

## Expected Outputs

Model outputs:

```text
core/scripts/models/l5kit_multipath_10_carla_finetuned_head
core/scripts/models/l5kit_multipath_10_carla_finetuned_head_best
```

Metrics:

```text
prediction_dataset_merged/logged_baseline_metrics_test.json
prediction_dataset_merged/finetuned_best_metrics_test.json
```

Training log:

```text
core/scripts/models/l5kit_multipath_10_carla_finetuned_head_training_log.csv
core/scripts/models/l5kit_multipath_10_carla_finetuned_head_history.json
```

## Evaluation Focus

The current logged baseline shows that the best trajectory mode often exists, but the probability ranking is weak:

```text
top-probability mode is best mode: 11.96%
mean probability assigned to best mode: 0.2535
mean top mode probability: 0.6027
```

Therefore, the first fine-tuning objective is to improve mode ranking and top-mode ADE/FDE, not necessarily minADE.

Key metrics:

- `top_prob_mode_is_best_frac`
- `top1_ADE_mean`
- `top1_FDE_mean`
- `mean_probability_assigned_to_best_mode`
- `minADE_mean` and `minFDE_mean` as support metrics

## Closed-Loop Use

If the fine-tuned model improves the fixed test split, copy or point the predictor config to the new model directory:

```text
core/scripts/models/l5kit_multipath_10_carla_finetuned_head_best
```

Then run a small 5-init or 10-init SMPC closed-loop check before using it in dissertation results. Do not replace the frozen main experiment unless the closed-loop result is stable.
