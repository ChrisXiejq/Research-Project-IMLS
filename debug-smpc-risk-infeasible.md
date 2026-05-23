# Debug Session: smpc-risk-infeasible [OPEN]

## Problem
The intersection reproduction run completes, but `smpc_var_risk` and
`smpc_fixed_risk` report `ego_feasible_frac=0.0` and `ego_solve_t_mean=nan`.

## Hypotheses
1. TV prediction tensors, mode probabilities, or covariance values are malformed,
   empty, non-finite, or scaled differently from the upstream implementation.
2. Ego/TV state or reference data are in an unexpected coordinate frame, causing
   impossible initial relative geometry.
3. Risk constraints become infeasible at construction time because `t_bar`,
   joint-mode counts, risk allocation bounds, or tightening values are wrong.
4. The solver returns a useful failure status/exception, but the current run only
   records `feasible=False` and `solve_time=nan`.
5. Fallback controls keep the simulation alive for 600 steps and hide the first
   optimization failure context.

## Instrumentation Plan
- Write per-scenario debug artifacts into the existing scenario output directory.
- Capture solver setup metadata, per-step SMPC inputs, prediction validity,
  risk parameters, and first failure details.
- Keep all changes as instrumentation only; do not change optimization behavior.

## Status
- Instrumentation added.
- Syntax check passed with:
  `python3 -m py_compile core/scripts/carla/policies/smpc_agent.py core/scripts/carla/scenarios/run_intersection_scenario.py core/scripts/carla/utils/mpc_utils.py`

## Added Artifacts
- `smpc_debug_setup.json`
- `smpc_debug_steps.jsonl`
- `smpc_first_failure.json`
- `smpc_debug_latest_failure.json`

## Next Run
Run the same small matrix and share the new result directory. The first files to
inspect are `smpc_first_failure.json` under `smpc_var_risk` and
`smpc_fixed_risk`.

## Evidence From 20260523_120547
- `smpc_var_risk/smpc_first_failure.json` shows Gurobi/CasADi returned
  `return_status=OPTIMAL`, `success=1`, but post-processing raised
  `IndexError('tuple index out of range')`.
- `smpc_fixed_risk/smpc_first_failure.json` shows the same pattern:
  `return_status=OPTIMAL`, `success=1`, followed by the same `IndexError`.
- The exception happens while estimating `collision_prob`, not while solving the
  optimization problem.
- `smpc_open_loop/smpc_first_failure.json` shows a separate later failure at
  step 18 with `return_status=INF_OR_UNBD`.

## Fix Applied
- Made collision-probability post-processing robust to scalar/1-D collision
  normal vectors by using `np.atleast_1d(...)` and `z.size`.
- Guarded collision-probability estimation so a post-processing error cannot
  overwrite an already successful optimization result.

## Verification Needed
- Re-run the same small matrix and compare:
  - `smpc_var_risk` should no longer have `ego_feasible_frac=0.0`.
  - `smpc_fixed_risk` should no longer have `ego_feasible_frac=0.0`.
  - Remaining `open_loop` infeasibility, if any, should be treated as a separate
    solver/model issue.

## Evidence From 20260523_123642
- The post-processing fix worked: `smpc_var_risk` and `smpc_fixed_risk` both
  reached `ego_feasible_frac=1.0`, and neither produced `smpc_first_failure.json`.
- Both risk policies still ran to `600` steps. Debug traces show they approach
  `s≈40-41m`, slow to near zero, and never satisfy the old completion condition.
- `smpc_open_loop` still has a real solver failure at step 18 with
  `return_status=INF_OR_UNBD`.

## Fix Applied After 20260523_123642
- Added completion diagnostics (`end_s`, `s_to_end`, `goal_dist`) to
  `smpc_debug_steps.jsonl`.
- Added `smpc_completion.json` when the SMPC agent marks the goal as reached.
- Extended the completion rule with a small progress margin and an Euclidean
  goal-distance fallback to avoid terminal Frenet projection jitter causing
  600-step crawls.
- Converted collision-probability post-processing values to dense float arrays
  before scalar/vector arithmetic to remove sparse-matrix debug errors.

