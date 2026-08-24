## Purpose

Defines a falsifiable and provenance-bound evidence contract for studying how prediction, risk allocation, SMPC and a rule-based supervisor jointly determine executed give-way behaviour.

## ADDED Requirements

### Requirement: Central thesis argument is bounded by identified causal evidence
The study SHALL use the following central argument: in the tested right-hand-traffic Town05 give-way task, task-specific prediction and short interaction history improve bounded offline prediction, but additional capacity, attention and adaptive risk do not uniformly improve executed behaviour; the rule-based supervisor has a large common causal effect on nominal yielding and completion, while the existing evidence does not establish that it selectively masks one upstream method.

#### Scenario: Reader-facing claim generation
- **WHEN** an abstract, introduction, result, discussion, conclusion or figure caption is generated
- **THEN** it distinguishes observed association, direct treatment effect and unsupported mechanism, and it does not claim universal superiority, formal safety, equivalence, cross-map generalisation or selective masking without the corresponding evidence

### Requirement: Four hypotheses have fixed estimands and decision rules
The evidence package SHALL represent the study with four falsifiable hypotheses whose verdicts may be supported, unsupported or bounded negative findings.

#### Scenario: H1 capacity evaluation
- **WHEN** H1 is evaluated
- **THEN** the system compares small, medium and large task-trained Transformer capacity at fixed 1.0 s history using rollout-macro NLL across the frozen paired groups, and treats a non-monotonic or non-confirmatory trend as evidence against capacity insufficiency as the main explanation

#### Scenario: H2 information evaluation
- **WHEN** H2 is evaluated
- **THEN** the system compares current-token-only, 0.4 s and 1.0 s trained interaction histories at matched capacity for both MLP and Transformer families, reporting effect size, paired-group direction and saturation rather than only a significance label

#### Scenario: H3 architecture evaluation
- **WHEN** H3 is evaluated
- **THEN** the system compares matched MLP and Transformer cells at the same capacity and history and reports both direct encoder-family gaps and the history-gain difference-in-differences required to attribute an advantage specifically to attention

#### Scenario: H4 closed-loop system evaluation
- **WHEN** H4 is evaluated
- **THEN** the system separately tests predictor transfer, adaptive-versus-fixed risk, and complete supervisor behavioural authority using the frozen V3, R3 and SF4 populations, and concludes only that the supervisor has a large common authority effect unless a valid interaction estimand demonstrates selective attenuation

### Requirement: Foundation adaptation remains a supporting result
The study SHALL report pretrained MultiPath B0 versus task-adapted B1 as the task-foundation manipulation that motivates the controlled model study, but SHALL NOT relabel that comparison as the Capacity hypothesis.

#### Scenario: MultiPath foundation is introduced
- **WHEN** the predictor methodology or first offline result is presented
- **THEN** the system explains the MultiPath mixture representation, reports the common frozen-test B0/B1 NLL, ADE and FDE comparison, and states the Town05 and response-active-tail boundaries

### Requirement: Experimental populations remain separate
The evidence system SHALL preserve the independent units, treatments and provenance of F1 foundation adaptation, R3 broad predictor--risk, SF4 authority, V3 offline decomposition and V3 selected-model deployment.

#### Scenario: Cross-experiment synthesis
- **WHEN** results from more than one evidence block support one discussion claim
- **THEN** the result identifies each source population separately and does not pool rollouts, windows, groups, effect sizes or significance tests across incompatible blocks

### Requirement: Existing evidence is exhausted before new CARLA collection
The system SHALL create a claim--evidence--boundary matrix and a raw-telemetry availability audit before authorising any new simulator experiment.

#### Scenario: Existing evidence answers the hypothesis
- **WHEN** a canonical completed experiment directly estimates the hypothesis with an acceptable boundary
- **THEN** no replacement or outcome-selected expansion is launched

#### Scenario: Material evidence gap remains
- **WHEN** a headline claim cannot be supported or rejected from canonical evidence and raw telemetry
- **THEN** a new experiment may proceed only after its treatment matrix, independent unit, primary outcomes, decision rule, stopping rule, nuisance settings and source hashes are frozen before outcomes are inspected

### Requirement: Supervisor limitations use direct observables
Claims about rule-based supervisor limitations SHALL be tied to observed authority requests and applications, direct on/off effects, solver/fallback accounting, threshold or timing sensitivity, and upstream-to-physical translation; similar final trajectories alone are insufficient.

#### Scenario: Behavioural attenuation is analysed
- **WHEN** the paper uses terms such as attenuation, compression, masking or bottleneck
- **THEN** it reports the relevant nominal/candidate/actual command contrast or treatment interaction, intervention frequency and intensity, and a causal boundary that names other active compression mechanisms

#### Scenario: Supervisor-off arm saturates at failure floor
- **WHEN** SF4 difference-in-differences is interpreted
- **THEN** the system reports the authority-off completion and adverse-outcome floor and does not convert a near-zero interaction into equivalence or proof of no masking

### Requirement: Give-way task is specified consistently
The scenario SHALL be defined as an unsignalised right-hand-traffic interaction in which the ego turns left across an opposing target that proceeds straight with priority, so the ego must approach, yield before conflict, and resume after clearance.

#### Scenario: Scenario appears in manuscript or figure
- **WHEN** the task is described textually or visually
- **THEN** ego and target routes, priority, conflict geometry, target behaviour and success phases are unambiguous and consistent with the executed CARLA configuration
