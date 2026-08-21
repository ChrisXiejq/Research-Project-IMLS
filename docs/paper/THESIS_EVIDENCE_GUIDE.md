# Thesis Study and Evidence Guide

Updated: 2026-08-15

This is the repository's only human-facing source for the study design, result
verdicts and evidence locations. The submission manuscript is maintained at
`../../../Jiaqi Xie Dissertation/main.tex`.

## 1. Research question and central claim

The project asks when a local improvement in motion prediction or risk
allocation remains useful after it enters a coupled predictor--risk--SMPC--
supervisor system at a CARLA give-way intersection.

The central finding is that task adaptation gives a large and consistent
in-distribution prediction improvement, but neither additional Transformer
complexity nor adaptive risk gives uniform additional value. Offline prediction
quality and closed-loop utility must therefore be evaluated together.

## 2. Frozen experimental design

### Prediction experiment

- CARLA Town05 give-way scenario;
- 200 data-collection rollouts;
- rollout-disjoint split: 160 train, 20 validation and 20 test rollouts;
- 2 s prediction horizon;
- B0 pretrained MultiPath control;
- B1 task-adapted final prediction head;
- B2-M/B2-D MLP residual controls;
- T1/T2 Transformer residual adapters;
- five trainable variants × seeds 11, 23 and 37;
- validation rollout-macro NLL for selection and one frozen test evaluation;
- constant velocity, clipped constant acceleration and train-mean route prior
  as physical baselines.

### Corrected closed-loop experiment

The primary matrix is:

```text
2 predictors × 4 risk policies × 2 target styles × 5 paired init groups
= 80 rollouts
```

Predictors are B0 and B1. Risk policies are fixed aggressive, fixed medium,
fixed conservative and adaptive. Target styles are assertive and reactive.
Primary outcomes are event-clock completion time and minimum physical
vehicle-footprint separation; collision, yield and completion failures are
binary guards.

### Supervisor-authority experiment

The externally requested mechanism ablation is:

```text
B1 × 2 risk policies × authority on/off × 2 target styles × 10 init groups
= 80 rollouts
```

It compares adaptive with fixed medium while switching the complete behavioural
application authority of the corrected rule-aware supervisor. It is a mechanism
analysis for H4, not a fifth headline hypothesis.

## 3. Headline hypothesis verdicts

| ID | Question | Evidence | Verdict |
| --- | --- | --- | --- |
| H1 | Does B1 improve prediction relative to B0? | NLL 2.171→1.857; ADE 1.283→0.100 m; FDE 2.644→0.121 m; all five test groups favour B1 | Supported |
| H2 | Do Transformer adapters add consistent value? | T1 slightly improves over B2-M, T2 slightly degrades relative to B2-D, neither exceeds B1; sequence ablations confirm input use | Not supported for tested configurations |
| H3 | Does the B1 offline gain transfer consistently? | Jointly favourable completion/separation in 2/8 policy--style conditions | Conditional transfer only |
| H4 | Does adaptive risk dominate fixed controls? | Dominance in 3/12 prespecified comparisons | Context dependent; no universal dominance |

All 80 corrected R3 rollouts completed without an observed native collision,
footprint collision, yield-order failure or completion failure. These are event
counts, not proof of zero population risk. Continuous footprint separation is
the discriminating safety-margin measure.

## 4. Supervisor feedback closure

The fine-tuning audit replaced the earlier 0.98%→100% mode-matching statement
with rollout-macro NLL/ADE/FDE and paired test-group evidence. Solver analysis
separates factual solve attempts, controller acceptance/fallback and bypass
steps instead of treating every historical logger row as MPC infeasibility.

SF4 completed all 80 prespecified rollouts and produced an active authority
intervention. Supervisor application authority materially changes vehicle
behaviour and adverse outcomes, so it is not an irrelevant layer. However, the
primary difference-in-differences for failure-penalised completion time is
0.020 s with a cluster-bootstrap 95% interval of [-0.260, 0.338] s. The result
does not support the simple explanation that the supervisor selectively erases
the adaptive-versus-fixed-medium difference; its major effect applies to both
risk policies.

## 5. Claim boundaries

Allowed claims:

- B1 strongly improves prediction on the frozen Town05 give-way distribution;
- the tested Transformer adapters use temporal inputs but show no consistent
  additional advantage;
- the prediction gain has conditional rather than uniform closed-loop value;
- adaptive risk is a context-dependent operating point;
- predictor, risk policy, target response, solver and supervisor jointly shape
  executed behaviour.

Do not claim:

- Transformers are generally inferior for motion prediction;
- adaptive risk is useless;
- the supervisor is the sole cause of similar trajectories;
- zero observed collisions proves safety or statistical equivalence;
- the results generalise to other maps or real roads without further evidence.

## 6. Canonical evidence paths

Primary corrected results:

```text
docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/
docs/paper/generated/distinction_v1/10_four_hypothesis_evidence/
```

Supporting ML ablations:

```text
docs/paper/generated/distinction_v1/01_physical_baselines/
docs/paper/generated/distinction_v1/02_input_ablations/
docs/paper/generated/distinction_v1/03_training_budget/
docs/paper/generated/distinction_v1/04_in_loop_prediction/
docs/paper/generated/distinction_v1/06_split_balance/
```

Supervisor-feedback evidence:

```text
docs/paper/generated/supervisor_feedback_v1/
docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/
```

Generated assets are immutable. Correct a generator and rebuild its outputs;
never hand-edit a reported number.

## 7. Current closure state

R3 and SF4 are complete. The existing M1/W1 completion receipts still identify
their evidence cut as `pre-sf4`, so the final non-CARLA task is to rebuild the
evidence/manuscript audit chain after integrating SF4. No additional large
CARLA matrix is planned.

The internal repository manuscript at `docs/dissertation/latex/` remains only
because the evidence scripts reference it. The reader-facing manuscript is
`../../../Jiaqi Xie Dissertation/main.tex`.

## 8. Reproduction entry points

From the repository root:

```bash
.venv-precarla/bin/python core/scripts/models/build_r3_paper_synthesis.py
.venv-precarla/bin/python core/scripts/models/build_m1_evidence_package.py
.venv-precarla/bin/python -m unittest discover \
  -s core/scripts/models/tests -p 'test_*.py'
```

The exact number of tests is allowed to increase; require the current discovery
run to pass rather than relying on an old hard-coded count.

