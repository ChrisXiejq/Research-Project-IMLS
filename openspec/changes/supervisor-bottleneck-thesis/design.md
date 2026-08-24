## Context

See `proposal.md` for motivation. The project already contains five valid but statistically distinct evidence blocks: B0/B1 foundation adaptation, Capacity--Information--Architecture V3, R3 predictor--risk evaluation, V3 selected-model deployment and SF4 complete supervisor-authority on/off evaluation. The main engineering constraint is therefore evidence reconciliation, not wholesale recollection. Both the experiment and dissertation repositories contain substantial uncommitted work that must be classified and preserved.

The strongest existing controller result is asymmetric: full rule-based supervisor authority is necessary for nominal completion and yielding in the tested sample, but the authority-off arm collapses to a failure floor. This identifies a large common authority effect but weakens interaction estimates and does not by itself prove selective masking of predictor or adaptive-risk advantages.

## Goals / Non-Goals

**Goals:**

- Produce one claim-safe systems argument linking MultiPath prediction, controlled model ablations, risk-aware SMPC, rule-based supervision and executed CARLA behaviour.
- Close H1--H4 primarily from canonical completed evidence, adding only analyses or experiments that change the defensibility of a headline claim.
- Quantify supervisor authority and, where the telemetry permits, the difference between nominal, supervisor-candidate and executed commands.
- Deliver reproducible paper assets, a complete nature-writing-based dissertation and clean reviewable repository states.

**Non-Goals:**

- Claim that rule-based supervision is generally inferior, that the supervisor is the sole source of trajectory similarity, or that adaptive and fixed risk are equivalent.
- Resume open-ended implicit-filter or SMPC parameter search as the thesis contribution.
- Pool experimental populations, reopen frozen model selection, tune after seeing held-out/CARLA outcomes, or replace negative results with outcome-selected experiments.
- Prove formal recursive feasibility, population-level collision freedom, cross-map generalisation or real-road safety.

## Decisions

### 1. Use a cross-layer translation argument rather than a negative supervisor story

The manuscript will argue that local module quality is insufficient to predict system utility in a tightly coupled stack. B0/B1 establishes task-foundation mismatch; V3 separates capacity, information and architecture; R3 and V3 deployment measure physical transfer; SF4 identifies supervisor authority. This retains positive contributions while making bounded negative findings scientifically useful.

Alternative considered: centre the paper on “the rule-based supervisor is bad”. Rejected because the supervisor produced 40/40 successful SF4 authority-on rollouts and the current DID does not support selective masking.

### 2. Freeze four hypotheses around the controlled axes

- **H1 Capacity:** more trainable capacity is the explanation for the temporal model gap. Primary evidence is the fixed-history capacity curve. Current evidence does not support a coherent capacity-limitation explanation.
- **H2 Information:** explicit recent interaction history adds predictive information beyond the current interaction token. Primary evidence is the matched 0.0/0.4/1.0 s horizon comparison. Current evidence supports a small, rapidly saturating gain.
- **H3 Architecture:** attention extracts more value from the same history than a matched MLP. Primary evidence requires both direct matched-family contrasts and a positive history-gain interaction. Current evidence supports a small direct Transformer gap but not attention-specific history extraction.
- **H4 Closed-loop system utility:** validation-selected prediction and adaptive risk retain useful physical effects, while supervisor authority mediates executed behaviour. V3/R3 test transfer and the risk frontier; SF4 tests complete authority. Current evidence supports conditional transfer, context-dependent adaptive risk and a large common supervisor effect, not universal dominance or selective masking.

B0/B1 task adaptation remains a foundation result before H1 rather than consuming one of the three controlled offline axes.

### 3. Apply an evidence-gap gate before simulator work

The first implementation will build a machine-readable matrix with one row per claim and columns for estimand, population, independent unit, canonical source, current verdict, boundary, raw-telemetry availability and whether new data are necessary. New CARLA work is blocked unless this audit marks a headline claim `material_gap_requires_collection`.

Alternative considered: immediately run a predictor x risk x supervisor matrix. Rejected because existing V3 and SF4 already contain 160 formal rollouts across adjacent factors, and authority-off floor saturation makes a large replacement matrix scientifically inefficient.

### 4. Prefer shadow-action analysis to unsafe authority-off expansion

The analysis will first inspect SF4 and V3 raw logs for per-step nominal solver commands, supervisor candidates, actual commands, authority-channel requests, rule bypass, phase, geometry, risk state and solver status. If complete, it will estimate:

\[
I_{\mathrm{freq}}=T^{-1}\sum_t \mathbf{1}\{\|u_t^{\mathrm{exec}}-u_t^{\mathrm{nom}}\|>\epsilon\},
\]

