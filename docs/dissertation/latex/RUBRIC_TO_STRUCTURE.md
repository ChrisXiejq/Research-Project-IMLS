# Marking rubric → dissertation structure

This map converts the supplied dissertation rubric into concrete writing and
evidence obligations. It is not a substitute for the programme handbook.

| Rubric area | What a distinction-level submission must demonstrate | Where it is handled | Remaining writing task |
| --- | --- | --- | --- |
| Research area and gap | A clear, strong and tightly focused problem and gap | Abstract; Introduction §1.1–1.3; Related Work synthesis | Add broad primary citations and explicitly show what existing studies do not jointly test |
| State of the art / related work | Relevant, critical and sufficiently broad coverage | Related Work §2.1–2.5; Discussion comparison paragraphs | This is the largest unfinished component: conduct a current primary-literature search and compare assumptions, controls, metrics and evaluation scale |
| Methodology | Unambiguous end-to-end specification, explicit assumptions, reproducibility and audit trail | Problem Formulation; Methodology; Experimental Design; Appendices A and C | Fill exact software/hardware, hyperparameters, risk values, routes and execution commands from frozen configs |
| Experiments / evidence | Correct controls and baselines, reproducible detail and appropriate statistical evidence | Experimental Design; Results; Appendix B | Keep five-cluster exact/Holm limitation explicit; report effects and uncertainty rather than manufacturing `p<0.05` significance |
| Discussion / conclusions | Claims supported by evidence, impact and broader applicability considered | Discussion; Conclusion; Broader Impact; Threats table | Explain implications for larger systems and production evaluation, but do not claim the current single-map study demonstrates production-scale validity |

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
