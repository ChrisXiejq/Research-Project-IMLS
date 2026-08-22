## Purpose

Produce traceable, machine-readable, and thesis-ready evidence that supports only the claims licensed by the capacity-controlled prediction and predictor-by-risk experiments.

## ADDED Requirements

### Requirement: Evidence provenance chain
Every thesis-facing table, figure, and scalar SHALL be reproducible from a frozen protocol, source revision, dataset manifest, model/calibration manifest, and analysis output hash. Generated artefacts SHALL distinguish source-controlled protocol files from large external training and CARLA outputs.

#### Scenario: A thesis scalar is generated
- **WHEN** a numeric result is exported for dissertation use
- **THEN** the evidence index records its source file, field or contrast identifier, units, estimator, independent-unit count, and provenance hashes

### Requirement: Capacity-study evidence products
The evidence generator SHALL produce the 1.0-second Transformer capacity-performance curve, large-model trained history-horizon curves, matched large MLP-versus-Transformer tables at 0.0, 0.4, and 1.0 seconds, history-gain difference-in-differences, a large-B1 adaptation-allocation table, convergence and seed audits, response-stratified mechanism summaries, calibration summaries, and parameter/latency Pareto results. Every held-out result SHALL be labelled retrospective rather than new confirmatory evidence.

#### Scenario: Transformer superiority is stated
- **WHEN** a generated claim says that Transformer architecture is superior
- **THEN** the claim is enabled only by a capacity-, foundation-, history-, scope-, and optimisation-matched Transformer-versus-MLP contrast on the locked retrospective held-out data and is bounded to that evidence status

#### Scenario: Temporal attention superiority is stated
- **WHEN** a generated claim says that attention uses interaction history better than an MLP
- **THEN** the claim additionally requires a favourable Transformer-minus-MLP history-gain interaction and reports the one-token negative control

#### Scenario: Explicit history value is stated
- **WHEN** a generated claim says that explicit interaction history adds information
- **THEN** it cites independently trained current-token, 0.4-second, and 1.0-second comparisons and does not use frozen zero/shuffle perturbations as the primary evidence

#### Scenario: B1 superiority is stated
- **WHEN** a generated claim says B1 is superior to the Transformer configuration
- **THEN** it is worded as a bounded adaptation-allocation or complete-configuration finding unless the underlying comparison satisfies architecture-isolation requirements

### Requirement: Outcome-independent result synthesis
The generator SHALL implement predeclared interpretation branches for capacity, information, architecture, and B1 adaptation allocation, including positive, null, mixed, and adverse results, so prose does not change its evidentiary standard based on which model wins.

#### Scenario: A result branch is selected
- **WHEN** confirmatory metrics become available
- **THEN** the generator selects the matching preregistered interpretation branch and retains unsupported, conditional, and null results in the evidence ledger

#### Scenario: Three axes disagree
- **WHEN** capacity, information, and architecture estimands lead to different conclusions
- **THEN** the generator reports each conclusion separately and does not collapse them into a single Transformer-versus-B1 ranking

### Requirement: Predictor-risk evidence products
The evidence generator SHALL produce the full closed-loop cell table, within-risk model contrasts, model-by-risk difference-in-differences, risk-sensitive prediction diagnostics, solver/fallback/supervisor pathway summaries, and a claim-boundary ledger.

#### Scenario: Model and risk are linked in the dissertation
- **WHEN** the integration summary describes a model-by-risk relationship
- **THEN** it cites a registered interaction estimand or explicitly labels the statement as a mechanistic interpretation rather than an estimated causal interaction

### Requirement: Thesis integration gate
Authoritative dissertation prose SHALL not be updated with new numerical conclusions until the 27-run thesis-core prediction gate and 80-rollout closed-loop gate pass. Before completion, the system MAY generate methods text, planned tables, empty figure specifications, and clearly labelled placeholders only.

#### Scenario: Experiments are not yet complete
- **WHEN** one or more required completion gates are absent or failing
- **THEN** the integration tool refuses to emit final result claims and instead reports the missing evidence
