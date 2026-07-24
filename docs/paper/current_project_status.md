# Current Project Status and Canonical Results

This document is the canonical project status note. It consolidates the older milestone notes, fine-tuning plan, intermediate 10-init validation, 50-init validation, and ablation result tables.

## 1. Dissertation Narrative

The current dissertation story should be controlled as a two-stage improvement:

1. **Control-side improvement**: the project first moved from a single SMPC formulation to an SMPC+Supervisor architecture. The rule-aware supervisor enforces give-way behaviour, footprint safety, and final execution safety in the unsignalised right-hand-traffic intersection.
2. **Model-side improvement**: after the control pipeline became stable, the deployed MultiPath predictor was analysed. The main model-side issue was mode ranking / probability calibration: a good trajectory mode was often present, but it was not reliably assigned the highest probability.
3. **Model optimisation**: CARLA-domain prediction data were collected, a fixed train/val/test split was prepared, and the current MultiPath model was fine-tuned.
4. **Current best integrated milestone**: the fine-tuned predictor was inserted back into the SMPC+Supervisor pipeline and validated over 50 initial conditions.

The intended thesis claim is cumulative: the control-side contribution provides closed-loop rule-aware safety, and the model-side contribution improves prediction reliability while preserving the safety result in the integrated pipeline.

### Next-Stage Direction After Supervisor Feedback

The current best integrated milestone remains the reference point, but the next experimental stage should focus on explanation and ablation rather than simply producing more aggregate 50-init runs.

Guiding document:

```text
docs/paper/next_experiment_action_guide_after_supervisor_feedback.md
```

The next stage should prioritise:

- diagnosing why the ego vehicle stops too early and behaves conservatively;
- quantifying how much the supervisor shapes the final executed action;
- comparing fixed-risk and adaptive-risk SMPC under full and reduced-intervention supervisor settings;
- analysing MPC infeasibility cases separately instead of only reporting aggregate feasibility;
- sanity-checking the fine-tuned predictor result to rule out split leakage or metric inconsistency.

Future code changes and experiments should be checked against this direction before execution.

## 2. Current Best Integrated Milestone

```text
result:
  core/results/20260718_104740_50init_finetuned_predictor_validation

method:
  SMPC+Supervisor with CARLA-domain fine-tuned MultiPath predictor

comparison:
  smpc_fixed_risk
  smpc_var_risk with adaptive_interaction_severity

status:
  100/100 required SMPC rollouts PASS
  no footprint collision
  no yield-rule violation
  successful completion
```

### Closed-Loop Safety

| Policy | Gate pass | Solver failure max / mean | Min / mean footprint separation | Min / mean centre distance |
|---|---:|---:|---:|---:|
| `smpc_fixed_risk` | 50 / 50 | 0.0245 / 0.0063 | 0.8714 / 2.1449 m | 4.3740 / 5.4070 m |
| `smpc_var_risk` | 50 / 50 | 0.0244 / 0.0063 | 0.8833 / 2.1454 m | 4.3831 / 5.4093 m |

### Aggregate Paper Metrics

| Policy | Completion time | Feasibility | Average solve time | `dmin_TV` | Completion valid | Solver failure frac |
|---|---:|---:|---:|---:|---:|---:|
| `smpc_fixed_risk` | 10.0160 s | 0.9937 | 0.0629 s | 5.4070 m | 1.0 | 0.0063 |
| `smpc_var_risk` | 10.0130 s | 0.9937 | 0.0885 s | 5.4093 m | 1.0 | 0.0063 |

### Comparison with Previous Control-Side Frozen Milestone

Previous frozen control-side milestone:

```text
core/results/20260710_164024_50init_phase_floor_final_dissertation
```

| Result | Var-risk footprint min / mean | Var-risk centre min / mean |
|---|---:|---:|
| Previous frozen 50-init control-side result | 0.8745 / 2.1504 m | 4.3771 / 5.4114 m |
| Current fine-tuned predictor 50-init result | 0.8833 / 2.1454 m | 4.3831 / 5.4093 m |

The closed-loop improvement is small because the SMPC+Supervisor pipeline was already strongly safe. The current result is still the best integrated milestone because the model-side improvement is substantial, the full 50-init safety gate is preserved, and the worst-case variable-risk safety margin moves slightly in the positive direction.

## 3. Model-Side Improvement

Prediction dataset node:

```text
core/results/20260717_232553_prediction_dataset_collection/prediction_dataset_merged
```

Fixed split:

```text
train: ego_init_01-40
val:   ego_init_41-45
test:  ego_init_46-50
```

Same-test-set predictor metrics:

| Predictor | Top-1 ADE | MinADE | Top-1 FDE | MinFDE | Top-probability mode is best |
|---|---:|---:|---:|---:|---:|
| Pretrained MultiPath | 4.0337 m | 0.2215 m | 7.5259 m | 0.4102 m | 0.98% |
| Fine-tuned MultiPath | 0.0271 m | 0.0271 m | 0.0366 m | 0.0366 m | 100% |

Interpretation:

