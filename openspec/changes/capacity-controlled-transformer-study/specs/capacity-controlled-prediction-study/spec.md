## Purpose

Provide a leakage-controlled and reproducible comparison that separately identifies trainable-capacity effects, the incremental value of explicit interaction history, and attention-versus-MLP architecture effects before relating the selected predictor to closed-loop risk behaviour.

## ADDED Requirements

### Requirement: Frozen model-family contract
The study SHALL compare a spatial head-adaptation family, a non-attentional MLP encoder family, and a Transformer encoder family while preserving a common pretrained MultiPath backbone, anchor set, label horizon, loss, full-distribution output scope, split policy, and evaluation implementation. Every MLP-versus-Transformer architecture contrast SHALL hold explicit history horizon, sample eligibility, trainable-capacity tier, optimisation-selection protocol, and evaluation data fixed. B1 comparisons SHALL be labelled as adaptation-allocation or complete-configuration contrasts rather than pure architecture effects.

#### Scenario: Architecture claim is requested
- **WHEN** a report attributes a performance difference specifically to attention or Transformer architecture
- **THEN** the supporting contrast uses an MLP and Transformer with the same pretrained foundation, history horizon, eligible samples, output scope, capacity tier, optimisation-selection protocol, and evaluation set

#### Scenario: B1 is compared with a history encoder
- **WHEN** B1 is compared with an MLP or Transformer adapter
- **THEN** the result is labelled as an adaptation-allocation or complete-configuration contrast and does not isolate attention

### Requirement: Three declared capacity tiers
The study SHALL train 1.0-second Transformer variants at small, medium, and large trainable-capacity tiers targeting approximately 0.17 million, 0.50 million, and 1.034208 million parameters. The thesis-core architecture contrasts SHALL use large MLP and Transformer adapters whose trainable counts differ by no more than five percent of the large target, and both large adapters MUST differ from full B1 by no more than five percent. Exact counts, architecture settings, ratios, and all weights updated by training SHALL be recorded before performance is inspected. Small/medium B1 and small/medium MLP factorials are implementation controls, not required thesis-core executions.

#### Scenario: Capacity manifest is frozen
- **WHEN** model configurations are prepared for training
- **THEN** a machine-readable manifest records target and actual parameter counts and rejects any required matched comparison outside tolerance

#### Scenario: Large adaptation allocations are compared
- **WHEN** B1 is compared with either history encoder
- **THEN** full-head B1 and both large adapters satisfy the declared capacity tolerance and the contrast is labelled as adaptation allocation

#### Scenario: Transformer under-capacity is assessed
- **WHEN** the capacity hypothesis is evaluated
- **THEN** Transformer performance is compared across small, medium, and large tiers at fixed 1.0-second history, with the three-tier trend and small-to-large effect reported

### Requirement: Trained interaction-history factorial
The large MLP and large Transformer SHALL each be trained independently with three explicit ego-target interaction horizons sampled at 0.2-second cadence: current-token only at 0.0 seconds, three tokens spanning 0.4 seconds, and six tokens spanning 1.0 second. Small and medium Transformers SHALL be trained only at the primary 1.0-second horizon. All horizon variants MUST use the same examples that possess a complete valid 1.0-second history, and cropping the history MUST NOT change labels, base-model inputs, or output scope. Information claims SHALL refer specifically to older explicit ego-target interaction tokens beyond the common base predictor inputs and current interaction state, not to history in general.

#### Scenario: Explicit history value is assessed
- **WHEN** the study tests whether explicit interaction history adds predictive information
- **THEN** independently trained 1.0-second and current-token models are compared within the same encoder family and capacity tier on identical paired examples

#### Scenario: Short-history dose response is assessed
- **WHEN** the 0.4-second model is included in analysis
- **THEN** it is treated as a preregistered intermediate horizon that tests monotonicity or saturation between the current-token and 1.0-second endpoints

#### Scenario: One-token Transformer is interpreted
- **WHEN** the Transformer is evaluated with the current token only
- **THEN** it is treated as a negative control for cross-time attention because it cannot mix information across historical tokens

#### Scenario: Frozen history corruption is reported
- **WHEN** zeroed or shuffled history results are retained from prior diagnostics
- **THEN** they are labelled as appendix-level input-sensitivity evidence and do not replace the trained-horizon information or architecture contrasts

### Requirement: Convergence-aware optimisation protocol
Every thesis-core trainable configuration SHALL be trained for seeds 11, 23, and 37 under a maximum budget of 80 epochs, early-stopping patience of 12 epochs, deterministic data order per seed, crash-safe resume, and one common learning rate of `1e-4` frozen before held-out access. The common learning rate SHALL NOT be reselected by family, history, capacity, seed, or held-out outcome.

The frozen optimiser, weight decay, gradient clipping, encoder dropout, and checkpoint unit SHALL be identical wherever required by a matched comparison. Formal training completion SHALL require finite loss and weights; exact train/validation group separation; expected group and four-cell support; unique sample keys; present rasters; finite model inputs and labels; source, model, and dataset hashes; and a machine-readable training-health report. Any run using a debug sample limit SHALL be labelled smoke-only and SHALL NOT satisfy the formal training gate. Lack of improvement or an adverse validation result SHALL remain visible as a diagnostic rather than being silently discarded.

#### Scenario: A run reaches the budget boundary
- **WHEN** more than twenty percent of runs in a required matched comparison select a checkpoint within the final five allowed epochs
- **THEN** the comparison is labelled boundary-limited and the limitation remains visible; no post-outcome budget change is permitted in the time-bounded thesis-core study

