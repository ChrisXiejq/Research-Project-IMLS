# Dissertation writing checklist

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

- [ ] Every numerical claim has a `% EVIDENCE:` and `% SOURCE:` comment.
- [ ] Counts distinguish rollouts, windows, full-horizon samples, init clusters,
  cells and simulator frames.
- [ ] B1–B0 closed-loop wording says “frozen predictor stack.”
- [ ] “Significant” appears only when the declared exact/Holm test supports it.
- [ ] Zero observed events are not interpreted as zero risk.
- [ ] Primary, post-selection diagnostic and sensitivity results are separated.
- [ ] The four core verdicts remain visible: H1 supported with boundary;
  H2 not supported; H3/H4 universal claims not supported.
- [ ] Sequence use, calibration tail, deployment reliability and callback
  filtering are labelled diagnostics/robustness checks, not extra hypotheses.
- [ ] No claim generalises beyond the Town05 give-way scope.

## Literature review

- [ ] Use primary papers and official CARLA/model documentation.
- [ ] Cover risk-aware planning, MultiPath/multimodal prediction, calibration,
  interaction Transformers, prediction-aware planning and closed-loop metrics.
- [ ] For each group of papers, compare assumptions, dataset scale, history and
  horizon, baselines, statistics, open/closed-loop evaluation and limitations.
- [ ] End with the precise gap this experiment can actually answer.

## Reproducibility

- [ ] Record Git commit and all manifest/model/calibration hashes.
- [ ] State random seeds and the validation-only selection rule.
- [ ] State CARLA, TensorFlow, CUDA, solver, Python and OS versions.
- [ ] State routes, weather, fixed-risk values, adaptive rule and supervisor
  authority.
- [ ] Give runnable collection, training, evaluation and analysis commands.
- [ ] Verify that the supplement contains no credentials or identity leaks.

## Final TMLR-format pass

- [ ] Update official TMLR style only by replacing it wholesale from the
  official repository; never edit layout parameters.
- [ ] Keep appendices after references.
- [ ] Replace student/supervisor placeholders and remove all visible TODOs.
- [ ] Check every figure in colour and greyscale; captions must stand alone.
- [ ] Compile from a clean checkout and inspect every page for overflow,
  unreadable labels, isolated captions and broken references.
- [ ] If submitting to TMLR rather than UCL, switch to anonymous mode and audit
  the PDF/source/supplement for identity and repository links.
