# Post-Turn Heading Branch Status

## Decision

This visual-heading refinement branch is deprecated.

The experiment should restart from the validated mainline result:

```text
core/results/20260628_103325_final_dissertation
```

The user reviewed the videos from this result and confirmed that the ego vehicle does not show the unwanted post-turn lane change in the mainline rollout.

## Why The Branch Was Stopped

Later visual-heading trials introduced extra downstream or post-goal behaviour:

- longer downstream goal offsets;
- post-goal reference extension;
- exit-alignment shaping;
- lane-entry heading diagnostics;
- bounded or preview heading objectives;
- lane-lock tail experiments.

Those changes were useful for diagnosis, but they are not part of the current dissertation mainline. Some of them pushed the ego farther into downstream route-tail correction, which made the video show a lane-change-like motion after the turn.

The 20260628 mainline used only the core rule-aware/adaptive-risk give-way tuning and completed before this downstream correction became visible.

## Current Active Configuration

`core/scripts/carla/scenarios/tuning_configs/give_way_smpc_tuning.json` has been restored to exactly match:

```text
core/results/20260628_103325_final_dissertation/applied_tuning_configs.json
```

The active tuning now contains only:

- core SMPC horizon/model settings;
- collision ellipse settings;
- reference regeneration guard;
- rule-aware yield settings;
- post-yield recovery settings;
- target nominal/init speed;
- post-CARLA gate settings.

It no longer overrides:

- ego goal offset or downstream goal length;
- completion thresholds;
- post-goal reference extension;
- exit-alignment shaping;
- lane-entry heading objective;
- exit-lane lock.

## Mainline Command

Use the normal dissertation batch script, not the deleted lane-entry visual-branch scripts:

```bash
cd ~/autodl-tmp/Research-Project-IMLS/core/scripts/carla

source /root/autodl-tmp/load_gurobi11.sh
conda activate carla_modern
export CARLA_ROOT=/root/autodl-tmp/carla_0.9.14
export CARLA_EGG=$(ls "$CARLA_ROOT"/PythonAPI/carla/dist/carla-*py3*.egg | head -n 1)
export PYTHONPATH="${CARLA_EGG}:${CARLA_ROOT}/PythonAPI/carla:${PYTHONPATH}"

./run_give_way_final_dissertation_batch.sh
```

## Validation Target

The restart target is to reproduce the behaviour of:

```text
20260628_103325_final_dissertation
```

Acceptance criteria:

- required `smpc_var_risk` PASS;
- required `smpc_fixed_risk` PASS;
- no footprint collision;
- yield order OK;
- `solver_failure_frac=0.000` or at least `<=0.05`;
- video does not show the post-turn lane-change artefact observed in later visual-heading branches.

