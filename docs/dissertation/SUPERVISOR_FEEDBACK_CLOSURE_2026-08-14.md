# Supervisor-feedback closure plan

Date: 2026-08-14
Status: local implementation and regression gates pass; immutable R3-archive
execution (SF1/SF2) and the prospective CARLA matrix (SF4) remain pending
Scope: the four comments in Jiaqi's previous supervisor feedback

## Closure standard

A comment is **closed** only when all four layers exist:

1. a precise scientific question and estimand;
2. code that produces the required evidence from immutable inputs;
3. machine-readable results with hashes and an explicit independent unit;
4. dissertation text that reports the result, including a negative result or
   limitation, without changing the original H1--H4 decisions.

Passing a software or integrity gate is not evidence that a scientific claim
is true. Simulation steps and overlapping prediction windows are not treated
as independent observations. Infrastructure reruns are allowed only under the
frozen failure taxonomy; collisions, controller fallback/nonacceptance, adverse
raw solver statuses, null effects and
unfavourable treatment effects are retained as scientific outcomes.

The four comments do not create a fifth headline hypothesis. The additional
supervisor experiment is a preregistered **mechanism audit for H4**.

## Comment 1: conservative early stopping and late release

### Question

Does the corrected system keep approaching after first activating give-way,
stop near its configured route stop point rather than far upstream, and resume
promptly after the target path is nominally clear?

### Evidence and independent unit

Use the immutable corrected R3 logs (80 rollouts; five independent ego-init
groups per cell). The audit is explicitly post hoc because the metrics were
defined in response to the supervisor's qualitative observation.

For every rollout, generate:

- route progress between first active yield detection and first sustained stop;
- signed frozen-route distance from the ego actor/reference point at first
  sustained stop to the conflict point (`conflict_s - ego_route_s`, not bumper
  clearance; positive upstream);
- signed distance from that stop to the configured route stop point;
- duration stopped before path release (necessary waiting, not automatically a
  performance defect);
- delay from nominal conflict clearance to controller release, latency from
  release to sustained speed above 0.8 m/s, and recovery relative to the
  stricter buffered-clearance signal;
- event-chain completeness and source of the release signal.

For each behaviour metric, adaptive risk is also compared with aggressive,
medium and conservative fixed risk by first averaging the four
predictor--style nuisance conditions within each init group and then forming a
paired adaptive-minus-fixed effect. This post-hoc contrast directly tests
whether risk formulation explains the observed stopping/release pattern; it
does not turn the mechanism audit into a fifth headline hypothesis.

A stop is speed at or below 0.15 m/s for at least three consecutive 20 Hz
steps. Resumption is speed at or above 0.8 m/s for at least three consecutive
steps. These thresholds are sensitivity assumptions, not a naturalistic human
driving standard. The stop-search interval is the half-open registered
give-way episode from yield entry up to, but excluding, path release. If entry
is observed but release is absent, the stop window has no defensible endpoint:
stop and approach-to-stop values are marked as censored instead of searching
the later route for a terminal/goal stop.

### Acceptance criterion

- All promoted logs match the hashes recorded in the corrected R3 audit.
- Exactly 80 promoted treatment rollouts are analysed; attempt and quarantine
  directories are excluded.
- Results are summarised over the five init groups, never over simulation steps
  as if they were independent.
- The paper reports configured clearance (`conflict_s - stop_s`) alongside
  conflict distance and signed stop-line error (`stop_s - ego_route_s`, positive
  upstream/short and negative after passing the configured stop point),
  so a physically required vehicle-footprint margin is not mislabeled as
  arbitrary conservatism.
- Any missing stop/release event is reported as an outcome, not silently
  discarded.
- A terminal stop outside a complete entry-to-release episode can never be
  relabelled as a conflict-point stop.

### Implementation

`core/scripts/models/analyze_supervisor_feedback_behaviour.py` produces the
rollout table, 16-cell summary, analysis contract and hash receipt. It must be
run once against the archived R3 raw logs. No new CARLA collection is required
for this comment.

Historical full-versus-reduced-supervisor results may be described only as
diagnostic context: several release/recovery settings changed together and the
old controller predates corrected R1, so that comparison is not a pure causal
ablation.

