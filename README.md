# Prediction, Risk-Aware SMPC and Supervisor Authority for CARLA Give-Way

This repository contains the experiment and analysis code for a
right-hand-traffic give-way scenario in CARLA Town05. MultiPath predictions
feed fixed or adaptive risk allocation and probability-weighted multimodal
SMPC, while matched supervisor-authority experiments measure how policy
differences reach executed vehicle behaviour.

The dissertation manuscript and submission PDF are maintained separately in
[Jiaqi-Xie-Dissertation](https://github.com/ChrisXiejq/Jiaqi-Xie-Dissertation).

## System at a glance

```text
CARLA rollouts
    -> raster + interaction-history dataset
    -> MultiPath GMM predictor and controlled adapters
    -> fixed/adaptive chance-risk allocation
    -> probability-weighted multimodal SMPC
    -> rule-based behavioural authority on/off
    -> CARLA command and analysis outputs
```

## Quick start

Create the maintained environment and run the source contract tests:

```bash
conda env create -f core/env_setup/environment.modern.yml
conda activate carla_modern
python -m unittest discover -s core/scripts/models/tests -p 'test_*.py'
```

CARLA 0.9.14, the CARLA Python API, model assets, datasets and the licensed
Gurobi solver are external dependencies. See
[REPRODUCIBILITY.md](REPRODUCIBILITY.md) for the required paths and commands.

## Main workflows

1. **Environment setup.** Configure CARLA 0.9.14, CasADi and Gurobi as
   described in [REPRODUCIBILITY.md](REPRODUCIBILITY.md).
2. **Offline predictor experiments.** Use
   `core/scripts/models/run_offline_experiment.sh` with explicit dataset, model
   and output roots.
3. **Closed-loop CARLA experiments.** Start CARLA separately, then run
   `core/scripts/carla/run_closed_loop_experiment.sh` with explicit model,
   calibration and result roots.
4. **Repository checks.** Run the unit-test command above and
   `core/scripts/models/tools/publication_repository_policy.py` before release.

## Repository map

```text
core/scripts/carla/       CARLA scenarios, policies, SMPC and formal runners
core/scripts/models/      maintained predictor entry points
  modeling/               reusable model components and contracts
  data/                   dataset preparation and validation
  training/               training, evaluation and deployment utilities
  analysis/               post-processing, statistics and plotting
  tools/                  audit, packaging and release utilities
  assets/                 small tracked model-structure assets
  experimental/           historical process files and milestones
core/env_setup/           reproducible Python environment definitions
docs/architecture/        system and server execution documentation
```

Key entry points include:

- `core/scripts/carla/run_all_scenarios.py`
- `core/scripts/carla/run_closed_loop_experiment.sh`
- `core/scripts/carla/policies/smpc_agent.py`
- `core/scripts/carla/utils/mpc_utils.py`
- `core/scripts/models/run_offline_experiment.sh`
- `core/scripts/models/train_prediction_model.py`
- `core/scripts/models/evaluate_prediction_model.py`

Files whose names retain internal day, revision or version identifiers are
grouped under the package-specific `experimental/` directories. They are kept
for reproducibility of historical runs and are not public entry points.

## Repository boundary

Raw CARLA rollouts, datasets, checkpoints, licences and generated analysis
outputs are not committed. The repository includes one public demonstration
video at `docs/paper/CARLA_video.mp4`; other videos remain ignored. The ignore
rules keep generated files under `docs/paper/` outside the source release.
Run the repository policy check before committing:

```bash
python core/scripts/models/tools/publication_repository_policy.py \
  --root . \
  --output /tmp/imls-repository-content-manifest.json
```

No repository-wide software licence is asserted because this project combines
original work with upstream research code and separately licensed tools. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [CITATION.cff](CITATION.cff).
