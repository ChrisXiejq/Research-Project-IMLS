## Why

The current dissertation establishes a cross-layer predictor--risk--SMPC--supervisor evidence chain, but its central claim is broader than the most consequential observed phenomenon: the rule-based supervisor achieves nominal physical yielding while substantially compressing, and in some comparisons preventing identification of, upstream predictor and risk-allocation differences. A sharper hypothesis-led paper must separate three questions--physical effectiveness, predictor-to-action transfer, and risk-to-action transfer--and reserve the causal term *masking* for contrasts that identify it.

## What Changes

- Reframe the dissertation around the effectiveness--limitation tension of complete rule-based supervisor authority in a controlled Town05 right-hand-traffic left-turn give-way task.
- Replace the previous four-hypothesis structure with three falsifiable hypotheses: nominal yielding under supervisor authority; transfer or masking of Capacity--Information--Architecture predictor advantages; and transfer or masking of fixed/adaptive risk-allocation differences.
- Re-audit local and server-side V3, R3, SF4, timing-shift and legacy results at predictor, nominal-control, supervisor-candidate and executed-action layers without pooling incompatible populations.
- Define *retained*, *attenuated*, *compressed*, *not transferred* and causally *masked* as distinct verdicts with explicit identification requirements.
- Add supplemental analysis or frozen experiments only when the evidence-gap gate shows that an intended headline claim is not identifiable from existing paired or factorial evidence.
- Rebuild the manuscript methods so that MultiPath, multimodal SMPC, risk allocation and every rule-based supervisor channel are defined from inputs through equations to executed controls.
- Regenerate publication figures and tables with Python/Matplotlib only, then rewrite Results first and the title/abstract last using the nature-writing workflow.
- Preserve the previous release as an immutable evidence snapshot; emit the reframe into a separately versioned release.

## Capabilities

### New Capabilities

- `supervisor-masking-evidence`: Provides a provenance-bound, non-pooled evidence and identification contract for physical yielding, predictor-to-action transfer and risk-to-action transfer.
- `supervisor-masking-thesis-release`: Provides the restructured manuscript, reproducible mathematical exposition, Python-generated figures/tables, audits and submission release manifest.

### Modified Capabilities

None. The completed `supervisor-bottleneck-thesis` change remains an immutable prior release rather than an in-place requirement change.

## Impact

The change affects evidence-analysis scripts and tests under `core/scripts/models/`, generated evidence under a new `docs/paper/generated/` release root, OpenSpec artifacts, and the separate `Jiaqi-Xie-Dissertation` manuscript repository. It may add a bounded CARLA 0.9.14 experiment only after a signed evidence-gap decision and frozen protocol. It does not alter historical V3, R3 or SF4 outcomes, CARLA scenario geometry, model weights, solver settings, or the previous release artifacts.
