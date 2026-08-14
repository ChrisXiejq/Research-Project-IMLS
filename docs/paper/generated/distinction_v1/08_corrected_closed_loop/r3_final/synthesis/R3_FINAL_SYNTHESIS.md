# A2 — R3 corrected evidence synthesis

## Completion decision

R3 is complete and integrity-valid: **80/80** prespecified rollouts and all formal tables passed their frozen gates. `R3_STUDY_STOP_GATE.json` records `stop_formal_large_scale_collection`, so its observed H3/H4 direction cannot justify an outcome-selected R3 extension or R4. A later, separately preregistered SF4 application-authority on/off audit of the corrected `reduced_intervention` supervisor responds to external supervisor feedback; it is not the historical `full` supervisor configuration and does not alter the R3 estimands, reopen H1--H4 or weaken this stop decision.

## Central thesis claim

**Task adaptation produces large, consistent in-distribution prediction gains, but their closed-loop value is conditional on the coupling among predictor stack, risk policy, target interaction style and shared supervisor. Neither a more complex temporal model nor adaptive risk is universally superior.**

This is the paper's single organising claim. It keeps machine learning central (the prediction manipulation is strong and consistent) while explaining why better prediction alone does not guarantee better planning outcomes.

## Four hypothesis verdicts

- **H1 — supported:** B1 improves prediction over B0. In R3, all 40/40 in-loop metric-policy-style checks favour B1 across every paired init group. These checks validate the deployed manipulation but are not an independent offline benchmark.
- **H2 — not supported:** the tested Transformer/sequence variants do not beat the simpler B1 adaptation under matched data, training and selection controls. Complexity is therefore not the contribution.
- **H3 — universal claim rejected:** only **2/8** policy/style cells jointly show faster completion and no-worse footprint separation for B1 versus B0. Prediction improvement is real; closed-loop translation is conditional.
- **H4 — universal dominance rejected:** adaptive risk dominates its fixed comparator in only **3/12** prespecified predictor/style/comparator cells. Adaptive risk is a context-dependent policy, not a universally better one.

## Statistical interpretation

Each primary contrast uses five paired init groups (101–105). The smallest possible two-sided exact sign-flip p-value is 0.0625, and all Holm-adjusted results are non-confirmatory. The paper must therefore report effect sizes, paired directions and bootstrap intervals, and must not claim conventional statistical significance or equivalence.

No native collision, footprint collision, fixed-geometry yield failure or completion failure occurred. These are nominal outcome-reliability observations, not evidence that every MPC step was feasible: the legacy debug telemetry contains logger-unaccepted rows that require execution-level reclassification. The binary endpoints cannot distinguish the tested arms, so continuous footprint separation remains the primary safety-margin evidence.

## What the thesis may and may not claim

The thesis may claim robust in-distribution prediction improvement, failure of universal closed-loop transfer, and predictor–risk–interaction coupling in the tested Town05 give-way setting. It must not claim cross-map or real-world generalisation, a causal weight-only B1 effect, universal adaptive-risk superiority, Transformer superiority, statistical significance, or safety equivalence.

## Next writing action

Use the two generated SVG figures and four CSV tables in Results. Structure the chapter as manipulation validity → H3 translation test → H4 dominance test → mechanism/boundary interpretation. Preserve older timing experiments as secondary sensitivity evidence, not as the primary corrected R3 result.
