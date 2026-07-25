# Dissertation Guidance After Supervisor Feedback

This document is the canonical guidance for the dissertation direction after the supervisor feedback. It replaces older milestone-status notes and the initial paper outline. Future experiment decisions, code changes, result interpretation, and paper writing should be checked against this document first.

## 1. Final Thesis Goal

The dissertation should not claim that adaptive variable risk universally produces a visibly better final trajectory than fixed risk in every rollout. In this give-way intersection, a rule-aware supervisor is necessary for traffic-rule compliance and final safety, and that supervisor can mask differences between fixed-risk and adaptive-risk SMPC at the executed-control layer.

The defensible final goal is:

```text
Develop and evaluate a phase-aware adaptive-risk SMPC framework for an unsignalised give-way intersection, integrated with a rule-aware supervisor and a fine-tuned multimodal predictor. The framework should reduce unnecessary conservative stopping, preserve give-way safety, and show that adaptive risk provides a more interpretable and favourable risk-allocation / safety-performance trade-off than a family of fixed-risk baselines.
```

The proposal's advantage should be proven through a layered evidence chain:

```text
Layer 1: Supervisor masking and conservative stopping diagnosis.
Layer 2: Reduced-intervention supervisor that reduces unnecessary override while preserving safety.
Layer 3: Solver-layer adaptive-risk behaviour: pre-clearance tightening and post-clearance relaxation.
Layer 4: Fixed-risk frontier comparison: adaptive risk should be competitive or Pareto-favourable against conservative / medium / aggressive fixed-risk settings.
Layer 5: Prediction-model sanity: fine-tuning improves CARLA held-out mode ranking without overclaiming general prediction capability.
```

## 2. Lessons From The Reference Paper

The reference paper, *Predictive Control for Autonomous Driving With Uncertain, Multimodal Predictions*, proves its `Proposed` method against `Fixed Risk` in an intersection setting because its comparison is mostly internal to the SMPC optimizer:

- final control is essentially the SMPC output, not heavily filtered by an external right-of-way supervisor;
- `Proposed` optimizes both feedback policies and risk levels;
- `Fixed Risk` keeps risk levels fixed;
- the main metrics are optimizer-facing: SMPC feasibility, collision probability, trajectory deviation, comfort, mobility, and solve time.

This dissertation cannot copy that claim directly because the give-way setting has an explicit right-of-way rule. The rule-aware supervisor is not an implementation flaw; it is part of a realistic safety architecture. Therefore, the paper should adapt the reference-paper logic as follows:

```text
Reference paper claim:
Optimizing risk levels improves SMPC feasibility and safety-performance metrics compared with one fixed-risk ablation.

This dissertation claim:
In a rule-constrained give-way scenario, adaptive risk improves or clarifies optimizer-level risk allocation, while supervisor ablation explains how final actions are filtered for safety. Adaptive risk must be compared with a fixed-risk frontier, not only with one fixed-risk baseline.
```

## 3. Supervisor Feedback Status

### 3.1 Conservative Early Stopping

Status: mostly addressed, with formal evidence.

Evidence so far:

- Step-1 post-hoc diagnostics showed that conservative early stopping is mainly caused by shared supervisor / yield logic rather than adaptive risk alone.
- Formal 5-init supervisor ablation showed that reduced intervention improves early-stop behaviour while preserving safety.
- In the formal ablation:
  - fixed-risk first-stop distance dropped from `8.403 m` to `5.263 m`;
  - fixed-risk waiting time dropped from `8.040 s` to `4.200 s`;
  - fixed-risk clearance delay dropped from `3.720 s` to `1.440 s`;
  - adaptive-risk showed the same pattern.

Paper interpretation:

```text
The original conservative behaviour is largely a supervisor/yield-logic effect. Reduced intervention reduces unnecessary stopping and post-clearance delay, but adaptive-risk superiority still requires a separate fixed-risk frontier analysis.
```

### 3.2 Feasibility / Infeasibility

Status: partially addressed; must continue for all new sweeps.

Evidence so far:

- The old 50-init result only reported aggregate feasibility, which is not sufficient.
- Formal ablation now localises reduced-supervisor infeasible steps to `critical/pre-clearance` phases, especially `approach_yield_line` and `cautious_approach_observed_target`.
- Full supervisor has fewer infeasible steps because deterministic intervention shields the optimizer.

Required for final paper:

- report infeasible steps by policy, supervisor mode, phase, init, and distance-to-conflict;
- distinguish solver-layer infeasibility from final safety outcome;
- explain whether supervisor fallback preserved safety after infeasible solver steps.

### 3.3 Fine-Tuned Predictor Sanity

Status: first sanity pass completed; avoid overclaiming.

Current acceptable claim:

```text
Fine-tuning improves CARLA held-out split mode ranking / probability calibration on the same test set.
```

Current forbidden claim:

```text
The predictor is fully solved or universally accurate because top-probability mode is best reaches 100%.
```

Required evidence:

- same train/val/test split;
- same test samples for pretrained and fine-tuned models;
- top-1 ADE/FDE and minADE/minFDE;
- split leakage check;
- optional shuffled-label or mismatched-label sanity check if time permits.

