# Reproducibility

This guide separates lightweight source verification from full CARLA, GPU and
licensed-solver reproduction. Generated results and manuscript materials are
not part of this source repository.

## 1. External paths

Define the paths used by the workflows:

```bash
export IMLS_REPO=/path/to/Research-Project-IMLS
export CARLA_ROOT=/path/to/CARLA_0.9.14
export PREDICTION_DATASET_ROOT=/path/to/prediction-dataset
export MULTIPATH_BASE_MODEL=/path/to/l5kit_multipath_10
export EXPERIMENT_RESULTS_ROOT=/path/to/persistent/results
export GUROBI_LOADER=/path/to/load_gurobi.sh
export PYTHON_BIN=/path/to/carla_modern/bin/python
```

CARLA assets, datasets, model checkpoints and Gurobi licence files are external
and must not be committed. The small anchor file required by the model
structure is included at `core/scripts/models/l5kit_clusters_16.npy`.

## 2. Python environment

Create and activate the maintained environment:

```bash
cd "$IMLS_REPO"
conda env create -f core/env_setup/environment.modern.yml
conda activate carla_modern
```

Use the Python API distributed with CARLA 0.9.14:

```bash
export PYTHONPATH="$CARLA_ROOT/PythonAPI/carla:$CARLA_ROOT/PythonAPI/carla/agents:${PYTHONPATH:-}"
```

For the formal solver path, load the local Gurobi installation and verify the
CasADi plugin:

```bash
"$PYTHON_BIN" -c "import casadi as ca; print(ca.__version__); print(ca.has_conic('gurobi'))"
```

The final line must be `True`. A missing solver plugin is an environment error,
not a scientific rollout failure.

## 3. Source checks

Run the contract suite from the repository root:

```bash
python -m unittest discover -s core/scripts/models/tests -p 'test_*.py'
```

Check the tracked release boundary without writing into the repository:

```bash
python core/scripts/models/publication_repository_policy.py \
  --root . \
  --output /tmp/imls-repository-content-manifest.json
```

The licensed production-solver smoke test is skipped unless its environment
gate is explicitly enabled.

## 4. Offline predictor pipeline

The offline workflow requires an external dataset root, feature cache and
extension protocol:

```bash
export MULTIPATH_ANCHORS="$IMLS_REPO/core/scripts/models/l5kit_clusters_16.npy"

bash core/scripts/models/run_future_mask_v4e_pipeline.sh \
  "$EXPERIMENT_RESULTS_ROOT/capacity_history_future_mask_v4e_120" \
  "$EXPERIMENT_RESULTS_ROOT/capacity_history_thesis_core_v3" \
  "$EXPERIMENT_RESULTS_ROOT/capacity_history_future_mask_v4/cache" \
  "$EXPERIMENT_RESULTS_ROOT/capacity_history_future_mask_v4e_120/protocol/EXTENSION_PROTOCOL.json"
```

All raw outputs remain below `EXPERIMENT_RESULTS_ROOT`.

## 5. Closed-loop CARLA workflow

Start CARLA in a separate terminal:

```bash
cd "$CARLA_ROOT"
./CarlaUE4.sh -RenderOffScreen -quality-level=Low
```

Then provide the trained-model and calibration roots and run the formal matrix:

```bash
export REPO_DIR="$IMLS_REPO"
export TRAINING_ROOT="$EXPERIMENT_RESULTS_ROOT/capacity_history_thesis_core_v3/training"
export CALIBRATION_ROOT="$EXPERIMENT_RESULTS_ROOT/capacity_history_thesis_core_v3/postprocess/calibration"

SUPERVISOR_AUTHORITY_MODE=on \
RESULTS_ROOT="$EXPERIMENT_RESULTS_ROOT/weighted_smpc_v2_recovery/formal_supervisor_on" \
bash core/scripts/carla/run_probability_weighted_v2_recovery_formal.sh

SUPERVISOR_AUTHORITY_MODE=off \
RESULTS_ROOT="$EXPERIMENT_RESULTS_ROOT/weighted_smpc_v2_recovery/formal_supervisor_off" \
bash core/scripts/carla/run_probability_weighted_v2_recovery_formal.sh
```

Keep generated outputs outside Git. If a script defaults to `docs/paper/`, that
directory is intentionally ignored and must not be added to the code release.
