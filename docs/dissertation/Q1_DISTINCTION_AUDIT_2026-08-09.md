# Q1 distinction audit — 2026-08-09

> Historical status note (2026-08-14): this audit passed for the pre-feedback
> evidence cut. A later external supervisor request created the bounded SF1--SF5
> amendment documented in `SUPERVISOR_FEEDBACK_CLOSURE_2026-08-14.md`. Its SF4
> corrected-supervisor application-authority experiment is not an outcome-selected continuation of R3 or the
> cancelled R4. Q1 must be rerun after SF1--SF5 before release.

## Decision

**Historical decision for the 2026-08-09 evidence cut:** scientific Q1 passed
and submission-release Q1 awaited four verified human inputs; at that time no
additional CARLA experiment was required or authorised. This decision is
superseded only by the bounded, externally requested SF1--SF5 amendment in the
status note above.

The detached clean-checkout gate at commit
`2f80639d56289253149a40fa08f1b2c44f0dc00a` regenerated the corrected A2
synthesis, all 82 M1 value-resolving records and every W1 evidence table;
regenerated artefacts matched the committed scientific outputs. It also ran
66/66 analysis tests and built a 25-page TMLR-layout PDF. The Q1 audit found no
missing citation, unmatched evidence ID, blocking LaTeX error, credential,
prohibited overclaim or legacy/corrected pooling failure.

Q1 does **not** label the upload-ready gate complete because candidate metadata,
the module-specific GenAI category and the module word/page rule are not
recoverable from the repository. Guessing them would reduce, not improve,
submission integrity.

Machine receipts:

- `docs/paper/generated/distinction_v1/12_q1_final_audit/Q1_COMPLETE.json`;
- `docs/paper/generated/distinction_v1/12_q1_final_audit/Q1_CLEAN_CHECKOUT_AUDIT.json`;
- `docs/paper/generated/distinction_v1/12_q1_final_audit/Q1_SCIENTIFIC_MANUSCRIPT_AUDIT.json`.

## What Q1 independently rechecked

### Scientific consistency

- H1 remains an in-distribution task-adaptation claim and includes constant
  velocity, clipped constant acceleration and train-mean physical baselines.
- H2 architecture attribution is confined to the matched residual scopes T1
  versus B2-M and T2 versus B2-D. The manuscript explicitly says B1 is not
  parameter matched and that 10/15 runs reached the epoch ceiling.
- H3 remains a frozen predictor-**stack** contrast because B0/B1 calibration
  differs. The 15-window response-active tail is legacy diagnostic evidence and
  is not pooled with corrected R3.
- H4 is an empirical operating-point observation under a coupled policy stack,
  not isolated risk-allocation causality, equivalence or chance-constraint
  validation.
- The native-collision, reconstructed callback, actual-bounding-box and legacy
  mode-mapping boundaries are visible rather than silently removed.
- Five paired init groups remain the independent R3 units. The manuscript
  reports the minimum two-sided exact value of 0.0625 and never creates a fake
  sample size from windows, frames or solver steps.

### Evidence and reproducibility

| Gate | Q1 result |
| --- | --- |
| M1 locator/value audit | 82/82 records; zero invalid locator/value mismatch/orphan claim/pooling violation |
| Corrected R3 | 80/80 rollouts; five init groups; H3 2/8; H4 3/12 |
| A2/M1/W1 clean recomputation | Exact artefact match |
| Analysis regression suite | 66/66 pass |
| Active release scripts | `--help` and declared inputs pass |
| Bibliography | 27 cited / 27 defined; no missing or unused entry |
| Credential scan | zero hit in tracked release source |
| CARLA status at this historical cut | not reopened; later superseded only by the bounded external-feedback SF4 amendment |

Appendix A now distinguishes two reproducibility levels. A normal Git checkout
contains the code, frozen configuration, selected deployed weights, R3 raw
receipts, derived evidence and hashes needed to rerun analysis and rebuild the
paper. Full model retraining additionally needs the separately retained large
200-rollout raster dataset. This avoids falsely calling a small Git archive a
complete end-to-end replay package.

### Manuscript and PDF

- The title now exactly matches the frozen focused route:
  *Task-Adapted Motion Prediction under Predictor–Risk Coupling: A Controlled
  CARLA Give-Way Study*.
