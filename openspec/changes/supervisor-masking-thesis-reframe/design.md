## Context

See `proposal.md` for motivation. The completed prior release already separates five canonical populations and shows a decisive common authority effect, but its SF4 authority-off arm is floor-saturated and seven behaviour channels are toggled together. V3 and R3 contain useful predictor and risk comparisons under common supervision, yet those final-trajectory contrasts alone do not identify causal masking. A read-only server audit found no logged same-state alternative policies; it also found that adaptive/fixed tightening differences can already contract sharply at the SMPC nominal-command layer before the supervisor makes larger command changes. The new design must therefore preserve existing evidence while distinguishing controller transmission, supervisor transmission and a null downstream result.

The manuscript and experiment code live in separate repositories. Historical server artifacts may contain fields omitted from the compact local release, but canonical results must remain immutable and any pulled evidence must be minimal, hashed and population-labelled.

## Goals / Non-Goals

**Goals:**

- Make rule-based supervisor effectiveness and limitations the paper's single organising question.
- Test H1 at the physical-outcome and intervention-mechanism layers.
- Decompose H2 into Capacity, Information and Architecture upstream evidence plus a separately identified transfer/attenuation test.
- Decompose H3 into fixed/adaptive risk upstream evidence plus a separately identified transfer/attenuation test.
- Explain MultiPath, multimodal SMPC, risk allocation and the complete supervisor bundle well enough for a knowledgeable reader to reproduce the tested stack.
- Produce a versioned, audited manuscript and evidence release without changing prior results.

**Non-Goals:**

- Claim formal safety, universal masking, selective attribution to an individual rule, or generalisation beyond the tested Town05 geometry.
- Present authority-off operation as a deployable controller.
- Re-tune MultiPath, risk policies or supervisor thresholds after observing new outcomes.
- Pool V3, R3, SF4, foundation, timing-shift or legacy samples.
- Claim a line-for-line reproduction of the reference multimodal SMPC implementation.

## Decisions

### 1. Use an identification ladder rather than a binary masking label

Each comparison moves through `upstream difference -> candidate-control difference -> supervisor request/action -> executed-control difference -> physical outcome`. Verdicts are assigned as retained, attenuated, compressed, not detected downstream, consistent with masking, or causally identified masking. The strongest term requires an aligned or factorial estimand specified in the evidence spec.

**Why:** Similar final trajectories can also arise from inactive constraints, controller insensitivity, solver fallback, target response or low power. A binary label would overstate the current design.

**Alternative considered:** Call every upstream improvement without physical gain masking. Rejected because this defines the mechanism by its outcome and cannot discriminate rivals.

### 2. Preserve H1--H3 as hypotheses, but let results refute or bound them

H1 predicts nominal physical yielding under complete authority. H2 predicts supervisor-induced attenuation of predictor policy differences, with Capacity, Information and Architecture as upstream subtests rather than separate headline hypotheses. H3 predicts supervisor-induced attenuation of fixed/adaptive risk-allocation differences. Hypothesis wording will state the observable falsification contrast; the title will use only the strongest verdict supported after analysis.

**Why:** This matches a hypothesis paper while preventing title-first outcome selection.

**Alternative considered:** State all three as established findings. Rejected because H2/H3 identification is still under audit.

### 3. Run an evidence-gap gate before new CARLA collection

Local compact evidence is audited first, followed by the smallest read-only server inspection needed for missing fields. If same-state candidate and executed commands already license H2/H3, only analysis is added. Otherwise the gate specifies the missing estimand and freezes one bounded protocol.

**Why:** Reusing complete experiments is efficient and reduces researcher degrees of freedom, but efficiency cannot substitute for causal identification.

**Alternative considered:** Immediately run more seeds of the existing closed loop. Rejected because more unmatched trajectories do not repair a missing identifying contrast.

### 4. Prefer authority-on shadow-policy evaluation if supplemental evidence is required

The preferred supplemental design executes the already frozen authority-on factual policy while evaluating alternative predictor and/or risk policies on the same observed state in shadow. For each factual state, the logger records alternative prediction/risk outputs, constraint activity and nominal SMPC commands, then evaluates the complete supervisor mapping both enabled and monitor-only for each shadow command. No shadow command reaches CARLA. The resulting paired 2-by-2 command-transmission contrast separates upstream-to-SMPC contraction from additional supervisor-induced attenuation.

