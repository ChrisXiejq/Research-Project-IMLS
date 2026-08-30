# Dissertation evidence

Start with the [thesis evidence guide](THESIS_EVIDENCE_GUIDE.md). Generated
files are immutable research evidence and must not be edited by hand.

Primary corrected sources:

- [future-mask V4e offline evidence](generated/future_mask_v4e_120/) — masked
  Capacity–Information–Architecture results, audits, tables and figures;
- [probability-weighted joint60 evidence](generated/weighted_smpc_v2_recovery/)
  — historical deployed-predictor transfer, supervisor-authority analysis and
  frozen integrity provenance.

Older generated directories are retained only where they support provenance,
tests or secondary diagnostics. Unmasked V3 metrics and unweighted-controller
results are not final corrected estimates.

The allowlisted import boundary is defined by
`core/scripts/models/protocols/publication_evidence_v1.json` and enforced by
`core/scripts/models/materialize_publication_evidence.py`.
