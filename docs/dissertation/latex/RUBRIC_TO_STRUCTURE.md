# ELEC0054 rubric → distinction evidence map

This is the active mapping from the supplied two-page ELEC0054 marking rubric
to examiner-visible evidence. The original Q1 receipt is a pre-feedback
baseline; this map becomes final only after SF1/SF2/SF4, the SF5 evidence and
manuscript rebuild, and a new clean Q1 audit. It does not replace the current
module brief or Moodle submission instructions.

## Descriptor-level mapping

| Rubric area | Distinction descriptor in the supplied rubric | Examiner-visible evidence | Machine/audit evidence | Q1 judgement and attack to answer |
| --- | --- | --- | --- | --- |
| Research area and gap | “Clear, strong, and focused” | Abstract; Introduction §§1.1–1.3; Related Work synthesis; exactly one central thesis and RQ1–RQ4 | Q1 title/thesis/verdict consistency checks; M1 four-hypothesis package | **Pass.** The thesis is not “the supervisor caused the result”; it is the bounded relation between task adaptation, tested temporal adapters and predictor–risk coupling. Do not add a fifth hypothesis. |
| State of the art and related work | “Present, relevant, critical and sufficiently broad” | Related Work compares risk-aware planning, multimodal prediction/calibration, interaction Transformers and closed-loop evaluation, then states why each strand does not answer the crossed frozen-stack question | 27 cited and 27 resolved bibliography records; no uncited entry or missing key; Q1 overclaim scan | **Pass with normal examiner judgement.** The contribution is a controlled empirical synthesis, not the first discovery of open/closed-loop mismatch or a general new Transformer. |
| Methodology | “Unambiguous, fully specified, and reproducible end-to-end method with explicit assumptions and audit trail” | Problem Formulation; Methodology; Experimental Design; Appendix A specify population, split, coordinate frame, models, training budget, calibration, deployment, outcomes, retries, statistics and hashes | Clean-checkout regeneration; regression suite; completion manifests and SHA-256 chain; SF1/SF2 immutable-archive audit and SF4 preregistration | **Conditional pass pending final receipts.** Full retraining additionally needs the separately retained 200-rollout raster dataset; this boundary is stated rather than hidden. |
| Experiments and evidence | Correct controls/baselines, statistical evidence and reproducible detail | Physical baselines; simple B1 control; two matched-scope MLP/Transformer pairs; frozen one-shot test; corrected 2×4×2×5 R3 matrix; SF1 stop/release audit; SF2 solve-attempt taxonomy; prospective SF4 complete-authority ablation | 200 data rollouts; 15 model runs; 80/80 R3 rollouts; five R3 init clusters; 80-key SF4 with ten new clusters; exact sensitivities, cluster intervals, Holm families and value-resolving evidence audit | **R3/ML evidence sound; final closure pending.** Never create false significance from windows/frames. SF1/SF2 raw receipts and SF4 80/80 analysis/full snapshot are mandatory before submission. |
| Discussion and conclusions | “Impact discussed, claims supported, broad scope of application (e.g. tested at scale/production)” | Discussion explains why task adaptation wins here, why transfer is conditional, the remaining role of adaptive risk, quantified supervisor authority, threats, procedural implications and future cross-map validation; Broader Impact and Conclusion bound safety claims | H1–H4 verdicts plus four-row supervisor response re-resolve to rebuilt M1; legacy/corrected separation and zero-event language gates | **Pending result-specific SF4 synthesis.** This remains one-junction simulator evidence, not production. The distinction case rests on technical depth, auditability and critical evaluation, not pretending production scale. |

## Focus safeguards

- The single thesis is: task adaptation provides the directionally consistent in-distribution offline gain in
  this frozen setting; tested additional sequence complexity does not add a
  consistent gain; downstream value and adaptive-risk value are conditional
  on the coupled operating context.
- The four hypotheses remain H1 task adaptation, H2 tested Transformer added
  value, H3 uniform offline-to-closed-loop transfer and H4 adaptive dominance.
  Calibration, sequence ablation, collision filtering and deployment telemetry
  are diagnostics or sensitivities, not extra hypotheses.
- H2 architecture attribution is confined to T1 versus B2-M and T2 versus
  B2-D. B1 is the best tested simple control but is not parameter matched to
  those adapters.
- H3 is a frozen **predictor-stack** comparison because B0 and B1 calibration
  differ. The response-active legacy tail is diagnostic and is never pooled
  with corrected R3.
- H4 reports empirical operating-point dominance under a shared corrected
  stack; it does not identify risk allocation as an isolated cause or validate
  a real-world chance constraint.
- Zero observed binary failures establish nominal outcome reliability only;
  they do not establish per-step MPC feasibility. Continuous
  actual-bounding-box separation remains the discriminating safety-margin
  outcome.

## Submission-only items outside scientific inference

- Replace the neutral review author block with the candidate number or name,
  exact degree/programme wording and any supervisor field required by the
  current ELEC0054 brief. Do not infer these from Git history.
- Confirm the module's GenAI category. The first-page disclosure already
  states the actual assistive uses; UCL central guidance does not override a
  stricter module brief.
- Confirm the module word/page rule and how a word count must be displayed.
- Record the final release commit, PDF digest and source-archive digest at V1.

## Hard examiner questions already answered in the manuscript

1. **Why no conventional significance?** Five independent paired init groups
   imply a minimum two-sided exact value of 0.0625; windows and frames are not
   independent experimental units.
2. **Did the predictor manipulation survive deployment?** Yes: B1 is better in
   all five groups across all 40/40 registered in-loop metric–policy–style
   checks, but that is a manipulation check rather than a second benchmark.
3. **Did Transformers ignore the sequence?** No: frozen sequence shuffling
   worsens their NLL. They used the input but did not consistently beat the
   matched MLP scopes or simple B1 under this budget.
4. **Is B1 a pure architecture effect?** No. H3 estimates the frozen deployed
   stack, including its validation-frozen calibration.
5. **Why retain adaptive risk after H4?** It dominates in 3/12 prespecified
   contexts, so it remains a conditional operating point, not a universal
   replacement for all fixed settings.
6. **Why are legacy results present?** They motivate mechanisms and robustness
   boundaries only; corrected R3 is the sole primary closed-loop matrix.
