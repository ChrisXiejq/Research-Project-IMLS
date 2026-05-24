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

## 20260524_121954 Result

- Latest run confirmed the risk-profile fix was active: `smpc_debug_setup.json` shows `risk_profile="upstream_code"` and `tight=1.64`.
- Open-loop still did not complete: `ego_n_steps=600`, `ego_feasible_frac=0.745`, first failure at step 18 with `INF_OR_UNBD`.
- Therefore the main cause is no longer the risk tightening mismatch. The remaining problem is open-loop feasibility and recovery: when the solver fails once, the previous hard-brake fallback can push the rollout into a stalled/off-route state.

## Second Fix Applied

- Added a separate, heavily penalised `collision_slack` to the open-loop SOC collision constraints. This keeps the constraint nearly hard, but prevents one boundary collision constraint from making the whole open-loop problem immediately `INF_OR_UNBD`.
- Changed the open-loop fallback from hard braking to the current reference input. This avoids cascading failures where a single infeasible solve causes excessive braking, low speed, and persistent off-route behaviour.
- Added `slack` and `collision_slack` debug values to open-loop solver output.

Expected post-fix evidence:

- `smpc_open_loop` feasibility should improve from `0.745`.
- The first `INF_OR_UNBD` should move later or disappear.
- If `collision_slack` remains near zero on successful solves, the softening is not dominating the result.
- If `collision_slack` becomes large, the issue is genuinely the open-loop collision constraint geometry rather than fallback alone.

## 20260524_124620 Result

- The second fix made open-loop complete successfully in the single-init pilot: `ego_n_steps=107`, `ego_feasible_frac=1.0`, and all solver records report `OPTIMAL`.
- Completion is valid under the tightened completion diagnostic: `completion_step=107`, `completion_ey=-0.5923`, `completion_goal_dist=7.9792`, and `completion_s_to_end=6.0`.
- The improvement is not a fully hard-constraint result yet. `collision_slack` has `max=2.1516`, `mean=0.1747`, and 16 records above `0.05` (`significant_frac=0.1495`).
- The peak `collision_slack` occurs at step 22, and the largest values are concentrated at steps 18-25. This matches the old first-failure region and strongly suggests the open-loop SOC collision geometry is still the bottleneck.
- Automatic paper-style evaluation now needs to report `solver_failure_frac`, `collision_slack_max`, `collision_slack_mean`, and `solver_slack_max` so future summaries distinguish hard feasibility from soft-constraint-assisted feasibility.

Current assessment:

- The open-loop failure cascade is fixed for `scenario_01 + ego_init_01`.
- The open-loop ablation should still be treated cautiously in reports because its success depends on non-negligible collision slack.
- The next validation step should be a small pilot over `ego_init_01` to `ego_init_05`, not a full experiment sweep yet.