**Why:** It directly creates aligned immediate-action comparisons without relying on the unsafe, floor-saturated authority-off trajectory distribution. It also leaves the factual vehicle behaviour and existing safety envelope unchanged.

**Alternative considered:** A full predictor-by-risk-by-authority rollout factorial. Rejected as the default because authority-off failure saturation makes the interaction hard to interpret and expands the experiment substantially; it remains a fallback only if shadow application cannot reproduce all seven authority channels.

### 5. Separate policy-value evidence from method-development evidence

Capacity, Information and Architecture remain a controlled offline ablation establishing what changes prediction. V3 establishes whether a selected predictor difference remains in-loop and whether it reaches physical outcomes. R3 establishes adaptive-risk position relative to the full fixed frontier. SF4 establishes complete authority effectiveness and activity. Supplemental aligned evidence, if needed, tests the mapping mechanism; it does not retroactively merge populations.

**Why:** This gives every experiment one inferential job and prevents duplicated rollout counts from being treated as independent evidence.

### 6. Rebuild the manuscript from Results outward

The rewrite order is Result Analysis, Methodology/Problem Formulation, Introduction/Literature Survey, Discussion/Conclusion, then Abstract and Title. Detailed derivations, full cells, solver reconciliation and code locators move to appendices. The main system figure shows the exact give-way geometry and measurement layers; all plots are produced by committed Python/Matplotlib scripts.

**Why:** Results-first drafting forces the headline to follow evidence. Plain-language text after each principal equation makes the technical system accessible without removing mathematical precision.

**Alternative considered:** Rename hypotheses and patch the current Introduction first. Rejected because it would preserve section-level contradictions and encourage overclaiming before the evidence audit.

### 7. Version the new release and keep the prior release immutable

New evidence and figures are written under a new release root. The dissertation uses a new figure subdirectory and build manifest. Prior generated JSON, tables, figures, PDF hash and Git commits remain provenance anchors.

**Why:** A reviewer or future author must be able to reproduce both the prior interpretation and the revised one.

## Risks / Trade-offs

- **Risk: Current evidence supports physical effectiveness but not causal masking.** -> Keep masking as the hypothesis; use `limited downstream sensitivity` or `consistent with masking` in findings unless the aligned gate passes.
- **Risk: Shadow commands omit supervisor channels that act before optimisation.** -> Trace all seven channels and fail the masking gate unless each alternative follows the same input/reference transformation path.
- **Risk: One factual trajectory does not establish counterfactual long-horizon physical behaviour.** -> Interpret shadow evidence as instantaneous policy-to-command attenuation, not trajectory-level causal effect.
- **Risk: The authority-on factual policy determines visited states.** -> State the conditional state-distribution boundary and, if needed, use frozen initialisation groups from both predictor/risk factual policies without pooling them.
- **Risk: H1 wording `ensures` is read as a guarantee.** -> Qualify it as `achieved nominal yielding in all tested authority-on rollouts` and keep formal-safety limitations next to the result.
- **Risk: Reframing around a negative limitation appears to weaken contribution.** -> Emphasise the reusable systems insight: final closed-loop similarity cannot validate or reject upstream improvements when a shared high-authority rule layer controls the mapping.
- **Risk: Expanded equations overwhelm a 15-page main text.** -> Put execution-critical equations and module interfaces in the main text; move derivations and parameter tables to appendices.

## Migration Plan

1. Freeze the previous experiment and dissertation commits as the baseline release.
2. Materialise the new hypothesis, terminology and identification ledgers.
3. Audit local and server evidence and sign the evidence-gap decision.
4. If required, implement and smoke-test the frozen shadow protocol before any formal run.
5. Generate the new evidence release and Python figures; do not overwrite previous assets.
6. Rewrite and compile the dissertation, then run numerical, citation, equation, visual and provenance audits.
7. Commit changes by scientific role, verify clean worktrees and push without history rewriting.

Rollback consists of pointing the dissertation build back to the previously committed `supervisor_bottleneck_v1` figures and PDF; no canonical result data are modified.

## Open Questions

- Which final finding-led title is licensed after H2/H3 identification; title selection is intentionally deferred until Results and Discussion are complete.
