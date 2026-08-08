# Marking rubric → dissertation structure

This map converts the supplied dissertation rubric into concrete writing and
evidence obligations. It is not a substitute for the programme handbook.

| Rubric area | What a distinction-level submission must demonstrate | Where W1 now demonstrates it | Q1/V1 check |
| --- | --- | --- | --- |
| Research area and gap | A clear, strong and tightly focused problem and gap | Abstract; Introduction; Related Work synthesis define one predictor--risk coupling gap and four questions | Verify title, abstract and conclusion retain the same estimands |
| State of the art / related work | Relevant, critical and sufficiently broad coverage | Related Work critically connects risk-aware planning, multimodal calibration, interaction models and closed-loop evaluation; Discussion positions the findings | Citation-key and source-claim audit |
| Methodology | Unambiguous end-to-end specification, explicit assumptions, reproducibility and audit trail | Problem Formulation; Methodology; Experimental Design; Appendices A and C state the factorial design, versions, hashes, commands and boundaries | Clean-checkout reproducibility test |
| Experiments / evidence | Correct controls and baselines, reproducible detail and appropriate statistical evidence | Experimental Design; Results; Appendix B report frozen controls, full contrasts, five-cluster exact/Holm limits and effect directions | Re-resolve M1 and generated-asset hashes |
| Discussion / conclusions | Claims supported by evidence, impact and broader applicability considered | Discussion, Threats, Broader Impact and Conclusion distinguish supported, unsupported and diagnostic findings | Final overclaim and readability pass |

## Rubric-specific safeguards

- The single thesis claim is that task adaptation provides the reliable
  offline gain, whereas added model complexity does not, and that the gain's
  closed-loop value is conditional on the downstream risk--control context.
- The research gap is not “the supervisor is the cause.” The thesis tests the
  non-obvious relationship between task adaptation, explicit sequence use,
  offline metrics and predictor–risk coupling.
- Transformer models are a central experimental question and receive matched
  controls and mechanism ablations, but the final claim follows the evidence:
  they used the sequence and did not win under this protocol.
- Adaptive risk remains part of the core narrative. It is evaluated against a
  full fixed-risk frontier and reframed from universal superiority to a
  conditional operating-point question.
- Statistical insignificance is not hidden. With five clusters, the minimum
  two-sided exact p-value is 0.0625; correct inference, effect sizes and honest
  power limits are stronger scholarship than pseudoreplication.
- External validity is a limitation, not a missing result to fabricate. The
  Discussion must distinguish current evidence from future cross-map,
  cross-junction and real-world validation.
