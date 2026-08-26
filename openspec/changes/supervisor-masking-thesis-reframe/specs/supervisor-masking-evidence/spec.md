## Purpose

Defines the observable evidence, identification and provenance contract used to test physical yielding and upstream-policy masking claims without conflating incompatible experiments or promoting association to causation.

## ADDED Requirements

### Requirement: Three-hypothesis scientific contract
The evidence release SHALL define H1 as nominal physical yielding under complete rule-based supervisor authority, H2 as transfer of Capacity--Information--Architecture predictor improvements through the supervised control stack, and H3 as transfer of fixed/adaptive risk-allocation differences through that stack. Each hypothesis SHALL name its treatment, independent unit, upstream outcome, candidate-control outcome, executed outcome, falsification rule and population boundary.

#### Scenario: Hypothesis registry is generated
- **WHEN** the scientific contract is materialised
- **THEN** H1, H2 and H3 each have a machine-readable estimand, decision rule, evidence source, verdict vocabulary and prohibited overclaim

#### Scenario: Physical effectiveness is bounded
- **WHEN** H1 is reported from Town05 authority-on/off rollouts
- **THEN** the conclusion is limited to nominal completion, yielding and collision observations in the tested geometry and does not claim formal, general or real-road safety

### Requirement: Masking identification ladder
The analysis SHALL distinguish retained upstream difference, attenuated candidate difference, compressed executed difference, no detected physical transfer, and causally identified masking. Causal masking SHALL require either aligned same-state nominal-to-executed comparisons under supervisor intervention or a factorial upstream-policy-by-authority interaction with a non-saturated comparator; otherwise the release SHALL use a weaker verdict.

#### Scenario: Upstream difference lacks an identifying downstream contrast
- **WHEN** predictor or risk policies differ upstream but the available rollouts are not same-state aligned and the authority-off arm is floor-saturated
- **THEN** the result is labelled `not_transferred_or_not_identified`, `compressed`, or `consistent_with_masking` rather than `masked`

#### Scenario: Same-state action attenuation is available
- **WHEN** two upstream policies produce candidate controls for the same logged state and the supervisor maps them to executed controls
- **THEN** the release reports pre-supervisor and post-supervisor contrasts, an attenuation estimand, uncertainty and the exact alignment rule

#### Scenario: Factorial interaction is available
- **WHEN** upstream policy and supervisor authority are jointly varied over comparable non-saturated units
- **THEN** the release estimates the policy-by-authority interaction before assigning a causal masking verdict

### Requirement: H1 authority evidence
The analysis SHALL reconcile scenario completion, yield-rule compliance, collision events, minimum footprint separation, supervisor requests, actual command replacement and solver paths for complete supervisor authority on versus monitor-only authority off.

#### Scenario: Authority-on/off outcomes are reported
- **WHEN** the canonical SF4 evidence is analysed
- **THEN** counts, denominators, group-level uncertainty and authority-channel scope are reported together, including the seven-channel bundle and off-arm floor boundary

#### Scenario: Intervention mechanism is reported
- **WHEN** physical yielding is attributed to the supervisor bundle
- **THEN** request frequency, applied-command frequency, command-change magnitude, bypass and fallback accounting are reported so that effectiveness is not inferred solely from final trajectories

### Requirement: H2 predictor transfer decomposition
The analysis SHALL preserve Capacity, Information and Architecture as three offline subquestions while mapping each licensed predictor contrast to in-loop prediction, candidate control, supervisor intervention and executed physical outcomes whenever the data support those layers.

#### Scenario: Capacity evidence is mapped
- **WHEN** small, medium and large Transformer results are used
- **THEN** their held-out prediction contrast and its non-monotonic verdict are reported without implying that capacity was separately crossed with supervisor authority unless such data exist

#### Scenario: Information evidence is mapped
- **WHEN** 0.0, 0.4 and 1.0 second histories are used
- **THEN** the saturating offline history gain and the exact deployed history cell are reported, and physical transfer is claimed only for actually deployed matched policies

#### Scenario: Architecture evidence is mapped
- **WHEN** matched MLP and Transformer results are used
- **THEN** the direct full-history gap is separated from the history-gain interaction so that attention-specific benefit is not inferred from absolute performance alone

### Requirement: H3 risk-allocation transfer decomposition
The analysis SHALL retain fixed-risk frontier, adaptive-risk, target-behaviour and supervisor-authority populations as distinct blocks and SHALL compare risk allocation at constraint, nominal-control, intervention and executed-outcome layers where available.

#### Scenario: Adaptive risk is compared with the frontier
- **WHEN** adaptive risk is evaluated against fixed policies
- **THEN** every declared fixed comparator and context is shown rather than selecting only the fixed setting that adaptive risk beats

#### Scenario: Risk differences are physically similar
- **WHEN** adaptive and fixed policies produce similar completion time or minimum separation under common supervisor authority
- **THEN** the release tests whether risk/constraint or candidate-command differences still exist before describing the physical similarity as masking

#### Scenario: Historical populations are reused
- **WHEN** server-side timing, threshold or legacy risk results are relevant
- **THEN** their original protocol, unit and provenance are retained and they are juxtaposed rather than pooled with V3, R3 or SF4

### Requirement: Evidence-gap gate
The system SHALL issue a signed `existing_evidence_sufficient` or `material_gap_requires_collection` decision after the local and server audit. New CARLA collection SHALL be permitted only for a headline identification gap that cannot be resolved by provenance-safe reanalysis.

#### Scenario: Existing evidence is sufficient
- **WHEN** every headline verdict can be stated at its licensed causal strength from existing evidence
- **THEN** no new outcome-driven parameter search or CARLA experiment is launched

#### Scenario: Material gap requires collection
- **WHEN** a headline causal masking claim lacks the required aligned or factorial contrast
- **THEN** a pre-outcome protocol freezes treatments, units, nuisance settings, metrics, uncertainty, stopping rule and hashes before implementation or execution

### Requirement: Population and provenance integrity
The release SHALL preserve canonical V3, R3, SF4, foundation and any legacy populations without pooling, overwriting or relabelling their experimental units.

#### Scenario: Release audit runs
- **WHEN** the evidence package is finalised
- **THEN** every headline scalar resolves to a committed source locator and hash, all denominators reconcile, incompatible populations remain separate, and stale or modified canonical evidence fails closed

### Requirement: Probability-weighted controller evidence contract
The current SMPC SHALL minimize normalized joint-mode probability-weighted post-split branch cost, count a shared unbranched policy once, and use the same probability vector in adaptive risk allocation. Missing, non-finite, negative, zero-mass, wrong-size or partial joint-mode probabilities SHALL fail closed, and no unweighted runtime option SHALL be available.

#### Scenario: Weighted controller is qualified
- **WHEN** the controller implementation is admitted to smoke or formal CARLA execution
- **THEN** source tests, probability-contract tests and a numerical asymmetric-probability solver test pass, and per-solve telemetry records the objective identifier, normalized probabilities, probability sum and active weights

#### Scenario: Historical controller evidence is encountered
- **WHEN** a V3, R3, SF4 or legacy receipt identifies an unweighted controller implementation
- **THEN** it remains immutable audit provenance but is excluded from final H1--H3 closed-loop estimates and is never pooled with weighted-V2 evidence
