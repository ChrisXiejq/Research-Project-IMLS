# Dissertation evidence

Start with the [thesis evidence guide](THESIS_EVIDENCE_GUIDE.md). Generated
files are immutable research evidence and must not be edited by hand.

Primary corrected sources:

- [future-mask V4e offline evidence](generated/future_mask_v4e_120/) — masked
  Capacity–Information–Architecture results, audits, tables and figures;
- [probability-weighted joint60 evidence](generated/weighted_smpc_v2_recovery/)
  — historical deployed-predictor transfer, supervisor-authority analysis and
  frozen integrity provenance.
- [SF4 preregistration fixture](generated/distinction_sf4_supervisor_authority_ablation/prereg/)
  — the frozen protocol consumed by the supervisor-authority contract tests;
  it is retained as a test dependency rather than headline result evidence.

Closed-loop demonstration:

- [CARLA bird's-eye video](CARLA_video.mp4) — 2,078,047 bytes; SHA-256
  `8e61a54f58b9d35b1125289ddf5fbcabe2050335c116826f0e8d3c5a51e50c10`.

Other historical generated directories are excluded from the publication
release. Unmasked V3 metrics and unweighted-controller results are not final
corrected estimates.

The allowlisted import boundary is defined by
`core/scripts/models/protocols/publication_evidence_v1.json` and enforced by
`core/scripts/models/materialize_publication_evidence.py`.
