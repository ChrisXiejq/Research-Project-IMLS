# SF4 Prospective Corrected-Supervisor Behavioural-Authority Ablation

Status: **frozen before any init106--115 outcome is observed** (2026-08-14).

Pre-outcome amendment: before any smoke or formal treatment outcome, an
adversarial implementation audit added two already supervisor-motivated
secondary endpoints---cautious-approach progress and signed stop-line error---
to align the causal SF4 analysis with comment 1. The same audit completed the
excluded runtime smoke from three path-covering cases to the full four-cell
risk-by-authority factorial by adding adaptive-on. No definition or smoke case
was chosen from observed treatment results.

## Question and exact intervention

SF4 asks whether applying every behavioural channel available in the corrected
`reduced_intervention` rule-aware supervisor masks the closed-loop difference
between adaptive risk and the original fixed-medium risk policy. This
"complete application authority" is not the historical `full` supervisor
configuration. The sole behavioural config difference is
`yield_supervisor_behavioural_authority_mode={on,off}`.

In `on`, the supervisor may shape the pre-solve reference, force reference
linearization, add the lane-entry heading cost, invoke an eligible rule-SMPC
bypass, replace the post-solver command, and carry release/recovery effects into
factual reference, control, desired speed and next-step `control_prev`. In
`off`, the interaction/yield estimator still runs and may feed adaptive-risk
allocation, but every supervisor behavioural candidate is evaluated in
separately persisted shadow state. Hash audits require the factual reference,
non-risk solver inputs, command and next state to remain nominal. Both arms have
the bypass candidate identically configured. Authority-on applies an eligible
bypass; authority-off logs the shadow request but always attempts the factual
SMPC solve.

This is not deletion of B1 prediction, the interaction estimator, adaptive-risk
allocation, collision monitoring or the SMPC safety constraints. Native CARLA
collision sensors record and terminate an adverse rollout but never change a
command.

## Fixed design and stopping rule

The matrix is B1 x {adaptive, original fixed-medium} x {authority on, authority
off} x {assertive, reactive} x init106--115: 80 rollouts. Each init is an
independent cluster containing all eight combinations, shuffled within block
using seed `20260814`. Only prespecified infrastructure faults may be retried.
Collision, controller fallback/non-acceptance, adverse raw solver return
status, yield failure and noncompletion remain scientific outcomes and are
never retried or replaced.

Collection stops after the 80 treatment keys have integrity-valid receipts and
the analysis receipt verifies. Effect direction, p-values, collision incidence,
or observed supervisor activity cannot trigger extra runs, replacement or
tuning.

Before the first formal receipt, exactly four excluded full-stack runtime
smokes use fixed init105/assertive: fixed-on, fixed-off, adaptive-on and
adaptive-off. They exercise the complete risk-by-authority factorial, including
the joint adaptive-risk plus applied-authority path and the adaptive-risk-only
off-arm path.
Init105 and its outputs never enter the 80-rollout evidence or analysis. The
smoke may reveal only runtime, integrity or manipulation defects; scientific
direction cannot be inspected or used for tuning.

## Estimands and inference

For every init, average over styles and compute

`DID_i = (adaptive - fixed-medium)_on - (adaptive - fixed-medium)_off`.

The sole primary outcome is failure-penalized completion time: completion step
divided by 20 Hz, or the prospectively fixed 30 s horizon for a native CARLA
collision event or zero-margin actual-bounding-box overlap, fixed-geometry
yield failure or noncompletion. Fixed-geometry means the single conflict-zone
outcome from the frozen controller route projections and 4.0 m radius; the
realised-trajectory-inferred zone is reported only as a sensitivity. A
violation after inflating each actor box by
the registered 0.25 m safety margin is reported separately and does not by
itself receive the failure penalty. Lower is better, but the test is two-sided. The main
report also gives four direct paired effects: adaptive-minus-fixed under
authority on; adaptive-minus-fixed under authority off; authority-on-minus-off
within adaptive; and authority-on-minus-off within fixed-medium.