## Comment 2: adaptive-risk timing, controller acceptance and fallback

### Questions

1. What recorded optimiser solve-stage timing does adaptive risk add relative
   to all three fixed operating points, and what complete ego-policy wall time
   is observed prospectively in SF4?
2. At which phases and for which logged reasons are attempted solves rejected
   by the controller and replaced by fallback?
3. What fallback is applied, and what happens to the subsequent trajectory?

### Required reporting

- finite recorded CasADi solver wall-time distribution by policy, including
  P50/P95/P99, explicitly excluding prediction, controller preprocessing,
  supervisor logic and the CARLA loop;
- prospective SF4 prediction-pipeline and complete ego-policy `run_step`
  wall-time P50/P95/P99 as a server-side diagnostic, not a deployment
  real-time guarantee;
- paired policy differences at the ego-init-group level;
- exceedance rates for 50 ms (20 Hz simulation tick), 200 ms (SMPC planning
  interval) and the frozen 500 ms engineering gate, whenever complete
  step-level timings are available;
- fallback/nonaccepted steps, affected rollouts and per-rollout nonacceptance
  fraction;
- return status, prediction validity, yield phase, reference state, risk mode,
  fallback/control source and supervisor activity at every failed solve;
- a join from every fallback/nonaccepted event to exactly one canonical
  rollout's downstream completion, collision, yield and physical-separation
  outcomes; multiple events may legitimately belong to the same rollout.

Every raw solver-execution decision must first be assigned to exactly one of
three classes: `rule_bypass_no_solve`, `attempted_accepted`, or
`attempted_fallback_or_nonaccepted`. Rows without solver/problem/applied telemetry are
retained as control-context records but remain outside the solver-execution
denominator. Under the corrected-R3 logger contract, however, any such
telemetry-absent row also closes the final SF2 integrity gate: it cannot be
silently excluded when the audit cannot determine whether a solve was
attempted. It must be reported and resolved from immutable provenance before a
final controller-acceptance claim is released. Prediction validity is
contextual telemetry, not an execution
state: a row with `prediction_valid=false` is still an attempt when
solver/problem/applied telemetry proves that the optimiser was called. A
rule-yield bypass may carry `optimal=true` and a zero-second marker for
control-flow compatibility, but it is not a solve attempt and enters neither
the timing distribution nor the controller-acceptance denominator. Bypass count/rate
is reported separately by policy and by each of the five ego-init groups.

The historical logger field named `optimal` is a controller-acceptance flag:
the SMPC wrapper also sets it for a CasADi `SUBOPTIMAL` result that it elects
to execute. It is therefore neither mathematical optimality nor a feasibility
certificate. Raw return status is retained separately. Attempts whose timing
is not finite must not be included in the finite timing distribution or
imputed as fast solves. Synchronous CARLA execution is not proof of
wall-clock real-time deployment.

### Acceptance criterion

The dissertation must distinguish:

1. per-step controller acceptance versus fallback, with raw solver return
   status;
2. fallback or supervisor recovery;
3. eventual rollout completion; and
4. observed collision/yield outcomes.

The phrase "zero failures establish nominal feasibility" is prohibited when
fallback/nonaccepted solver steps exist. A valid formulation is:

> All rollouts completed without an observed collision or yield failure despite
> non-zero fallback/nonaccepted solver events; rollout completion is not a
> per-step MPC feasibility certificate.

This is an offline analysis of existing R3 evidence and requires no new CARLA
collection.

The repository reproduces the earlier 104.24 ms versus 90.23 ms result
(paired +14.01 ms) and 264/17,230 non-optimal/debug-row diagnostic, but these
are now explicitly `preliminary_legacy_conflated`. The legacy latency includes
zero-second rule-bypass/no-solve markers, and the legacy logger-rate
denominator includes all logged control contexts, including bypass rows and
rows without solver telemetry. Neither is a final solver-timing or controller-
acceptance result. Final SF2 reporting is blocked until the raw archive has
hash-verified every log, verified unique strictly increasing step IDs,
reproduced the legacy aggregate, completed the execution classification,
joined downstream outcomes, and emitted finite recorded solver timing,
deadline and controller-acceptance results with bypass and non-finite timing
separated.

