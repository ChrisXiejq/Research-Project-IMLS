## Why

The current B1-versus-Transformer result is not a persuasive architectural comparison because trainable capacity, access to explicit interaction history, and encoder architecture change together, while many runs terminate at the 20-epoch budget boundary. The dissertation needs a leakage-controlled factorial study that answers three separate questions: whether the Transformer was under-capacity, whether older interaction tokens add predictive information beyond the current interaction state, and whether attention uses the same historical information better than a matched MLP.

## What Changes

- Use a thesis-core nine-cell matrix: large B1; small, medium, and large 1.0-second Transformers; and capacity-matched large MLP/Transformer adapters at 0.0, 0.4, and 1.0 seconds. This preserves the primary Capacity, Information, and Architecture estimands without executing the redundant full factorial.
- Train all nine cells for seeds 11, 23, and 37 with one prospectively frozen common learning rate, identical optimisation controls, and a locked rollout-group split: groups 1--35 for training, 36--40 for checkpoint selection, and 41--45 for retrospective held-out evaluation.
- Use the trained history-horizon factorial, rather than test-time history corruption, as the main information ablation. Retain existing zero/shuffle perturbations only as appendix-level input-sensitivity checks.
- Define architecture evidence from capacity- and history-matched MLP-versus-Transformer pairs. Use the one-token Transformer as a negative control and a history-gain difference-in-differences to distinguish generic encoder effects from value specifically attributable to cross-time attention.
- Replace the underpowered common 20-epoch comparison with an 80-epoch maximum, patience-12, deterministic, crash-safe protocol. Remove the per-cell learning-rate sweep and data-fraction grid from the thesis-core execution scope.
- Precompute hash-bound outputs and penultimate features from the frozen B0 backbone once, train mathematically equivalent lightweight heads/adapters from that cache, reconstruct deployable full models, and require cached-versus-full numerical parity before accepting a run.
- Add validation-fitted calibration and frozen evaluation for every selected configuration, reporting rollout-macro NLL, ADE/FDE, calibration/coverage, response-stratified target-speed and timing errors, conflict-zone probability, parameter count, latency, and paired initialisation effects.
- Use the locked groups 41--45 only as a retrospective held-out set for the time-bounded thesis study and report that limitation explicitly; do not describe it as a new confirmatory set.
- Add a B1-versus-validation-selected best sequence model (`P*`) closed-loop protocol crossed with fixed-medium and adaptive risk, assertive and reactive target styles, and groups 81--90, yielding 80 paired rollouts and the primary model-by-risk difference-in-differences.
- Generate machine-readable manifests, completion gates, tables, figures, and thesis-facing evidence summaries without using test or closed-loop outcomes for model selection.

## Capabilities

### New Capabilities

- `capacity-controlled-prediction-study`: Defines the thesis-core model matrix, capacity and trained-history estimands, frozen optimisation, exact cached-backbone acceleration, calibration, retrospective held-out evaluation, and fairness audits.
- `predictor-risk-interaction-study`: Defines validation-only predictor selection, the paired closed-loop model-by-risk experiment, safety gates, and interaction-effect analysis.
- `dissertation-model-evidence`: Defines reproducible evidence products and claim boundaries for integrating the expanded model study into the dissertation.

### Modified Capabilities

None. This repository did not previously contain OpenSpec capability specifications.

## Impact

- Prediction model construction and training under `core/scripts/models/`, including adapter architecture, dataset filtering, training orchestration, evaluation, calibration, and statistical synthesis.
- CARLA experiment manifests and runners under `core/scripts/carla/` for the reduced B1-versus-`P*` risk matrix.
- Unit and contract tests under `core/scripts/models/tests/` and any CARLA runner tests already used by the repository.
- Generated experiment protocols and paper-evidence artefacts under `docs/paper/generated/`; large datasets, checkpoints, and server run outputs remain external/generated artefacts rather than source-controlled binaries.
- Dissertation-facing integration inputs in the experiment repository and, after evidence exists, corresponding prose/tables in the separate dissertation repository.