#### Scenario: Training resumes after interruption
- **WHEN** a run resumes from a checkpoint
- **THEN** semantic configuration and source provenance are checked and the resumed run cannot silently change data, model, optimiser, seed, history horizon, or capacity settings

### Requirement: Exact frozen-backbone acceleration
The study SHALL permit training from a hash-bound cache containing the frozen B0 raw prediction and final-head input features for each sample. Cached training MUST preserve sample identifiers, interaction inputs, labels, B0 model hash, raster/data hashes, initial predictions, trainable parameter ownership, loss, optimiser, and output distribution. Every accepted cached run SHALL reconstruct a deployable full-input model and pass a declared cached-versus-full numerical parity tolerance before its completion marker is valid.

#### Scenario: A cached run is accepted
- **WHEN** a model is trained without recomputing the frozen raster backbone on every epoch
- **THEN** the completion artefact records cache provenance and a parity audit showing that cached and reconstructed full-model predictions agree within the frozen tolerance

#### Scenario: Cache provenance drifts
- **WHEN** the B0 model, dataset, raster, feature schema, sample ordering, or source hash differs from the cache manifest
- **THEN** training or completion validation fails rather than reusing the stale cache

### Requirement: Locked retrospective held-out evaluation
The time-bounded thesis study SHALL derive immutable rollout-grouped partitions from the sealed groups 1--45 dataset: groups 1--35 for fitting, groups 36--40 for checkpoint selection and calibration, and groups 41--45 for one-pass held-out evaluation. All four policy/style cells SHALL remain complete within every group. Because groups 41--45 have informed earlier development, every thesis artefact MUST label this evaluation retrospective held-out evidence rather than new confirmatory evidence.

#### Scenario: Test evaluation is attempted early
- **WHEN** the fixed optimisation, convergence, capacity, cache provenance, checkpoint selection, and calibration gates are incomplete
- **THEN** the groups 41--45 evaluator refuses to run

#### Scenario: Retrospective held-out metrics are produced
- **WHEN** all freeze gates pass
- **THEN** all three seeds are evaluated exactly once on groups 41--45 and reported by rollout and independent initialisation group

#### Scenario: Held-out support is audited
- **WHEN** the groups 41--45 partition is sealed
- **THEN** the audit reports independent-group and window support for assertive, reactive pre-response, response-onset, and response-active strata, and any sparse stratum remains visible

### Requirement: Comprehensive prediction and interaction reporting
The study SHALL report uncalibrated and validation-calibrated rollout-macro NLL, top-1 ADE/FDE, oracle/min metrics, probability and covariance calibration, trainable and total parameters, training compute, and warmed deployment latency. It SHALL additionally report target speed-profile error, response-onset timing error where defined, conflict-zone entry-time error, and predicted probability mass in the conflict zone by assertive, reactive pre-response, response-onset, and response-active strata. Primary paired effects SHALL use independent initialisation groups and SHALL NOT treat overlapping windows as independent observations.

#### Scenario: Model ranking is generated
- **WHEN** the confirmatory report ranks configurations
- **THEN** it includes effect sizes, paired directions, cluster intervals, seed variability, convergence status, and performance-versus-parameter and performance-versus-latency frontiers

#### Scenario: History mechanism is reported
- **WHEN** a report explains where older interaction tokens help
- **THEN** it reports history gains by response stratum and distinguishes global displacement error from speed, response-timing, and conflict-zone behaviour

### Requirement: Predeclared three-axis inference hierarchy
Let lower rollout-macro NLL be better and define the history gain for encoder `e` and capacity `c` as `G_history(e,c) = NLL(e,0.0s,c) - NLL(e,1.0s,c)`. The primary capacity estimand SHALL be `NLL(Transformer,1.0s,small) - NLL(Transformer,1.0s,large)`. The primary information estimands SHALL be `G_history(MLP,large)` and `G_history(Transformer,large)`. The primary temporal-architecture estimand SHALL be `G_history(Transformer,large) - G_history(MLP,large)`, accompanied by direct MLP-versus-Transformer contrasts at 0.0 and 1.0 seconds. Simultaneous primary claims SHALL use the frozen multiplicity procedure. The 0.4-second dose response, B1 allocation contrasts, ADE/FDE, calibration, response strata, and latency SHALL be identified as supporting or secondary.

#### Scenario: Capacity claim is emitted
- **WHEN** the evidence generator concludes that the original Transformer was capacity-limited
- **THEN** it cites the fixed-1.0-second small-to-large Transformer effect, the full three-tier trend, uncertainty, and convergence audit

#### Scenario: Information claim is emitted
- **WHEN** the evidence generator concludes that explicit interaction history adds predictive information
- **THEN** it cites trained 1.0-second versus current-token effects within each encoder, the 0.4-second dose response, paired retrospective held-out examples, and response-stratified support

#### Scenario: Temporal-attention claim is emitted
- **WHEN** the evidence generator concludes that attention extracts historical information better than an MLP
- **THEN** it requires a favourable matched 1.0-second Transformer-versus-MLP contrast and a favourable history-gain difference-in-differences while reporting the one-token negative-control contrast

#### Scenario: Generic encoder advantage is observed
- **WHEN** Transformer improves similarly over MLP at both 0.0 and 1.0 seconds without a favourable history-gain interaction
- **THEN** the result is described as an encoder-family advantage and not as evidence that temporal attention used history better