- Abstract, RQ1–RQ4, H1–H4, Results, Discussion and Conclusion use the same
  estimands and bounded verdicts.
- The current PDF has 25 pages. Every page was visually inspected; key figures
  and dense Appendix B tables were also inspected at original render size.
- No content was clipped, overlapped or pushed outside the page; figures and
  table labels remain readable; appendices follow the references.
- The first page now discloses actual Codex assistance. This follows TMLR's
  transparency requirement, but the ELEC0054 brief still decides whether that
  use is permitted.
- The raw LaTeX source contains approximately 7,894 whitespace-delimited tokens
  including commands, captions, comments and appendices. This is **not** an
  official word count; the programme rule must be obtained before displaying a
  submission word count.

## Rubric judgement

| ELEC0054 area | Q1 judgement | Strongest evidence | Residual mark risk |
| --- | --- | --- | --- |
| Research area and gap | distinction-ready | one central thesis; four linked hypotheses; supervisor-only story rejected | do not add another claim during revision |
| State of the art | distinction-ready | 27 relevant primary/official sources organised as critical synthesis | contribution must remain a controlled synthesis, not a “first” claim |
| Methodology | distinction-ready at analysis level | end-to-end contracts, hashes, assumptions, clean rebuild and audit trail | raw raster dataset must remain examiner-accessible separately |
| Experiments and evidence | rigorous but rubric-sensitive | physical/control baselines, 15 model runs, frozen test, corrected factorial R3 and exact/Holm analysis | only five independent R3 clusters, so no conventional two-sided significance |
| Discussion and conclusions | strong critical discussion with an external-validity ceiling | supported/unsupported hypotheses, impact, mechanisms, limitations and procedural implications | one Town05 junction is not scale/production; do not imply that it is |

The dissertation is defensible as distinction-level work because the technical
depth, controls, negative findings, prospective freeze and evidence audit are
substantive. A distinction is not guaranteed: the literal rubric wording on
statistical significance and broad/production scope remains the examiner's
largest basis for marking below 70. The academically correct response is the
current transparent limitation, not post-outcome data collection or
pseudoreplication.

## Repairs completed during Q1

1. Unified the title with the frozen final route.
2. Added a first-page, non-author LLM-use disclosure covering planning, code,
   debugging, audit automation and manuscript assistance.
3. Added a precise data/artefact availability statement.
4. Expanded the rubric map to every supplied distinction descriptor and its
   hardest examiner attack.
5. Added `--help`, input/output arguments and validation to the W1 evidence
   builder and figure renderer.
6. Added a single Q1 command that refuses a dirty worktree, constructs a
   temporary detached checkout, recomputes A2/M1/W1, runs tests, builds the PDF
   and records machine receipts.
7. Rebuilt and visually inspected the current 25-page PDF.

## Four inputs required to close submission-release Q1

The candidate must supply or confirm all four together:

1. candidate number **or** full name, exactly as the ELEC0054 submission brief
   requires;
2. exact MSc programme/degree wording and whether the title block must contain
   the supervisor;
3. the ELEC0054 GenAI category or written module-leader instruction;
4. the official word/page limit, what is included, and where the word count
   must appear.

After inserting those verified values, rebuild the PDF, visually check page 1
and any changed page break, then rerun:

```bash
.venv-precarla/bin/python core/scripts/models/audit_q1_dissertation.py \
  --clean-checkout \
  --visual-review-complete \
  --programme-ai-confirmed \
  --module-length-rule-confirmed \
  --python "$PWD/.venv-precarla/bin/python"
```

The source should then be committed before the final clean-checkout rerun. V1,
not Q1, will bind the submitted PDF, source archive and final Git commit into
the release inventory and prepare the viva materials.

## Policy sources checked at Q1

- [UCL student GenAI guidance](https://www.ucl.ac.uk/study/current-students/exams-and-assessments/assessment-success-guide/engaging-generative-ai-your-education-and-assessment): acknowledge assistive use; the assessment instructions remain decisive.
- [UCL three-category guidance](https://www.ucl.ac.uk/teaching-learning/generative-ai-hub/three-categories-genai-use-assessment): the module leader determines permitted use.
- [TMLR author guide](https://jmlr.org/tmlr/author-guide.html): official style, PDF format and appendices after references.
- [TMLR FAQ](https://www.jmlr.org/tmlr/faq.html): LLM writing assistance must be disclosed on the first page.
