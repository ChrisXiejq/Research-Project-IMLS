# Third-party notices

This research repository integrates or interoperates with independently
licensed software, models and research formulations. No top-level licence is
asserted for the combined repository. Users are responsible for reviewing the
terms that apply to every external component and asset they obtain.

## CARLA

Closed-loop experiments use [CARLA 0.9.14](https://github.com/carla-simulator/carla).
CARLA simulator binaries, maps and Python API distributions are not bundled.
Use the licence and release terms supplied by the CARLA project.

## L5Kit and MultiPath assets

The prediction pipeline builds on the MultiPath implementation and data
interfaces provided through [L5Kit](https://github.com/woven-by-toyota/l5kit).
Pretrained and fine-tuned SavedModel/checkpoint assets are external and are not
redistributed here. Obtain them under their upstream terms.

## CasADi

The SMPC implementation uses [CasADi](https://github.com/casadi/casadi) for
symbolic optimisation and conic solver integration. CasADi remains governed by
its upstream licence.

## Gurobi

The formal solver path uses the commercial
[Gurobi Optimizer](https://www.gurobi.com/). No installer, shared library,
licence file or licence key is included. Each user must install and license
Gurobi independently.

## Multimodal SMPC formulation and upstream research code

The controller is adapted from the multimodal stochastic MPC formulation in
S. H. Nair et al., “Predictive Control for Autonomous Driving with Uncertain,
Multimodal Predictions,” *IEEE Transactions on Control Systems Technology*,
33(4), 1178–1192, 2025,
[doi:10.1109/TCST.2024.3451370](https://doi.org/10.1109/TCST.2024.3451370),
and the associated [SMPC_MMPreds research repository](https://github.com/shn66/SMPC_MMPreds).
The implementation in this repository includes CARLA 0.9.14 integration,
probability-weighted branch costs, risk-allocation variants and
supervisor-authority instrumentation. These changes do not relicense upstream
material; consult the source repository and publication before reuse.

## Data and generated outputs

Raw simulator data, generated experiment outputs and model weights are not
distributed. External datasets, simulator assets and pretrained models remain
subject to their respective licences and terms.