- The pretrained model often contained a near-correct mode, but the top-probability mode was usually not the best one.
- Fine-tuning mainly fixes CARLA-domain mode ranking / probability calibration.
- The model-side improvement is much larger than the closed-loop metric improvement because the rule-aware supervisor already made the original closed-loop system safe.

## 4. Phase-Aware Adaptive-Risk Evidence

Current best integrated milestone:

| Conflict phase | Adaptive tightening | Fixed tightening | Adaptive - fixed | Floor applied frac |
|---|---:|---:|---:|---:|
| Approach / pre-clearance | 1.6800 | 1.6400 | +0.0400 | 1.0000 |
| Critical / pre-clearance | 1.7954 | 1.6400 | +0.1554 | 0.9911 |
| Near / pre-clearance | 1.8500 | 1.6400 | +0.2100 | 1.0000 |
| Critical / post-clearance | 1.2816 | 1.6400 | -0.3584 | 0.0000 |
| Near / post-clearance | 1.2816 | 1.6400 | -0.3584 | 0.0000 |

The adaptive-risk mechanism remains interpretable with the fine-tuned predictor: it is stricter before target clearance and relaxed after target clearance.

## 5. Mechanism Ablation

Canonical ablation result:

```text
core/results/20260711_120356_10init_adaptive_risk_ablation
```

The ablation tested whether the pre-clearance risk floor is responsible for the stronger adaptive-risk behaviour.

| Variant | Critical / pre-clearance adaptive-minus-fixed tightening | Interpretation |
|---|---:|---|
| `phase_floor` | about +0.1600 | Intended phase-aware tightening is clearly active. |
| `no_phase_floor` | about +0.0603 | Removing the floor substantially weakens the critical pre-clearance tightening gap. |

Conclusion: the phase-aware pre-clearance floor is a key mechanism that makes adaptive risk more conservative before the priority target clears the conflict area.

## 6. Graphical Results

Frozen control-side figures:

```text
docs/paper/figures/
```

Fine-tuned predictor validation figures:

```text
core/results/20260718_104740_50init_finetuned_predictor_validation/figures/
```

Generated fine-tuned validation figures:

- `fig_finetuned_validation_01_safety_summary.svg`
- `fig_finetuned_validation_02_phase_risk_tightening.svg`
- `fig_finetuned_validation_03_var_minus_fixed_tightening.svg`
- `fig_finetuned_validation_04_supervisor_override_fraction.svg`
- `fig_finetuned_validation_05_acceleration_delta.svg`

Original-paper-style result package:

```text
docs/paper/original_paper_style_results/
```

This package follows the evaluation structure of the reference paper, especially Table I: mobility, comfort, safety, and solver performance. It also includes a comparison analysis against the original paper's published unprotected-left result. The key conclusion is that the current milestone improves the previous project version and substantially improves model-side prediction calibration, but it should not be claimed as a strict overall performance improvement over the original paper because the scenario, normalization, and safety architecture are different.

Generated files:

- `original_paper_style_result_analysis.md`
- `table_original_paper_i_values.csv`
- `table_dissertation_paper_style_metrics.csv`
- `table_current_milestone_improvement.csv`
- `fig_01_paper_style_closed_loop_metrics.svg`
- `fig_02_prediction_model_improvement.svg`
- `fig_03_reference_paper_comparison.svg`
- `fig_04_current_vs_frozen_safety_margin.svg`
- `fig_05_timeseries_init_{41,47,48}_closed_loop_behaviour.svg`
- `fig_06_timeseries_init_{41,47,48}_risk_supervisor.svg`
- `fig_07_timeseries_init_{41,47,48}_prediction_and_execution.svg`

The `fig_05` figures are closest to the original paper's Fig. 9 / Fig. 10 style: they show multi-panel closed-loop time-series curves for lateral error, heading error, speed, steering / yaw command, and longitudinal acceleration command. The `fig_06` and `fig_07` figures add dissertation-specific diagnostics for phase-aware risk and supervisor intervention.

Recommended bird's-eye qualitative video cases from the 50-init validation:

- `ego_init_41`: best overall safety margin.
- `ego_init_47`: clean rollout with zero solver failure.
- `ego_init_48`: high safety margin and stable behaviour.
- Optional robustness case: `ego_init_31`, the lowest-margin PASS case.

## 7. Paper-Safe Milestone Claim

Recommended claim:

> The current best result combines the control-side SMPC+Supervisor architecture with the model-side fine-tuned MultiPath predictor. The control-side improvement provides robust rule-aware closed-loop safety, while the model-side fine-tuning resolves the predictor's CARLA-domain mode-ranking problem. In the final 50-init validation, the integrated system preserves the full post-CARLA safety-gate pass result, slightly improves the worst-case variable-risk safety margin, and retains the intended phase-aware adaptive-risk behaviour.

Avoid claiming that fine-tuning alone creates a dramatic closed-loop safety gain. The correct interpretation is that the dissertation contribution is cumulative: control-side safety was established first, model-side reliability was improved next, and the final integrated system is the current best validated milestone.
