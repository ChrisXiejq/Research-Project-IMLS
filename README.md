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
   `core/scripts/models/run_future_mask_v4e_pipeline.sh` with explicit dataset,
   model and output roots.
3. **Closed-loop CARLA experiments.** Start CARLA separately, then run
   `core/scripts/carla/run_probability_weighted_v2_recovery_formal.sh` with
   explicit model, calibration and result roots.
4. **Repository checks.** Run the unit-test command above and
   `core/scripts/models/publication_repository_policy.py` before release.

## Repository map

```text
core/scripts/carla/       CARLA scenarios, policies, SMPC and formal runners
core/scripts/models/      dataset, model, audit and analysis utilities
core/env_setup/           reproducible Python environment definitions
core/results_template/    example post-processing utilities and templates
docs/architecture/        system and server execution documentation
```

Key entry points include:

- `core/scripts/carla/run_all_scenarios.py`
- `core/scripts/carla/policies/smpc_agent.py`
- `core/scripts/carla/utils/mpc_utils.py`
- `core/scripts/models/evaluate_thesis_core_cached_v3.py`

## Repository boundary

Raw CARLA rollouts, datasets, checkpoints, videos, licences and generated
analysis outputs are not committed. The ignore rules keep these local files,
including anything generated under `docs/paper/`, outside the source release.
Run the repository policy check before committing:

```bash
python core/scripts/models/publication_repository_policy.py \
  --root . \
  --output /tmp/imls-repository-content-manifest.json
```

No repository-wide software licence is asserted because this project combines
original work with upstream research code and separately licensed tools. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [CITATION.cff](CITATION.cff).
