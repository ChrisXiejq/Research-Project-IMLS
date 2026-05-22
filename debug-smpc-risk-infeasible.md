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
