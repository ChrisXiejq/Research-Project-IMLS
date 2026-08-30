# Prediction, Risk-Aware SMPC and Supervisor Authority for CARLA Give-Way

This repository implements the experiment pipeline used to study a
right-hand-traffic give-way scenario in CARLA Town05: the ego vehicle turns
left across an opposing vehicle travelling straight. MultiPath predictions
feed fixed or adaptive risk allocation and probability-weighted multimodal
SMPC; matched supervisor-authority experiments measure how upstream policy
differences reach executed vehicle behaviour.

The repository contains experiment code and compact, hashed dissertation
evidence. Raw CARLA rollouts, datasets, model checkpoints, videos, Gurobi
licences and internal planning material are intentionally external.

## System at a glance

```text
CARLA rollouts
    -> raster + interaction-history dataset
    -> MultiPath GMM predictor (B1 and controlled MLP/Transformer adapters)
    -> fixed/adaptive chance-risk allocation
    -> probability-weighted multimodal SMPC
    -> rule-based behavioural authority on/off
    -> CARLA command, safety gates and paper evidence
```

The predictor emits multiple future trajectories, their probabilities and
uncertainty. The SMPC uses those probabilities as branch-cost weights and
optimises the ego control over the multimodal future. The supervisor-authority
factor determines whether the rule-aware reference, bypass and post-solver
command channels may alter the executed control.

## Evidence-backed scope

- The source collection protocol contains 200 CARLA rollouts. The corrected
  model study uses 180 rollout-disjoint runs from 45 initialisation groups and
  produces 3,526 fit, 510 selection and 506 held-out trajectory windows.
- The corrected offline matrix contains nine model cells and three fixed
  training seeds per cell (27 runs). Capacity, history information and
  architecture are varied separately.
- Future-valid masks are enforced in training, validation, checkpointing,
  early stopping, calibration and held-out evaluation. Invalid future points
  are never scored as local-coordinate origins.
- The probability-weighted assertive CARLA evidence contains 40
  supervisor-on rollouts and 20 matched supervisor-off rollouts. All 60 pass
  the frozen integrity audit.
- Corrected V4 selects an MLP history adapter rather than the historically
  deployed Transformer P*. The historical CARLA matrix therefore remains
  valid for its deployed stack but is not relabelled as corrected-V4 transfer.

See the [thesis evidence guide](docs/paper/THESIS_EVIDENCE_GUIDE.md) for result
interpretation and claim boundaries.

## Quick start

Create the source/test environment, then run the pure-Python contract suite:

```bash
conda env create -f core/env_setup/environment.modern.yml
conda activate carla_modern
python -m unittest discover -s core/scripts/models/tests -p 'test_*.py'
```

CARLA 0.9.14 and the licensed Gurobi solver are external dependencies. Follow
the [reproducibility guide](REPRODUCIBILITY.md) before running closed-loop
experiments.

## Canonical workflows

1. **Environment setup.** Configure CARLA 0.9.14, the CARLA Python API,
   CasADi and the Gurobi conic plugin using environment variables documented in
   [REPRODUCIBILITY.md](REPRODUCIBILITY.md).
2. **Corrected offline predictor study.** Build the frozen dataset/cache and
   execute `core/scripts/models/run_future_mask_v4e_pipeline.sh`. This runs the
   uniform training extension, calibration, freeze-gated held-out evaluation
   and synthesis.
3. **Probability-weighted assertive CARLA matrix.** Start CARLA separately,
   then execute `core/scripts/carla/run_probability_weighted_v2_recovery_formal.sh`
   once with supervisor authority on and once with it off. The runner freezes
   model, scenario, controller and configuration identities before outcomes.
4. **Paper figure/table regeneration.** Use
   `core/scripts/models/plot_future_mask_v4_offline.py`,
   `core/scripts/models/materialize_future_mask_v4_paper_outputs.py` and
   `core/scripts/models/analyze_weighted_smpc_joint60.py`. Generated figures
   are produced with Python/Matplotlib from audited CSV/JSON inputs.

## Repository map

```text
core/scripts/carla/       CARLA scenarios, policies, SMPC and formal runners
core/scripts/models/      dataset, MultiPath, ablations, audits and analysis
core/env_setup/           reproducible Python environment definitions
docs/architecture/        system and server execution documentation
docs/paper/generated/     compact immutable evidence and Python-made figures
```

Key entry points are `core/scripts/carla/run_all_scenarios.py`,
`core/scripts/carla/policies/smpc_agent.py`,
`core/scripts/carla/utils/mpc_utils.py` and
`core/scripts/models/evaluate_thesis_core_cached_v3.py`.

## Publication boundary

`core/results/`, `artifacts/`, logs, checkpoints and videos are ignored. Use
`core/scripts/models/materialize_publication_evidence.py` to copy only the
allowlisted evidence and record SHA-256 identities. Run
`core/scripts/models/publication_repository_policy.py` before release.

No repository-wide software licence is asserted because this project combines
original work with upstream research code and separately licensed tools. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [CITATION.cff](CITATION.cff).