### 3.4 Supervisor Contribution Isolation

Status: first formal layer completed; adaptive-risk contribution still incomplete.

Completed:

- Formal supervisor ablation:

```text
core/results/20260725_125938_5init_formal_supervisor_ablation
```

- Report:

```text
core/results/20260725_125938_5init_formal_supervisor_ablation/formal_supervisor_ablation_analysis/formal_supervisor_ablation_report.md
```

Main conclusion:

```text
Full supervisor strongly masks fixed/adaptive final behaviour differences. Reduced supervisor improves conservative behaviour, but final-layer adaptive-risk advantage remains weak in the 5-init ablation.
```

Still required:

- adaptive-risk sensitivity sweep under frozen reduced supervisor;
- fixed-risk frontier baseline;
- solver-layer vs final-layer plots for the selected comparison.

## 4. Research Questions And Hypotheses

### RQ1

Why does the ego vehicle stop too early in the initial system?

Hypothesis:

```text
H1: Conservative early stopping is mainly caused by rule-aware supervisor / yield logic, not by adaptive risk alone.
```

Evidence:

- supervisor active fraction;
- solver bypass fraction;
- nominal-final acceleration delta;
- first-stop distance;
- waiting time after stop;
- delay after target clearance.

### RQ2

Can a reduced-intervention supervisor reduce unnecessary conservatism while preserving safety?

Hypothesis:

```text
H2: A reduced-intervention supervisor decreases early stopping and clearance delay while preserving footprint safety, give-way safety, and route completion.
```

Evidence:

- formal full vs reduced supervisor ablation;
- video qualitative gate;
- post-turn lane keeping non-regression;
- infeasibility phase analysis.

### RQ3

Does phase-aware adaptive risk provide meaningful risk-allocation behaviour?

Hypothesis:

```text
H3: Adaptive risk tightens chance constraints before target clearance and relaxes them after target clearance, producing solver-layer behaviour consistent with the give-way interaction phase.
```

Evidence:

- risk tightening by conflict-distance bucket and clearance phase;
- nominal SMPC acceleration;
- solver-layer target probability;
- adaptive-risk sensitivity variants.

### RQ4

Does adaptive risk outperform fixed-risk baselines fairly?

Hypothesis:

```text
H4: Compared with a fixed-risk frontier, adaptive risk provides a more favourable safety-performance trade-off, especially in solver feasibility, release delay, supervisor intervention, or nominal-final action consistency.
```

Evidence:

- fixed conservative / medium / aggressive baselines;
- adaptive selected setting from sensitivity sweep;
- Pareto plot using safety, feasibility, delay, completion time, and intervention fraction;
- same init set, same predictor, same supervisor.

## 5. Experiment Plan

### Experiment A: Existing Best 50-Init Diagnostic

Purpose:

- diagnose early stopping;
- separate nominal solver behaviour from final supervised behaviour;
- analyse infeasible steps by phase.

Status: completed.

Use as background evidence, not as final adaptive-risk proof.

### Experiment B: Formal Supervisor Ablation

Matrix:

| Policy | Supervisor |
|---|---|
| fixed-risk | full |
| adaptive-risk | full |
| fixed-risk | reduced_intervention |
| adaptive-risk | reduced_intervention |

Status: completed at 5-init scale.

Claim supported:

```text
Supervisor contribution is substantial. Reduced supervisor improves conservative early stopping while retaining safety.
```

Claim not supported:

```text
Adaptive risk is clearly superior in final trajectory metrics.
```

### Experiment C: Adaptive-Risk Sensitivity Sweep

Current active experiment:

```text
YIELD_SUPERVISOR_MODE=reduced_intervention
VARIANT_SET=sensitivity
INIT_COUNT=5
```

Purpose:

- identify reasonable adaptive-risk settings;
- test pre-clearance floor, post-clearance relaxation, and severity gain;
- measure solver-layer risk allocation;
- check whether any adaptive setting improves final-layer metrics without breaking safety.

Important limitation:

```text
This sweep alone cannot prove proposal superiority because it still compares against only the default fixed-risk baseline.
```

### Experiment D: Fixed-Risk Frontier Baseline

This is the next essential experiment after the current sensitivity sweep.

Required matrix:

| Method | Description |
|---|---|
| fixed conservative | higher tightening / lower allowed risk |
| fixed medium | current default fixed-risk |
| fixed aggressive | lower tightening / higher allowed risk |
| adaptive selected | best defensible adaptive setting from Experiment C |

All runs must use:

- same reduced-intervention supervisor;
- same fine-tuned predictor;
- same init set;
- same post-CARLA gate;
- same infeasibility phase analysis.

Decision rule:

```text
Adaptive risk is useful if it is not Pareto-dominated by the fixed-risk frontier and shows at least one stable advantage in safety, feasibility, release delay, supervisor intervention, or solver-final consistency.
```

### Experiment E: Prediction Sanity

Purpose:

- defend the fine-tuned predictor result;
- avoid overclaiming `100%` top-probability mode is best.