\[
I_{\mathrm{mag}}=T^{-1}\sum_t \|u_t^{\mathrm{exec}}-u_t^{\mathrm{nom}}\|_2,
\]

and, for aligned upstream alternatives,

\[
C=1-\frac{D_{\mathrm{post}}}{D_{\mathrm{pre}}}, \qquad
D=\mathbb{E}\|u^{(a)}-u^{(b)}\|_2.
\]

Positive compression may be reported only with an identified pre/post comparison and uncertainty across initialization groups. If existing logs cannot construct the comparison, the preferred supplemental experiment is a supervisor-on factual rollout with isolated shadow evaluation of alternative predictor/risk nominal actions on the same factual states. This avoids applying unsafe supervisor-off commands and avoids trajectory-divergence confounding. A physical on/off expansion is a last resort and must explicitly address floor saturation.

### 5. Treat threshold sensitivity as a limitation test, not parameter optimisation

Existing timing-shift evidence and rule activation geometry will be audited for discontinuities in intervention, delay, margin and release. If a gap remains, a small frozen boundary-stress design will vary initial arrival timing or speed around declared rule thresholds while keeping supervisor parameters fixed. The experiment maps a response surface; it does not search thresholds for a favourable outcome.

### 6. Generate an evidence-first five-figure package

All graphics will be generated with Python from canonical tables:

1. task-specific cross-layer pipeline and measurement points;
2. multi-panel Capacity--Information--Architecture evidence landscape;
3. offline-to-closed-loop predictor and risk transfer across styles/conditions;
4. SF4 authority effects, intervention/fallback pathways and safety--completion outcomes;
5. phase- or threshold-sensitivity / nominal-to-executed attenuation figure if licensed by the mechanism audit.

Figures will use restrained colour, accessible line/marker encodings, explicit units, paired observations or intervals, and vector output. The architecture diagram may use Python plotting primitives; no generative-image asset will be used for result evidence.

### 7. Separate evidence generation, manuscript writing and repository release

Generated evidence will remain immutable output of versioned scripts. The reader-facing manuscript stays in `Jiaqi-Xie-Dissertation`; compatibility sources in the experiment repository are not the submission source. Manuscript writing will follow nature-writing in evidence-first order: Results, Introduction/Conclusion, title, Discussion, Methods, then Abstract. The requested seven top-level headings, approximately 15-page working scale, 25--30 or more verified references and appendices are release requirements.

### 8. Preserve dirty work through classification and atomic commits

The experiment repository will be partitioned conceptually into completed V3 evidence, exploratory implicit-filter code, new post-SF4 analysis and generated outputs. The dissertation repository will separate source text/bibliography, generated figures and build outputs. No destructive reset or silent deletion will be used. Reproducible caches will be ignored only after their generating path is verified; meaningful exploratory code will be committed separately or preserved in a documented archive.

## Risks / Trade-offs

- **[Selective masking remains unidentifiable]** -> Report a systems bottleneck/conditional translation result, not a supervisor-only cause; run the shadow-action study only if it supplies the missing estimand.
- **[Authority-off floor saturation obscures interactions]** -> Emphasise the direct common authority effect and use same-state shadow commands rather than a larger failing on/off matrix.
- **[Phase clocks are incomplete]** -> Build explicit availability gates and leave unsupported phase endpoints as limitations.
- **[V3 held-out groups are retrospective]** -> Preserve that label and avoid confirmatory language or pooling with other groups.
- **[Many uncommitted files contain mixed provenance]** -> Inventory hashes and diffs before staging, isolate commits by scientific role, and never discard unclassified work.
- **[The thesis becomes too broad]** -> Make prediction-to-execution translation the only main line; place implementation detail, complete formulas and secondary diagnostics in appendices.
- **[Negative hypotheses appear weak]** -> Lead with discriminating experiments and bounded design insight: capacity is not the explanation, history gain saturates, attention-specific gain is unsupported, and safety-layer authority dominates nominal success.

## Migration Plan

1. Snapshot both repositories' branch, HEAD, remotes, staged/unstaged/untracked inventory and source hashes.
2. Build and validate the claim--evidence--boundary matrix from existing completion markers.
3. Audit local and remote raw SF4/V3 telemetry; implement post-SF4 mechanism analysis without modifying frozen inputs.
4. Decide the experiment gate. If closed, proceed directly to assets; if open, freeze and run only the approved shadow-action or boundary-stress study.
5. Regenerate final tables, figures, evidence manifests and paper-integration snippets.
6. Rewrite and compile the reader-facing dissertation, then run citation, numerical and page-level visual audits.
7. Classify and commit experiment-repository changes, then dissertation-repository changes; push only after tests and release manifests pass.

Rollback is non-destructive: remove the new generated namespace and revert only commits created for this change. Historical V3, R3, SF4, exploratory implicit-filter files and prior manuscript work remain recoverable.