Uncertainty uses a 10,000-resample cluster bootstrap over complete init blocks
(seed `20260814`). The exact two-sided sign-flip number is explicitly a
**sensitivity value under a symmetric cluster-effect assumption**, not
treatment-randomisation inference. The completion-time DID is the only primary
test; direct effects and all secondary outcomes are exploratory.

Controller fallback/non-acceptance is conditional on a factual SMPC attempt:
effective rule-SMPC-bypass steps are excluded from its numerator and
denominator. `applied.is_opt`/`solver.optimal` is interpreted only as the
implementation's decision to accept the returned command (including accepted
`SUBOPTIMAL` solutions), not strict optimizer optimality or feasibility. Raw
solver return-status counts and missing-status counts are reported separately,
along with bypass-requested, bypass-applied and factual-attempt counts. The
give-way stop clock is searched only from yield entry up to actual path release,
so a later goal/terminal stop cannot be misclassified. If either entry or
release is unobserved, the stop clock is censored rather than searched to the
end of the rollout.

The same DID and four direct paired effects are reported for cautious-approach
progress, first-stop conflict distance, signed stop-line error, stopped
duration and the three clearance/release clocks. Approach progress is the
frozen-route change from yield entry to first sustained stop (with the
conflict-distance difference used only when route coordinates are absent).
Stop--conflict is `conflict_s - ego_route_s` from the ego actor/reference point,
not bumper clearance. Signed stop-line error is `stop_s - ego_route_s`:
positive means upstream/short of the configured stop point and negative means
the reference point passed it. Positive approach progress merely means motion
toward the conflict after detection; no direction is automatically labelled
beneficial. Missing event clocks remain censored and are never imputed.

Collision and separation outputs retain three non-interchangeable definitions:
native CARLA callbacks; physical overlap of actual actor bounding boxes at
0.0 m inflation; and the stricter 0.25 m-per-actor margin-adjusted overlap and
minimum separation. The latter is a registered safety-margin diagnostic, not
renamed as a physical collision.

Computational cost is a prospectively instrumented exploratory secondary,
common to both arms and frozen before the excluded smoke and all formal
outcomes. Every scenario-loop invocation records `time.perf_counter` wall time
around ego `policy.run_step`, plus `policy.done()` after the call. This scope
includes interaction/risk allocation, solver update and solve, all supervisor
channels, action arbitration and policy-local telemetry. It excludes CARLA
tick waiting, rendering, other-agent policies and the common prediction
pipeline; `_make_predictions` is timed and reported separately.

Within each rollout, P50, P95, P99 and fractions above 50, 200 and 500 ms are
computed over active-planning invocations (`policy.done()==false` after the
call), excluding completion-tail calls that do not execute the planning
pipeline. These rollout summaries receive the same init-cluster blocking, DID
and four direct paired contrasts; simulation steps are never treated as
independent observations. Non-finite samples and exceptions are separately
counted and never imputed. Missing exploratory timing cannot invalidate the
primary outcome or authorise a replacement rollout. Wall time is a
machine/load-specific server diagnostic, not an embedded deployment benchmark,
deadline guarantee or claim of real-time feasibility.

## Implementation gate versus observed activity

The mandatory implementation/manipulation gate proves the candidate channels
exist, both arms have the intended semantics, the rule-SMPC bypass is
authority-gated, shadow state is isolated, and authority-off is neutral for
reference, linearization, heading cost, factual bypass, post-action,
recovery/release state and next-step control history. The
interaction estimator to adaptive-risk allocation is the sole allowed
authority-off estimator-to-solver route.

The gate also requires the raw per-step wall-time samples to reconcile exactly
with the counts, quantiles and threshold fractions frozen into the scenario
summary; this verifies instrumentation without judging which arm is faster.

Observed first-stage activity is a scientific result, not an integrity gate.
Requested frequency and intensity are reported for reference shaping, heading
cost, forced linearization, rule-SMPC bypass and post-action changes by authority, risk, style and
risk-by-style block. Zero activity anywhere—including the full matrix—does not
permit rerunning. If the full matrix is inactive, the paper must state that
authority assignment was implemented but these data cannot identify masking
conditional on an activated supervisor intervention.
