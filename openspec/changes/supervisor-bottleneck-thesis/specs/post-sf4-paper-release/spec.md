## Purpose

Defines the reproducible analysis, manuscript-asset and repository-quality gates required to release the completed post-SF4 thesis as a clean, submission-ready project.

## ADDED Requirements

### Requirement: Post-SF4 evidence is generated from canonical sources
The release pipeline SHALL regenerate all headline scalars, tables, figures and claim verdicts from hash-verified canonical CSV/JSON/raw-log sources and SHALL fail closed on missing, stale or inconsistent evidence.

#### Scenario: Paper asset generation
- **WHEN** paper assets are built
- **THEN** every reported scalar has a source locator, aggregation unit, evidence role and claim boundary, and no generated evidence file is manually edited to change an outcome

### Requirement: Supervisor mechanism audit separates factual pathways
The post-SF4 analysis SHALL distinguish rule bypass/no-solve, factual solver attempt, raw return status, controller acceptance, fallback, supervisor candidate, applied command and physical rollout outcome.

#### Scenario: Solver or feasibility result is reported
- **WHEN** controller performance is summarised
- **THEN** bypass steps are excluded from attempted-solve denominators, controller acceptance is not called mathematical feasibility, and rollout completion is not substituted for solver status

### Requirement: Behaviour phases are reported only when observable
Approach, yield/stop, target-clearance and release/resume behaviour SHALL use explicit event definitions and availability checks.

#### Scenario: Event clock is incomplete
- **WHEN** a required event cannot be reconstructed for a complete paired block
- **THEN** the endpoint remains missing or becomes a stated limitation and is not imputed from another clock or a provisional debug field

### Requirement: Figures are reproducible academic visualisations
All result figures SHALL be produced programmatically in Python from canonical evidence using restrained journal-style visual design, explicit legends, units, uncertainty or paired observations where applicable, and multi-panel composition when several related dimensions support one claim.

#### Scenario: Main-text figure is accepted
- **WHEN** a generated figure is proposed for the dissertation
- **THEN** its source script, data inputs, caption, vector or high-resolution output and visual QA result are present, and the figure contains no AI-generated decorative artwork

### Requirement: Manuscript follows the frozen evidence chain
The reader-facing dissertation SHALL be completed using the nature-writing argument workflow and SHALL be organised as Introduction, Literature Survey, Problem Formulation, Methodology, Experimental Design, Result Analysis and Conclusion, with a distinct Discussion function inside Result Analysis or as an allowed substructure, plus appendices for detailed formulas, tables and reproducibility material. The working draft SHALL target approximately 15 pages before user-led shortening and SHALL contain at least 25--30 verified, relevant references.

#### Scenario: Full manuscript audit
- **WHEN** the dissertation is built for review
- **THEN** the title, abstract, hypotheses, methods, result order, discussion and conclusion all trace to the same central argument, detailed formulas and supplementary data are placed in appendices where appropriate, and internal day labels, run-management rules and engineering diary language are absent from reader-facing prose

### Requirement: Existing work is classified before repository cleanup
The release process SHALL inventory every tracked modification and untracked artifact in both repositories, classify it as canonical implementation, generated evidence, exploratory work, manuscript asset, reproducible temporary output or discard candidate, and preserve user work until its disposition is explicit.

#### Scenario: Dirty worktree is reconciled
- **WHEN** commits are prepared
- **THEN** unrelated or exploratory changes are separated into reviewable commits or documented archives, reproducible caches are ignored, no destructive reset is used, and both repositories end with no unexplained worktree changes

### Requirement: Submission tag passes reproducibility gates
A submission-ready revision SHALL pass relevant unit/integration tests, evidence audits, manuscript compilation, bibliography checks and page-by-page PDF visual inspection before it is tagged or described as final.

#### Scenario: Final release candidate
- **WHEN** the project is declared submission-ready
- **THEN** the experiment commit, dissertation commit, evidence completion markers, test results, build log and remaining bounded limitations are recorded together in a final release manifest
