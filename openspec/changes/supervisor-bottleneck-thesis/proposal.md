## Why

The completed prediction, closed-loop and supervisor-authority experiments show a coherent but not yet submission-ready systems result: task-specific prediction gains and risk-policy differences do not automatically survive the coupled predictor--risk--SMPC--supervisor stack. The thesis must now distinguish the supervisor's large common safety/completion effect from the stronger, currently unsupported claim that it selectively masks one upstream method, and must close only the evidence gaps needed for that bounded argument.

## What Changes

- Replace the abandoned implicit-safety-filter search as the thesis main line with a system-level study of prediction quality, closed-loop translation, risk allocation and rule-based supervisor authority.
- Freeze one central argument and four falsifiable hypotheses, each linked to canonical existing evidence, an explicit causal boundary and a prespecified decision rule.
- Reuse the completed Capacity--Information--Architecture, R3 and SF4 experiments wherever they answer the new hypotheses; do not merge incompatible experimental populations.
- Add reproducible post-SF4 analyses for intervention authority, nominal-to-executed behavioural attenuation, phase-specific behaviour and solver/fallback pathways when the raw telemetry supports those estimands.
- Permit new CARLA experiments only when the claim--evidence audit identifies a material unanswered hypothesis that cannot be resolved from existing raw data; freeze all treatments and analysis rules before execution.
- Generate publication-quality tables and multi-panel figures exclusively from canonical CSV/JSON evidence with Python, including source provenance and claim-boundary checks.
- Reconcile the experiment and dissertation repositories into reviewable, reproducible commits without deleting or overwriting unclassified existing work.

## Capabilities

### New Capabilities

- `supervisor-bottleneck-evidence`: Defines the thesis argument, four-hypothesis claim--evidence contract, causal boundaries, reuse rules and targeted experiment decision gates.
- `post-sf4-paper-release`: Defines reproducible post-SF4 analysis, paper-asset generation, manuscript integration and final repository-release requirements.

### Modified Capabilities

- None. The completed capacity-controlled Transformer study remains immutable historical evidence and is consumed rather than redefined.

## Impact

- Evidence and analysis code under `core/scripts/models/`, with possible narrowly scoped CARLA collection code under `core/scripts/carla/` only after an evidence-gap gate.
- Generated evidence under `docs/paper/generated/`, plus the reader-facing dissertation in the adjacent `Jiaqi-Xie-Dissertation` repository.
- Existing Capacity/History V3, R3 and SF4 completion markers, hashes and raw evidence remain unchanged.
- The uncommitted implicit-SMPC branch of work is retained and classified as exploratory code, appendix/future-work material or an independently reviewable non-headline commit; it is not silently discarded.
