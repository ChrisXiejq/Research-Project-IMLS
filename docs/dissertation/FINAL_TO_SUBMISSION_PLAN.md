# Final route from frozen evidence to dissertation submission

**Status:** active and canonical  
**Evidence cut:** R3/A2/M1, 2026-08-08  
**Experiment decision:** large-scale CARLA collection is closed; R4 is `not_run`  
**Current gate:** Q1 scientific/rubric/PDF gate passed; verified human release
metadata pending before Q1 can close

This is the sole active route from the completed experiments to the final
dissertation. [`DISTINCTION_EXECUTION_PLAN.md`](DISTINCTION_EXECUTION_PLAN.md)
remains the historical record of how the evidence was produced; it must not be
used to reopen experiments or redefine hypotheses after seeing R3 outcomes.

## 1. Frozen destination

### Working title

> **Task-Adapted Motion Prediction under Predictor--Risk Coupling: A
> Controlled CARLA Give-Way Study**

### Single organising claim

> In the frozen Town05 give-way setting, simple task adaptation provides a
> large and consistent in-distribution prediction improvement, whereas the
> tested Transformer residual adapters provide no consistent additional
> benefit. When deployed as a frozen predictor stack, that improvement does
> not translate uniformly into closed-loop safety--efficiency gains, and
> adaptive risk is conditionally useful rather than universally dominant.

The machine-learning result is the starting point of the argument. The control
stack explains the boundary of that result; it is not a replacement thesis
about the supervisor.

### Four hypotheses and final evidence status

| ID | Frozen hypothesis | Final status | Primary evidence |
| --- | --- | --- | --- |
| H1 | B1 improves held-out in-distribution prediction over B0 and simple physical baselines | supported with boundary | frozen test, E1, R3 manipulation checks |
| H2 | Transformer sequence adapters provide a consistent gain beyond their corresponding MLP controls/simple adaptation | not supported | frozen model comparison and E3 fairness audit |
| H3 | B1's offline gain transfers consistently to closed-loop completion and separation | universal claim not supported | corrected R3: 2/8 directional cells |
| H4 | adaptive risk dominates all three fixed-risk comparators | universal dominance not supported | corrected R3: 3/12 comparisons |

“Not supported” is preferred to “proved false”. With five paired init groups,
the design cannot establish conventional significance, equivalence or a
population-wide null effect.

## 2. Frozen evidence hierarchy

Use evidence in this order:

1. `docs/paper/generated/distinction_v1/10_four_hypothesis_evidence/` — the
   only claim-to-value entry point for H1--H4;
2. `docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis/`
   — corrected R3 tables, figures and interpretation;
3. other `distinction_v1/` stages — provenance, baselines, ablations,
   fairness, audits and prospective contracts;
4. `paper_assets_v1/` and Day10--13 outputs — legacy or secondary diagnostics
   only; never pool them with corrected R3 estimates.

No value is to be copied from memory or edited in a generated CSV/JSON. If a
number changes, its generating script and M1 value audit must be rerun.

## 3. Final work packages and acceptance gates

### W0 — Evidence and document migration

**Purpose:** remove competing narratives before prose is expanded.

Deliverables:

- this route is the only current plan;
- `docs/paper/` describes R3/M1 rather than the legacy Day10--12 synthesis;
- LaTeX uses the corrected R3 design and verdicts;
- obsolete execution guides are removed while raw/generated evidence remains;
- every retained historical document is visibly labelled historical.

**Gate W0:** no active document calls `paper_assets_v1` the sole evidence
source; no active document calls the old 160-rollout timing synthesis the
primary closed-loop experiment; all local documentation links resolve.

### W1.1 — Methods and experimental design

Write these sections first because the protocol is frozen:

1. Town05 give-way scenario and system boundary;
2. 200-rollout prediction dataset and rollout-disjoint split;
3. B0/B1/B2-M/B2-D/T1/T2 configurations and trainable-scope caveat;
4. validation-only selection, frozen test and calibration;
5. corrected R3 factorial:
   $2$ predictors $\times$ $4$ policies $\times$ $2$ target styles $\times$
   $5$ new init groups $=80$ rollouts;
6. event-clock completion, actual-bounding-box separation, binary guards and
   telemetry outcomes;
7. paired-init analysis, bootstrap intervals, exact sign-flip tests, Holm
   families and the minimum two-sided exact $p=0.0625$;
8. declared estimands: B1 versus B0 is a frozen predictor-stack contrast, not
   a weight-only causal effect.

**Gate W1.1:** another researcher can identify every treatment, control,
independent unit, exclusion/censoring rule, primary outcome and analysis family
without reading experiment-day notes.

