# Open Loop Debug Session

Status: OPEN

Session ID: open-loop

## Symptom

`smpc_open_loop` still runs to 600 steps in `20260523_163954`, has no `smpc_completion.json`, and reports lower feasibility than the closed-loop risk-aware SMPC policies.

## Hypotheses

1. The open-loop optimisation becomes infeasible or unbounded early, causing fallback controls for a large portion of the rollout.
2. The open-loop controller lacks feedback policy structure, so after avoidance it cannot recover to the reference path as reliably as `smpc_var_risk` / `smpc_fixed_risk`.
3. The latest reference recovery logic helps closed-loop SMPC but may not be sufficient for open-loop dynamics/control rollout.
4. `SMPC_MMPreds_OL` still uses a configuration mismatch or overly conservative assumptions for the current single-TV intersection case.
5. The stricter completion criterion correctly exposes that open-loop never reaches the valid completion region.

## Evidence Log

- Initial evidence source: `core/results/20260523_163954`.
- Closed-loop `var_risk` and `fixed_risk` both reach valid completion.
- `smpc_open_loop` runs 600 steps with `ego_feasible_frac=0.743333`.
- First open-loop failure occurs at step 18 with Gurobi `return_status=INF_OR_UNBD`.
- Open-loop records 154 fallback steps out of 600.
- All open-loop debug records use `tight=2.053748910631823`.
- Closed-loop `SMPC_MMPreds` uses `risk_profile=upstream_code`, which maps to tightening `1.64`.
- `SMPC_MMPreds_OL` currently does not receive `risk_profile` from `SMPCAgent` and defaults to `PAPER_INTERSECTION_TIGHTENING`.

## Current Assessment

Hypothesis 1 is supported: open-loop has repeated `INF_OR_UNBD` failures and falls back to emergency/control-reference actions.

Hypothesis 4 is strongly supported: the open-loop ablation uses a stricter tightening than the current reproduction profile, making it more conservative than the closed-loop methods.

Hypothesis 2 remains plausible: even when feasible, the open-loop formulation lacks the closed-loop feedback structure used by `smpc_var_risk` and `smpc_fixed_risk`.

## Next Instrumentation

Before changing open-loop behaviour, add explicit debug fields for:

- `risk_profile`
- `target_prob`
- `tight`
- `N_TV_MAX`
- consecutive fallback count
- first failing `s`, `ey`, `dv0`, `v_ref`, `a_ref`, `df_ref`

Then test whether making `SMPC_MMPreds_OL` respect `risk_profile=upstream_code` improves feasibility.

## Fix Applied

- Added explicit open-loop debug fields for `risk_profile`, `target_prob`, `tight`, and the latest reference/update values.
- Changed `SMPC_MMPreds_OL` so its default tightening is derived from `risk_profile` instead of always using the stricter paper epsilon value.
- Passed `SMPCAgent.risk_profile` into `SMPC_MMPreds_OL`.

Expected post-fix evidence:

- `smpc_open_loop` debug records should show `risk_profile="upstream_code"`.
- `smpc_open_loop` debug records should show `tight=1.64` instead of `2.053748910631823`.
- If the hypothesis is correct, the first `INF_OR_UNBD` step should move later or disappear, and feasibility should improve above `0.743333`.
