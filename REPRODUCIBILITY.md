# Reproducibility

This document separates lightweight source verification from full CARLA/GPU
reproduction. Commands are written with portable environment variables; no
private server path is required by the documentation.

## 1. Required external paths

```bash
export IMLS_REPO=/path/to/Research-Project-IMLS
export CARLA_ROOT=/path/to/CARLA_0.9.14
export PREDICTION_DATASET_ROOT=/path/to/dataset_35_5_5
export MULTIPATH_BASE_MODEL=/path/to/l5kit_multipath_10
export EXPERIMENT_RESULTS_ROOT=/path/to/persistent/results
```

For the formal CARLA solver path also define:

```bash
export GUROBI_LOADER=/path/to/load_gurobi.sh
export PYTHON_BIN=/path/to/carla_modern/bin/python
```

CARLA assets, pretrained/fine-tuned models and Gurobi licence files are not
bundled. The repository does include `core/scripts/models/l5kit_clusters_16.npy`
because these anchors are a small, required model-structure input.

## 2. Python environment

The maintained environment is
[core/env_setup/environment.modern.yml](core/env_setup/environment.modern.yml).
Create it with:

```bash
cd "$IMLS_REPO"
conda env create -f core/env_setup/environment.modern.yml
conda activate carla_modern
```

Use the Python API shipped with CARLA 0.9.14, rather than a mismatched PyPI
CARLA package:

```bash
export PYTHONPATH="$CARLA_ROOT/PythonAPI/carla:$CARLA_ROOT/PythonAPI/carla/agents:${PYTHONPATH:-}"
```

Gurobi is optional for documentation, audit and most source tests. It is
required for the formal `ca.Opti("conic")` solver path. After loading the
locally licensed installation, verify:

```bash
"$PYTHON_BIN" -c "import casadi as ca; print(ca.__version__); print(ca.has_conic('gurobi'))"
```

The second line must be `True`. A missing Gurobi plugin is an environment
failure and must not be counted as a scientific rollout failure.

## 3. Source and contract tests

The local writing environment can run tests through the standard library:

```bash
cd "$IMLS_REPO"
python -m unittest discover -s core/scripts/models/tests -p 'test_*.py'
```

The licensed production solver smoke is intentionally skipped unless its
environment gate is enabled. Before any release, also run:

```bash
python core/scripts/models/publication_repository_policy.py \
  --root . \
  --output docs/paper/REPOSITORY_CONTENT_MANIFEST.json
```

## 4. Dataset and representation

The collection protocol creates four scenario cells per initialisation group:
two target-interaction settings crossed with fixed/adaptive collection policy.
Two hundred CARLA source rollouts are collected. The corrected frozen study
uses groups 1--35 for fitting, 36--40 for selection/calibration and 41--45 for
held-out evaluation, preserving rollout-disjoint splits.

Each supervised window contains:

- a MultiPath raster representation around the target vehicle;
- a six-token, 12-feature ego--target interaction history;
- ten future target positions at 0.2 s spacing (2 s horizon);
- a future-valid mask for windows truncated near rollout termination.

The corrected cache contains 3,526 fit, 510 selection and 506 held-out windows.
Mask validity is fail-closed throughout validation, checkpoint selection,
calibration and held-out metrics.

## 5. Corrected offline predictor pipeline

The full run requires the frozen V3 protocol/dataset root, feature cache and a
pre-held-out extension protocol. The public entry point accepts them as four
arguments:

```bash
export PYTHON_BIN=/path/to/training/python
export MULTIPATH_BASE_MODEL=/path/to/l5kit_multipath_10
export MULTIPATH_ANCHORS="$IMLS_REPO/core/scripts/models/l5kit_clusters_16.npy"

bash core/scripts/models/run_future_mask_v4e_pipeline.sh \
  "$EXPERIMENT_RESULTS_ROOT/capacity_history_future_mask_v4e_120" \
  "$EXPERIMENT_RESULTS_ROOT/capacity_history_thesis_core_v3" \
  "$EXPERIMENT_RESULTS_ROOT/capacity_history_future_mask_v4/cache" \
  "$EXPERIMENT_RESULTS_ROOT/capacity_history_future_mask_v4e_120/protocol/EXTENSION_PROTOCOL.json"
```

The pipeline trains all 27 cells under the same amended budget, audits every
epoch/checkpoint, fits calibration only on groups 36--40, freezes selection,
then opens groups 41--45 once. Raw outputs remain under
`$EXPERIMENT_RESULTS_ROOT`; compact evidence is imported with
`core/scripts/models/materialize_publication_evidence.py`.

## 6. Probability-weighted CARLA experiment

Start CARLA 0.9.14 in one terminal:

```bash
cd "$CARLA_ROOT"
./CarlaUE4.sh -RenderOffScreen -quality-level=Low
```

Set model/calibration roots produced by the offline pipeline, then run the
assertive matrix:

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

The on arm contains B1/P* × fixed-medium/adaptive × ten paired initialisation
groups (40 rollouts). The off arm uses the same factorial over five paired
groups (20 rollouts). Target behaviour is assertive constant speed and does not
use ego state. Camera visualisation is disabled during formal timing runs.

## 7. Regenerate tables and figures

Offline figures:

```bash
python core/scripts/models/plot_future_mask_v4_offline.py \
  --impact-audit docs/paper/generated/future_mask_v4e_120/audits/HISTORICAL_CHECKPOINT_IMPACT_AUDIT.json \
  --offline-synthesis docs/paper/generated/future_mask_v4e_120/postprocess/offline_synthesis.json \
  --full-horizon-sensitivity docs/paper/generated/future_mask_v4e_120/audits/FULL_HORIZON_SENSITIVITY.json \
  --selection-freeze docs/paper/generated/future_mask_v4e_120/postprocess/selection_freeze.json \
  --output-dir /tmp/imls-offline-figures
```

Closed-loop joint analysis requires the external raw joint60 result root:

```bash
python core/scripts/models/analyze_weighted_smpc_joint60.py \
  --input-root "$EXPERIMENT_RESULTS_ROOT/weighted_smpc_v2_recovery" \
  --output-dir /tmp/imls-joint60-analysis
```

All publication plots are generated by Python/Matplotlib. Numerical source
files under `docs/paper/generated/` are immutable: fix a generator and rebuild,
never hand-edit a reported result.

## 8. Evidence and claim boundary

The corrected offline evidence is under
`docs/paper/generated/future_mask_v4e_120/`. The weighted closed-loop analysis
and joint60 integrity evidence are under
`docs/paper/generated/weighted_smpc_v2_recovery/`. Historical unmasked V3 and
unweighted-controller outputs may support provenance only; they are not final
corrected estimates.
