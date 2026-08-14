# Supervisor feedback 2 — solver timing, controller acceptance and fallback

Evidence status: **partial_raw_required**.

## Preliminary legacy aggregate — not a final solver result

The frozen aggregate counted rule-yield bypass decisions as successful zero-second solves. It is retained only to reproduce the previous report and must not be used for final timing or controller-acceptance claims.

Under that legacy conflated definition, adaptive mean rollout P95 was 104.24 ms and fixed-medium was 90.23 ms; the legacy paired difference was +14.01 ms.
The legacy logger diagnostic was 264/17230 non-optimal/debug rows. Its denominator contains all logged control contexts, including bypass/no-solve and rows without solver telemetry, and is therefore not an attempted-solve controller-acceptance rate.

## Corrected attempted-solve audit

**Not evaluated.** The hash-validated raw R3 snapshot is required to separate solver execution decisions into rule-bypass/no-solve, attempted-accepted and attempted-fallback/nonaccepted rows. Prediction validity remains a context stratifier. The legacy numbers above remain preliminary.

## Statistical unit and taxonomy boundary

Step counts diagnose execution. The five ego-initialisation clusters, not individual steps, are the independent units for paired summaries.

Raw taxonomy status: **not_evaluated**. extracted raw snapshot directory was not provided
Return status, exception, fallback, supervisor action and exact deadline outcomes are not inferred from aggregate tables.
