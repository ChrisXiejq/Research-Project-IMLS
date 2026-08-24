# Implicit SMPC Safety-Filter Experiment

## Research question

This experiment isolates whether the ego vehicle's stochastic MPC can produce
the complete give-way sequence without a rule-based supervisor:

1. proceed while the priority target is still outside the interaction region;
2. slow down and let the target clear the conflict zone first;
3. resume the route and complete the turn after the target has cleared.

The treatment is deliberately narrow. It does not claim that every feasible
SMPC controller is a formal safety filter, or that one CARLA rollout proves a
general safety guarantee.

## Controller boundary

The ego's factual control is produced by `SMPC_MMPreds` in variable-risk mode.
It retains the paper implementation's multimodal target hypotheses, Gaussian
uncertainty, chance-constrained collision avoidance, feedback-policy
parameterisation, vehicle dynamics/input limits and nominal route/speed
tracking objective.

The experiment contract rejects the run during setup unless all of the
following hold:

- `smpc_config == "var_risk"` and `risk_profile == "paper_eps_002"`;
- the horizon covers at least 4 s (the frozen configuration uses 25 x 0.2 s);
- rule yield state machine, observed caution, emergency brake, creep and
  recovery are disabled;
- rule reference shaping, solver bypass, adaptive rule-risk mapping and
  post-solver action authority are disabled;
- traffic-light control overrides are disabled;
- the terminal predicted state is included in collision constraints.

The ordinary solver-failure fallback remains available to prevent an
uncontrolled runtime failure, but **any solver fallback invalidates the
experiment**. The analysis threshold is therefore exactly zero solver
failures, not 5%.

## Ego-independent target treatment

The priority target uses `StraightLineAgent`. Its control law reads only the
target's own pose, velocity, fixed start-to-goal line and nominal speed; it does
not use the `pred_dict` ego state.

The target predictor is also ego-independent. At every planning step it builds
three Gaussian straight-motion modes from the measured target pose and
velocity. The modes differ in longitudinal speed and have time-growing
longitudinal/lateral covariance. This avoids an interaction model silently
predicting that the target will cooperate with the ego.

These covariances are a declared robustness envelope, not a newly calibrated
probabilistic model. A later statistical claim about coverage must fit and
validate them on held-out target trajectories.

## Why the horizon changed

The previous `N=10`, `dt=0.2` configuration exposed only 2 s of target motion.
At 9 m/s that can reveal the priority target too late for a smooth implicit
yield. The dedicated experiment uses a 5 s horizon. It also closes the old
horizon-end gap by applying the collision chance constraint at the terminal
state `t=N`, rather than only at `t=1,...,N-1`.

## Running the experiment

From `core/scripts/carla`, with CARLA and Gurobi configured:

```bash
./run_implicit_smpc_safety_filter.sh
```

The default is the difficult `ego_init_01` pilot. Run the frozen 50-init matrix
with:

```bash
INIT_GLOB='paper_intersection_50/ego_init_*.json' \
  ./run_implicit_smpc_safety_filter.sh
```

The wrapper fixes the only admissible policy/risk/target treatment:
`smpc_var_risk`, `paper_eps_002`, and `assertive_constant_speed`.

## Acceptance evidence

Each subrun writes `implicit_safety_filter_contract.json`. Its fixed route
conflict geometry is evaluation metadata only and is explicitly excluded from
controller inputs.

The wrapper runs two independent post-rollout gates:

- `postcarla_trajectory_gate.py` replays oriented vehicle footprints and checks
  collision, give-way order, completion and solver integrity;
- `analyze_implicit_smpc_safety_filter.py` evaluates the three requested phases
  using the fixed route geometry.

The three-phase report passes only when the ego makes measurable progress
before target arrival, loses sufficient speed and enters the conflict zone
after target clearance, then regains speed/progress and completes. It also
requires no native CARLA collision, no offline footprint collision, a straight
target trajectory, a valid no-supervisor contract and zero solver failures.

Primary reference: Nair et al., *Predictive Control for Autonomous Driving
with Uncertain, Multi-modal Predictions*, arXiv:2310.20561 (2023). The local
implementation reuses and extends the authors' MIT-licensed
`shn66/SMPC_MMPreds` codebase; the terminal-horizon correction, exogenous
straight-target treatment, no-supervisor contract and three-phase evaluation
are project-specific additions and must be identified as such in the thesis.
