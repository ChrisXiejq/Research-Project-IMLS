# Dissertation writing and review checklist

The original pre-feedback W1 draft and Q1 audit are historical baselines, not
submission-ready receipts. SF1/SF2 offline closure and the prospectively frozen
SF4 authority ablation must finish before SF5 rebuilds M1/W1/Q1. The checklist
below records both completed foundations and still-open final-release gates.

## Recommended order

1. Fill Methodology and Appendix A from frozen configurations and manifests.
2. Complete Results from canonical tables/figures and evidence IDs.
3. Write Discussion around three findings: simple adaptation wins offline;
   calibration/sequence diagnostics qualify that result; closed-loop value is
   conditional.
4. Conduct and write the critical Related Work review.
5. Rewrite Introduction so its gap follows from the literature review.
6. Finalise Conclusion, Abstract and title last.

## Evidence discipline

- [x] Every headline numerical result has an adjacent `% EVIDENCE:` and source
  comment or is rendered from a hash-bound generated table.
- [x] Counts distinguish rollouts, windows, full-horizon samples, init clusters,
  cells and simulator frames.
- [x] B1–B0 closed-loop wording says “frozen predictor stack.”
- [x] “Significant” appears only when the declared exact/Holm test supports it.
- [x] Zero observed events are not interpreted as zero risk.
- [x] Primary, post-selection diagnostic and sensitivity results are separated.
- [x] The four core verdicts remain visible: H1 supported with boundary;
  H2 not supported; H3/H4 universal claims not supported.
- [x] Sequence use, calibration tail, deployment reliability and callback
  filtering are labelled diagnostics/robustness checks, not extra hypotheses.
- [x] No claim generalises beyond the Town05 give-way scope.

## Literature review

- [x] Use primary papers and official CARLA/model documentation.
- [x] Cover risk-aware planning, MultiPath/multimodal prediction, calibration,
  interaction Transformers, prediction-aware planning and closed-loop metrics.
- [x] Compare the assumptions and evaluation scope that matter to the argument,
  including open- versus closed-loop evidence, calibration and interaction.
- [x] End with the precise gap this experiment can actually answer.

## Reproducibility

- [ ] Record the final release Git commit and submitted-PDF hash at V1; W1
  already records all evidence, model and calibration hashes.
- [x] State random seeds and the validation-only selection rule.
- [x] State the recoverable CARLA, TensorFlow, Python and OS versions and
  explicitly disclose unavailable archived CUDA/cuDNN/solver version strings.
- [x] State routes, weather, fixed-risk values, adaptive rule and supervisor
  authority.
- [ ] Give the frozen collection, training, evaluation and analysis entry
  points; SF4 is the one remaining CARLA experiment, after which only offline
  regeneration and manuscript work are allowed.
- [x] Verify that the Q1 manuscript/evidence source contains no credentials;
  repeat on the exact final V1 archive after inserting submission metadata.

## Final TMLR-format pass

- [x] Use the vendored official TMLR style without modifying layout parameters.
- [x] Keep appendices after references.
- [x] Remove visible drafting markers from the W1 scientific manuscript.
- [ ] Insert verified UCL candidate/supervisor metadata at the submission pass.
- [ ] Update official TMLR style only by replacing it wholesale from the
  official repository; never edit layout parameters.
- [x] Check every figure in colour and greyscale; captions stand alone and
  outcome labels remain readable without colour.
- [ ] Compile and inspect the post-SF5 PDF for overflow, unreadable labels,
  isolated captions and broken references; the earlier W1 inspection is stale.
- [ ] Rebuild from a clean checkout after SF1--SF5 and the final Q1 audit, then
  repeat after inserting the verified submission-only values.
- [ ] If submitting to TMLR rather than UCL, switch to anonymous mode and audit
  the PDF/source/supplement for identity and repository links.