### W1.2 — Results and figures

Write in the following order:

1. data integrity and physical-baseline context;
2. H1 frozen offline effect: NLL reduction 0.314 nats/step, ADE reduction
   1.193 m and FDE reduction 2.555 m versus B0;
3. H2: T1 versus B2-M and T2 versus B2-D point in different directions, plus
   the non-parameter-matched limitation;
4. R3 manipulation validity: B1 wins all five init groups in 40/40
   metric--policy--style checks;
5. H3 corrected translation: only 2/8 cells are jointly faster with no-worse
   separation;
6. H4 corrected dominance: adaptive dominates in 3/12 comparisons;
7. reliability: no observed binary scientific failures, so those endpoints
   validate nominal feasibility but do not discriminate treatments;
8. legacy active-tail/timing/collision analyses as clearly labelled mechanism
   or sensitivity evidence.

**Gate W1.2:** all headline numbers have M1 evidence IDs, table/figure captions
state the unit and protocol, and no exact/Holm result is described as
significant.

### W1.3 — Related work

Build a critical synthesis around four questions rather than a list of papers:

- how risk-aware planning evaluates fixed/adaptive uncertainty budgets;
- how motion-prediction work evaluates multimodal accuracy and calibration;
- when interaction/Transformer capacity helps under limited data;
- why open-loop prediction metrics may not determine closed-loop utility.

Use approximately 25--35 checked primary or official sources, with each source
read far enough to support the exact sentence citing it. Distinguish this
controlled empirical contribution from claims of a new general-purpose
architecture or a newly discovered open/closed-loop mismatch.

**Gate W1.3:** no placeholder citation, every factual method claim is cited,
and the gap leads directly to H1--H4.

### W1.4 — Introduction, discussion, conclusion and abstract

Write these only after Methods and Results stabilise.

- Introduction: motivation → gap → one thesis → four RQs/Hs → four focused
  contributions.
- Discussion: why simple adaptation wins here; why translation is conditional;
  what adaptive risk still contributes; limitations and future work.
- Conclusion: answer H1--H4 in order without adding evidence.
- Abstract: problem, design, three decisive numerical findings, conclusion and
  scope boundary.

**Gate W1.4:** every contribution has a Results subsection; every limitation
prevents a specific overclaim; no conclusion exceeds Town05, the tested
models, the two-second horizon or the frozen stack.

### W1.5 — Reproducibility and appendices

Include configuration/provenance tables, split checks, model fairness,
secondary diagnostics, full R3 contrast tables, evidence-ID instructions and
the no-more-CARLA decision. Keep supplementary detail after the references as
required by the TMLR layout.

**Gate W1.5:** a clean checkout can rebuild the R3 synthesis, M1 evidence audit
and manuscript PDF without manual result editing.

### Q1 — Final scientific, rubric and PDF audit

All of the following must pass:

- zero `TODO`, placeholder identity field or unresolved cross-reference;
- all M1 locators and values re-resolve;
- generated table/figure hashes match completion markers;
- tests pass and the LaTeX build is clean enough to inspect the final PDF;
- title, abstract, hypotheses, results and conclusion use the same estimands;
- the marking-rubric map has explicit evidence for research quality, technical
  depth, critical evaluation, presentation and reproducibility;
- figures are legible at final page size and appendices follow references;
- AI-use, acknowledgements and submission identity follow current UCL rules.

### V1 — Viva and submission package

Prepare:

- final PDF and source archive with checksums;
- one-page claim/evidence/limitation summary;
- a 5--7 minute project explanation;
- answers to the hardest questions: small $n$, calibration confounding,
  Transformer fairness, corrected versus legacy results, negative H3/H4 and
  generalisation;
- final repository tag/commit and an immutable evidence inventory.

**Gate V1:** every headline statement can be defended by naming its control,
unit, number, uncertainty and boundary without opening the code.

## 4. Actions that are now out of scope

Do not start R4, a larger Transformer, additional maps, extra init groups or
new outcome definitions for this dissertation. They would be post-outcome
scope expansion and are not required by the frozen stop rule. They belong in
Future Work unless Q1 discovers an actual data-integrity or implementation
error that invalidates an existing headline result.

Do not delete raw results, generated evidence, completion markers, manifests or
hash records. Documentation can be consolidated; evidence must remain
auditable.

## 5. Immediate next action

W0 and W1 are accepted. Q1's scientific, rubric, clean-checkout and PDF gates
passed on 2026-08-09. The upload-ready release gate remains open only for
verified candidate/programme metadata, the ELEC0054 GenAI category and the
module word/page rule. This is not permission to reopen CARLA, select new
outcomes or alter a verdict because its direction is inconvenient.