## Comment 3: implausible 0.98% to 100% fine-tuning result

### Resolution target

The old 0.98%-to-100% top-probability/oracle-best-mode hit rate is formally
withdrawn as evidence of trajectory quality. It was not a thresholded
trajectory-accuracy endpoint. It is replaced by a frozen evaluation using
rollout-macro NLL and explicitly aggregated ADE/FDE, with the pretrained B0,
physical baselines and five held-out ego-init groups.

### Acceptance criterion

- State what the old mode-ranking hit rate measured and that its headline
  interpretation was withdrawn after audit; do not merely omit it and leave
  the reader to infer what happened.
- Report the 160/20/20 rollout-group split, train-only normalisation, duplicate
  audit, frozen B1/seed-37 choice and one-shot test opening.
- Produce B0--B1 results separately for each of the five test init groups.
- Hash-bind the exact shared test JSONL, anchors, evaluation/calibration
  schemas, horizon, subset, leakage flag, per-init counts and all 20 rollout
  keys/counts; equal aggregate counts alone are insufficient.
- Do not use overlapping windows as independent replicates.
- Never subtract a sample-micro B1 statistic from a rollout-macro baseline.
- Report response-active tail NLL and the small active-tail sample size even
  though it is unfavourable to B1.
- Retain capacity, epoch-ceiling and raster-dominance limitations.

No retraining is required unless the reproducible re-aggregation changes the
qualitative conclusion. The selected weights and test set remain frozen.

The corrected frozen-test result is now fixed. At the common rollout-macro
aggregation, B0 to B1 changes NLL from 2.170712 to 1.857094 nats/step, ADE from
1.282672 to 0.099658 m and FDE from 2.644311 to 0.120895 m. The corresponding
five-init macro effects favour B1 in 5/5 groups for each metric, but the
smallest possible two-sided exact sign-flip sensitivity value is 0.0625 under
a symmetric paired-cluster-effect assumption; it is not treatment-
randomisation inference. The result is therefore a
large, directionally consistent in-distribution effect rather than ``100%
accuracy''. In the small response-active tail (15 overlapping windows),
frozen calibration is worse for B1 (NLL 8.573) than B0 (2.959), and this
limitation is retained.

## Comment 4: fixed/adaptive comparison with and without the supervisor

### Why the previous ablation is insufficient

The historical `full` versus `reduced_intervention` comparison changed several
release/recovery parameters and did not include a true supervisor-off arm.
Corrected R3 used the same reduced-intervention stack everywhere. Supervisor
activity telemetry measures association; it does not identify the causal
effect of applying every behavioural channel available in that corrected
reduced-intervention stack.

### Exact causal treatment

The single treatment field toggles **the complete application authority of the
corrected `reduced_intervention` supervisor**. This is not the historical
`full` supervisor configuration. Both arms have the same predictor, estimator, configured
rule-SMPC bypass, risk interface and candidate computations.

- `on`: supervisor requests may affect reference shaping, forced
  linearisation, heading cost, rule-SMPC bypass, post-solver action,
  release/recovery state and next-step control history;
- `off`: the same requests are logged in shadow telemetry, bypass requests do
  not skip the solve, and non-risk solver/control/state channels remain
  neutral. Estimator output may still feed adaptive-risk allocation.

The native collision monitor remains active in both arms and may
record/terminate a rollout, but it must not alter control. Zero requested
activity is a scientific first-stage result, never an integrity failure or
rerun trigger.

### Matrix and estimand

Use the selected B1 predictor stack to control the nuisance predictor factor:

\[
2\ \text{risk policies}\times2\ \text{authority arms}\times
2\ \text{target styles}\times10\ \text{new init groups}=80\ \text{rollouts}.
\]

- risk: adaptive versus the original fixed-medium baseline;
- authority: complete application authority of the corrected
  `reduced_intervention` supervisor on versus shadow-only off;
- style: assertive and reactive;
- new init groups: 106--115, accepted only after spawn/geometry preflight;
- execution: block randomised with transactional, resumable receipts.