Required outputs:

- split integrity report;
- same-test-set comparison;
- top-1 vs minADE/minFDE;
- optional shuffled-label or mismatched-label sanity check.

## 6. Metrics To Report

### Behaviour Metrics

- first stop distance to conflict;
- waiting time after first stop;
- delay after target clearance;
- completion time;
- post-turn lane keeping and heading completion;
- qualitative video gate for representative rollouts.

### Safety Metrics

- post-CARLA gate PASS count;
- footprint collision;
- minimum footprint separation;
- minimum centre distance;
- give-way violation;
- target clearance timing.

### Solver / Risk Metrics

- SMPC feasibility / infeasible fraction;
- infeasible phase and distance-to-conflict;
- risk tightening by bucket and clearance phase;
- target probability / risk target probability;
- solve time;
- nominal acceleration;
- final applied acceleration.

### Supervisor Metrics

- supervisor active fraction;
- solver bypass fraction;
- hard safety intervention fraction;
- nominal-final acceleration delta;
- nominal-final acceleration delta when supervisor is active.

### Frontier Metrics

- safety versus completion time;
- safety versus post-clearance delay;
- infeasible fraction versus completion time;
- supervisor active fraction versus release delay;
- adaptive setting position relative to fixed-risk conservative / medium / aggressive settings.

## 7. Paper Structure

### Introduction

Motivate:

- autonomous driving under multimodal prediction uncertainty;
- unsignalised give-way interactions require both uncertainty-aware planning and rule compliance;
- fixed-risk SMPC is not phase-aware;
- pure optimizer output is not sufficient for safety-critical rule compliance.

Main claim:

```text
The dissertation combines phase-aware adaptive-risk SMPC, a fine-tuned multimodal predictor, and a rule-aware supervisor, then explicitly analyses how the supervisor affects final behaviour.
```

### Literature Review

Use three threads:

- stochastic / chance-constrained MPC with multimodal predictions;
- risk allocation and fixed-risk limitations;
- runtime safety layers, supervisors, shields, and rule-aware driving.

### Method

Explain:

- CARLA give-way scenario;
- MultiPath predictor and fine-tuning;
- SMPC formulation and fixed-risk baseline;
- phase-aware adaptive-risk mapping;
- rule-aware supervisor and why it is required.

### Experiments

Order:

1. best 50-init diagnostic;
2. formal supervisor ablation;
3. adaptive-risk sensitivity sweep;
4. fixed-risk frontier comparison;
5. predictor sanity check.

### Results

Avoid a single aggregate table as the main evidence. Use:

- supervisor ablation table;
- infeasibility phase table;
- solver-layer vs final-layer plots;
- fixed-risk frontier / Pareto plots;
- representative time-series;
- predictor sanity table.

### Discussion

Key points:

- full supervisor masks final-layer fixed/adaptive differences;
- reduced supervisor reduces unnecessary conservatism but does not eliminate the need for safety supervision;
- adaptive risk is best interpreted as optimizer-level risk allocation;
- fixed-risk frontier is the fair baseline;
- final trajectory differences may remain small in rule-critical phases, which is an expected consequence of a safety architecture.

## 8. Paper-Safe Claims

Allowed:

```text
The original conservative early stop is mainly caused by supervisor/yield logic.
```

```text
Reduced intervention decreases unnecessary waiting and clearance delay while preserving give-way safety.
```

```text
Adaptive risk applies stronger pre-clearance tightening and post-clearance relaxation, matching the give-way interaction phase.
```

```text
Adaptive risk should be evaluated against a fixed-risk frontier; its contribution may appear in solver-layer behaviour and Pareto trade-off rather than raw final trajectory difference.
```

```text
Fine-tuning improves CARLA held-out split mode ranking / probability calibration.
```

Forbidden:

```text
Adaptive risk alone guarantees safe yielding.
```

```text
Adaptive risk universally dominates fixed risk in final executed trajectory metrics.
```

```text
The fine-tuned predictor is generally solved because top-probability mode is best is 100%.
```

```text
This dissertation directly outperforms the reference paper numerically.
```

## 9. Immediate Next Actions

1. Finish or recover the current 5-init adaptive-risk sensitivity sweep.
2. Analyse it with:
   - post-CARLA gate;
   - supervisor feedback diagnostics;
   - infeasibility phase analysis;
   - solver-layer vs final-layer comparison.
3. Select one defensible adaptive setting if the sweep supports it.
4. Implement and run a 5-init fixed-risk frontier baseline:
   - fixed conservative;
   - fixed medium;
   - fixed aggressive;
   - selected adaptive setting.
5. Only after the fixed-risk frontier result is clear, decide whether a new 50-init milestone is justified.

## 10. Decision Gate Before 50-Init

Do not run a new 50-init milestone unless all conditions below are satisfied:

- formal supervisor contribution has been reported;
- infeasibility has been analysed by phase;
- fine-tuning sanity is documented;
- adaptive risk has been compared against fixed-risk frontier;
- at least one stable advantage is visible, or the thesis explicitly reframes the result as solver-layer contribution plus supervisor masking limitation.

