# Project Memory

## Captured Learning [Managed by learning-capture Skill]

> Before starting any task, scan this list and load relevant files to avoid repeat mistakes.
> New task requirements from the user always take precedence over captured learning.
> Evolve these entries as new tasks reveal better patterns.

- **give-way-smpc-tuning**: Before changing the UK give-way SMPC experiment, read the experiment changelog and base the next parameter change on measured past effects. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`
- **server-result-pull-method**: For this project, pull server experiment results with direct `scp -r` from `root@connect.cqa1.seetacloud.com:/root/autodl-tmp/Research-Project-IMLS/core/results/<timestamp>`; do not tar unless explicitly requested. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-give-way-smpc-tuning.md`
- **server-carla-environment**: Before any server-side CARLA/SMPC run, configure `carla_modern`, `CARLA_ROOT`, `PYTHONPATH`, `GUROBI_HOME`, `GUROBI_VERSION=110`, `GRB_LICENSE_FILE`, and verify `ca.has_conic("gurobi") == True`; do not use `ca.has_nlpsol("gurobi")` as the pass/fail check. → `/Users/bytedance/.agents/-Users-bytedance-my-Dissertation-Research-Project-IMLS/captured-learning/task-server-carla-environment.md`

## Project Records

- **give-way-smpc-experiment-changelog**: Per-run parameter deltas, measured effects, rejected directions, and next candidate changes. → `docs/architecture/Give_Way_SMPC_Experiment_Changelog.md`
- **server-carla-environment-runbook**: Copy-paste server startup commands and smoke-test procedure for CARLA/SMPC experiments. → `docs/architecture/Server_CARLA_Environment_Runbook.md`
