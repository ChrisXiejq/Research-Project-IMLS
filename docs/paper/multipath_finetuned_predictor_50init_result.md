# Fine-Tuned MultiPath Predictor: 50-Init Closed-Loop Validation

## Result Directory

`core/results/20260718_104740_50init_finetuned_predictor_validation`

This experiment validates the CARLA-domain fine-tuned MultiPath predictor in the closed-loop phase-aware adaptive-risk SMPC pipeline. The run uses 50 ego initial conditions and compares:

- `smpc_fixed_risk`
- `smpc_var_risk` with `adaptive_interaction_severity`

The run completed successfully with `exit_code=0`.

## Closed-Loop Safety Result

The post-CARLA trajectory gate reports an overall `PASS`.

| Policy | Gate pass | Solver failure max / mean | Min / mean footprint separation | Min / mean centre distance |
|---|---:|---:|---:|---:|
| `smpc_fixed_risk` | 50 / 50 | 0.0245 / 0.0063 | 0.8714 / 2.1449 m | 4.3740 / 5.4070 m |
| `smpc_var_risk` | 50 / 50 | 0.0244 / 0.0063 | 0.8833 / 2.1454 m | 4.3831 / 5.4093 m |

Both fixed-risk and variable-risk SMPC completed all 50 required rollouts without post-CARLA safety-gate failure.

## Aggregate Paper Metrics

| Policy | Completion time | Feasibility | Average solve time | `dmin_TV` | Completion valid | Solver failure frac |
|---|---:|---:|---:|---:|---:|---:|
| `smpc_fixed_risk` | 10.0160 s | 0.9937 | 0.0629 s | 5.4070 m | 1.0 | 0.0063 |
| `smpc_var_risk` | 10.0130 s | 0.9937 | 0.0885 s | 5.4093 m | 1.0 | 0.0063 |

The closed-loop safety and completion metrics remain very close between fixed-risk and variable-risk SMPC. This is consistent with the previous main experiment: the rule-aware supervisor dominates the final safety envelope, while the variable-risk method changes the solver-layer conservatism.

## Phase-Aware Risk Evidence

The adaptive-risk mechanism remains visible with the fine-tuned predictor:

| Conflict phase | Adaptive tightening | Fixed tightening | Adaptive - fixed | Floor applied frac |
|---|---:|---:|---:|---:|
| Approach / pre-clearance | 1.6800 | 1.6400 | +0.0400 | 1.0000 |
| Critical / pre-clearance | 1.7954 | 1.6400 | +0.1554 | 0.9911 |
| Near / pre-clearance | 1.8500 | 1.6400 | +0.2100 | 1.0000 |
| Critical / post-clearance | 1.2816 | 1.6400 | -0.3584 | 0.0000 |
| Near / post-clearance | 1.2816 | 1.6400 | -0.3584 | 0.0000 |

This supports the intended claim: adaptive risk is more conservative before the priority target clears the conflict area and more relaxed after clearance.

## Graphical Results

Post-hoc graphical results were generated from the saved 50-init validation outputs:

`core/results/20260718_104740_50init_finetuned_predictor_validation/figures`

Generated figures:

- `fig_finetuned_validation_01_safety_summary.svg`
- `fig_finetuned_validation_02_phase_risk_tightening.svg`
- `fig_finetuned_validation_03_var_minus_fixed_tightening.svg`
- `fig_finetuned_validation_04_supervisor_override_fraction.svg`
- `fig_finetuned_validation_05_acceleration_delta.svg`

These figures are suitable for a supervisor update because they show the main safety result, the phase-aware adaptive-risk behaviour, the adaptive-minus-fixed risk gap, and the interaction between solver-layer differences and supervisor intervention.

## Paper-Safe Claim

A conservative statement is:

> A 50-init closed-loop validation with the CARLA-domain fine-tuned MultiPath predictor shows that both fixed-risk and phase-aware adaptive-risk SMPC satisfy the post-CARLA safety gate for all required rollouts. The fine-tuned predictor remains compatible with the closed-loop SMPC pipeline, and the adaptive-risk mechanism still produces the intended phase-aware conservatism: tighter risk before target clearance and relaxed risk after clearance.

It should not be claimed that the fine-tuned predictor alone improves closed-loop safety over fixed-risk SMPC, because both policies already pass the gate and their final trajectory-level metrics remain close under the rule-aware supervisor.