Fixed-medium is the baseline pair shown in the supervisor's criticised figure,
so SF4 identifies authority masking for that pair only.  It does not identify
the authority interaction at the aggressive or conservative fixed operating
points; those remain covered only by the non-causal R3 mechanism contrasts.

The primary mechanism estimand is the difference in differences

\[
(\text{adaptive}-\text{fixed})_{\text{authority on}}-
(\text{adaptive}-\text{fixed})_{\text{authority off}}.
\]

Its exact two-sided sign-flip value is a small-sample sensitivity analysis
under a symmetric cluster-effect assumption, not treatment-randomisation
inference. The effect estimate and block-bootstrap interval remain primary to
interpretation.

The 30 s primary failure penalty applies to a native CARLA collision or a
zero-margin overlap of the actual actor bounding boxes, the single
route-projected fixed-geometry yield failure, or noncompletion.  The
realised-trajectory conflict-zone rule is sensitivity-only.  Overlap after
inflating each actual box by 0.25 m per actor is a stricter safety-margin
violation and is not relabelled as a physical collision.

Report completion, margin-adjusted actual-bounding-box separation, native and
zero-margin physical collision outcomes, first-stop
distance, cautious approach, clear-to-resume latency, nominal-versus-executed
acceleration and solver/fallback events. Also report prediction-pipeline and
complete ego-policy wall time as secondary server-side diagnostics. The result
may show strong masking,
weak masking, amplification or no interaction; all are valid outcomes.

### Stop rule

If all 80 prespecified rollouts pass integrity and all adverse scientific
outcomes are retained, this closes the targeted CARLA mechanism study. Its
direction must not trigger further tuning or larger collection. Cross-map,
naturalistic-behaviour and larger-sample work remains future work rather than
an outcome-selected dissertation requirement.

The implementation is isolated behind one behavioural-authority treatment
boundary and a transactional runner. The runner never starts or changes CARLA, supports
preflight-only, read-only progress and receipt-based resume, and produces a
deterministic compact evidence archive. Local SF4/attempt, R3 geometry/control
and full analysis regressions pass; this is an engineering readiness result,
not a scientific SF4 result.

## Execution order and current status

| Stage | Work | CARLA required | Current status | Completion condition |
|---|---|---:|---|---|
| SF0 | Freeze this closure standard and mechanism definitions | No | complete | This document reviewed with generated contracts |
| SF1 | R3 approach/stop/release behaviour audit | No | code complete; raw archive run pending | 80-row hash-verified table and paper subsection |
| SF2 | R3 solver-timing, controller-acceptance and fallback taxonomy | No | legacy aggregate reproduced but marked preliminary; corrected raw audit pending | Raw execution classification; monotonic unique steps; finite solver timing; separate bypass/non-finite timing; controller acceptance; fallback causes and downstream outcomes |
| SF3 | Frozen-test fine-tuning re-aggregation | No | complete | Exact test/anchor/key/count contract; five-init paired table; consistent physical-baseline comparison and tail limitation |
| SF4 | Complete supervisor behavioural-authority on/off preflight and formal matrix | Yes, 80 rollouts | code/prereg/tests complete; run pending | Integrity-complete receipt irrespective of direction or observed activity |
| SF5 | Rebuild dissertation and evidence package | No | pending SF1/SF2/SF4 | All claims resolve to hashed results and Q1 audit passes |
| SF6 | Send closure memo to supervisors | No | pending | Email includes the four-row closure table and copies Mr Shaowei Yuan |

Existing headline H1--H4 results remain frozen. The final dissertation may be
closed after SF1--SF5; only SF4 requires additional CARLA execution.

The exact Git-only server commands, restart procedure and required transport
packages are frozen in
[`SUPERVISOR_FEEDBACK_EXECUTION_RUNBOOK_2026-08-14.md`](SUPERVISOR_FEEDBACK_EXECUTION_RUNBOOK_2026-08-14.md).

## Final supervisor update

The update should copy Mr Shaowei Yuan and contain, for each original comment:

- the exact change made;
- one compact result table or figure;
- the evidence path/commit and independent unit;
- what conclusion is supported;
- what remains a bounded limitation.

Authorship or acknowledgement should follow actual contribution and consent;
copying a discussion email alone is not treated as an authorship contribution.
