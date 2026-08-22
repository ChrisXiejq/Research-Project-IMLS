## Purpose

Provide a preregistered closed-loop experiment that measures whether differences between B1 and the validation-selected best sequence model are amplified, suppressed, or reversed by the risk policy.

## ADDED Requirements

### Requirement: Validation-only deployment selection
The deployed large-B1 and best sequence-model checkpoints, calibration parameters, model hashes, and runtime contracts SHALL be selected using groups 1--40 only. The sequence candidate `P*` SHALL be selected from the six thesis-core MLP and Transformer cells by median groups-36--40 rollout-macro NLL, with deterministic ties resolved by lower trainable parameter count, lower warmed latency, and then lexical model identifier. Groups 41--45 and closed-loop outcomes MUST NOT influence checkpoint, capacity, history horizon, calibration, or architecture selection; the learning rate is already frozen globally at `1e-4`.

#### Scenario: Deployment bundle is frozen
- **WHEN** the offline validation study is complete and converged
- **THEN** a signed or hashed deployment manifest identifies exactly one B1 stack and one `P*` sequence stack, including whether `P*` is MLP or Transformer, before groups 41--45 or formal closed-loop outcomes are inspected

### Requirement: Primary model-by-risk factorial
The formal closed-loop study SHALL cross B1 and `P*` with fixed-medium and adaptive risk policies, assertive and reactive target styles, and ten paired initialisation groups 81--90, producing 80 planned rollouts. Fixed-aggressive and fixed-conservative branches are outside the time-bounded thesis-core scope. Initialisation groups used in earlier formal matrices or the retrospective held-out set SHALL not be reused.

#### Scenario: Matrix completeness is audited
- **WHEN** formal execution is declared complete
- **THEN** every predictor-by-risk-by-style-by-initialisation cell exists exactly once or the study is explicitly incomplete and no confirmatory interaction claim is emitted

### Requirement: Runtime and safety equivalence
Except for the frozen predictor stack and declared risk policy, formal cells SHALL share simulator version, map, route, target behaviour parameters, solver settings, joint-mode mapping, supervisor authority, seeds, termination definitions, and logging contract. Both predictors MUST pass numerical deployment, latency, covariance-validity, and solver-compatibility preflight gates before formal execution.

#### Scenario: A preflight gate fails
- **WHEN** either predictor produces incompatible shapes, non-finite distributions, invalid covariance, unacceptable runtime, or a solver-interface mismatch
- **THEN** formal collection is blocked and the failure is recorded without substituting another model based on test outcomes

### Requirement: Model-by-risk estimands
The primary closed-loop estimand SHALL be the difference-in-differences between `P*` and B1 under adaptive versus fixed-medium risk, separately for completion time and minimum footprint separation. Secondary estimands SHALL cover solver failure, fallback, supervisor activity, intervention timing, prediction calibration in loop, and binary adverse outcomes.

#### Scenario: Risk moderation is reported
- **WHEN** formal analysis completes
- **THEN** it reports paired initialisation effects and cluster uncertainty for each within-policy model contrast and for the adaptive-minus-fixed model difference-in-differences

### Requirement: Claim-safe interpretation
The analysis SHALL distinguish predictive accuracy, constraint activation, candidate control, supervisor modification, and executed trajectory. A model SHALL not be called safer solely because it has lower NLL/ADE/FDE, and a risk policy SHALL not be called superior solely because it is more conservative.

#### Scenario: Offline and closed-loop rankings disagree
- **WHEN** the validation-selected `P*` improves prediction metrics but not completion/separation outcomes
- **THEN** the report identifies where translation ceased, using solver, fallback, and supervisor diagnostics, rather than treating the result as contradictory or suppressing it

### Requirement: Crash-safe formal execution and immutable analysis
Formal rollout execution SHALL be resumable without duplicating completed cells and SHALL write per-cell provenance before the aggregate completion gate. Analysis SHALL consume only the frozen manifest and completed logs and SHALL never mutate model selection or formal runtime configuration.

#### Scenario: Formal execution is interrupted
- **WHEN** the simulator or host stops during the matrix
- **THEN** the runner resumes only missing or invalid cells after verifying manifest and source hashes
