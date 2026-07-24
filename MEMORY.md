# Project Memory

## Captured Learning [Managed by learning-capture Skill]

> Before starting any task, scan this list and load relevant files to avoid repeat mistakes.
> New task requirements from the user always take precedence over captured learning.
> Evolve these entries as new tasks reveal better patterns.

- **give-way-smpc-tuning**: Before changing the UK give-way SMPC experiment, read the experiment changelog and base the next parameter change on measured past effects. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`
- **server-result-pull-method**: For this project, pull server experiment results with direct `scp -r` from `root@connect.cqa1.seetacloud.com:/root/autodl-tmp/Research-Project-IMLS/core/results/<timestamp>`; do not tar unless explicitly requested. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`
- **server-carla-environment**: Before any server-side CARLA/SMPC run, configure `carla_modern`, `CARLA_ROOT`, `PYTHONPATH`, `GUROBI_HOME`, `GUROBI_VERSION=110`, `GRB_LICENSE_FILE`, and verify `ca.has_conic("gurobi") == True`; do not use `ca.has_nlpsol("gurobi")` as the pass/fail check. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-server-carla-environment.md`
- **reduced-supervisor-iteration-rule**: For supervisor ablation iterations, do not keep failed versions as `v1/v2/v3` runtime modes; overwrite `reduced_intervention` with the current best candidate and rely on git/results directories for history.
- **promising-reduced-supervisor-candidate**: The 20260724 reduced early-stop candidate is considered promising by the user; preserve the direction and next optimize for var/fixed separation without sacrificing safety. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`
- **server-sync-boundary**: The user syncs code to the server; do not upload or overwrite server code unless explicitly asked for that exact operation. Pulling result files for analysis is allowed when requested. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`
- **supervisor-feedback-decision-gate**: Every tuning or experiment decision for the give-way dissertation must map to the supervisor's four comments: reduce conservative early stopping, analyze MPC infeasibility separately, sanity-check fine-tuned prediction metrics, or quantify supervisor dominance via ablation. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`
- **give-way-video-behaviour-gate**: Do not rank reduced-supervisor results by first-stop distance alone; if ego stops when target has almost cleared and remains stopped on an apparently clear path, treat it as a clear-path release problem to fix, not just a failed candidate. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`
- **post-turn-lane-keeping-non-regression**: Clear-path release must not bypass post-yield recovery/rejoin reference; turning into the correct lane and continuing straight after the intersection is a required video gate. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`

## Project Records

- **give-way-smpc-experiment-changelog**: Per-run parameter deltas, measured effects, rejected directions, and next candidate changes. → `docs/architecture/Give_Way_SMPC_Experiment_Changelog.md`
- **server-carla-environment-runbook**: Copy-paste server startup commands and smoke-test procedure for CARLA/SMPC experiments. → `docs/architecture/Server_CARLA_Environment_Runbook.md`