## Evidence From 20260523_133921
- Adding a lateral-error guard to the completion rule removed the false completion
  seen in `20260523_131925`, but `smpc_var_risk` and `smpc_fixed_risk` again ran
  to `600` steps.
- Both risk policies remained solver-feasible for all steps, so the current
  issue is not the original Gurobi infeasibility diagnosis.
- Final debug state shows large off-route deviation: `smpc_var_risk` ends around
  `ey=23.86m`, `goal_dist=24.91m`; `smpc_fixed_risk` ends around `ey=23.65m`,
  `goal_dist=24.76m`.
- The latest traces were generated before the reference-regeneration status field,
  so `reference.status` is absent in `20260523_133921`.

## Upstream-Code Difference Found
- Upstream `SMPC_MMPreds/scripts/carla/utils/mpc_utils.py` uses
  `mode = lambda m, v: int(m/N_TV)*(v==1) + (m%N_TV)*(v==0)`.
- In the published intersection experiment `N_TV=1`; therefore every joint
  hypothesis maps to target `mode 0`.
- The migrated code had changed this to mathematical base-`N_modes` joint-mode
  decoding, so `N_TV=1` used target modes `0/1/2`. That changes the collision
  constraints and can make the controller avoid a different obstacle envelope,
  matching the observed large lateral deviation.

## Fix Applied After Upstream Comparison
- Added `_mode_component(...)` so `--risk_profile upstream_code` preserves the
  upstream single-TV indexing behavior while other profiles can still use
  mathematical joint-mode decoding.
- Updated `SMPC_MMPreds` and `SMPC_MMPreds_OL` collision constraints to use this
  helper.
- Added a reference-regeneration guard in `SMPCAgent`: if `|ey| > 2m`, do not
  regenerate the reference from the already-deviated state; instead restore the
  global feasible reference and log `reference.status.skip_reason`.

## Next Verification Focus
- Re-run the same small matrix with `--risk_profile upstream_code`.
- Confirm `smpc_debug_steps.jsonl` contains `reference.status`.
- Check whether `smpc_var_risk` and `smpc_fixed_risk` avoid the previous
  `ey > 20m` drift and whether a valid `smpc_completion.json` is generated.
- Treat `smpc_open_loop` `INF_OR_UNBD` as a separate solver/model issue unless
  the indexing change also improves it.

## Evidence From 20260523_142559
- The run used the upstream single-TV mode-indexing fix: remote `mpc_utils.py`
  contains `_mode_component(...)` and both closed-loop/open-loop constraints call
  it.
- `notv` and `notv_cl` remain healthy baselines: `119/120` steps, feasible
  fraction `1.0`.
- `smpc_var_risk` and `smpc_fixed_risk` still run to `600` steps with feasible
  fraction `1.0`, and no `smpc_completion.json` is generated.
- Final off-route deviation remains large:
  - `smpc_var_risk`: `ey=23.43m`, `goal_dist=24.62m`, `s_to_end=8m`.
  - `smpc_fixed_risk`: `ey=24.31m`, `goal_dist=25.30m`, `s_to_end=7m`.
- `reference.status` shows the lateral-deviation guard triggered as designed:
  - `smpc_var_risk`: `restored_global_reference` for `512/600` steps, first at
    step `88`.
  - `smpc_fixed_risk`: `restored_global_reference` for `511/600` steps, first at
    step `89`.
- However, the controller still continues drifting after the guard starts. Around
  steps `88-110`, steering stays positive and near `0.23rad`, while `ey` grows
  from about `2m` to `6m`.

## Fix Applied After 20260523_142559
- Found that reference restoration only restored `x_ref/y_ref`; when `prev_opt`
  was true, `l_states` still came from `linearization_traj(...)`, which rolls out
  the previous already-deviating controls.
- Because the closed-loop SMPC cost is built around the linearization trajectory,
  this made the reference-restoration guard too weak: the optimizer still stayed
  near the previous deviated nominal trajectory.
- Updated `SMPCAgent` so `restored_global_reference=True` also sets
  `forced_reference_linearization=True`; in that case `l_states/l_inputs` are
  sliced from the restored global feasible reference instead of the previous
  optimal rollout.
- Next run should check for `reference.status.forced_reference_linearization`
  and whether `ey` stops growing after the first `|ey| > 2m` event.
