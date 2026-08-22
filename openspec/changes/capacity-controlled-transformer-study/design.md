## Context

The existing study trains B1 by unfreezing the final MultiPath dense head and trains B2-M/B2-D/T1/T2 as bounded residual adapters over a frozen pretrained predictor. B1 has 1,034,208 trainable parameters; the current distributional MLP and Transformer controls have 176,096 and 165,728. Ten of fifteen trainable runs select the 20-epoch budget boundary. The present comparison therefore changes capacity, input information, and architecture at once.

The explicit interaction input is a six-by-twelve ego-target sequence at times `[-1.0, -0.8, -0.6, -0.4, -0.2, 0.0]` seconds. Each token already contains relative position, ego and target speed, relative velocity, relative yaw, and separation. The current token is consequently a strong Markov-like summary; older tokens can add trends, acceleration, and response-onset evidence, but their value must be demonstrated rather than assumed. The common B0 predictor also retains its original raster and state inputs. The dissertation deadline requires a same-day thesis-core execution, so the expanded benchmark is narrowed prospectively before V3 outcomes are inspected. Groups 41--45 are explicitly treated as retrospective held-out evidence, not a new confirmatory set. See `proposal.md` and the three capability specifications for observable requirements.

## Goals / Non-Goals

**Goals:**

- Identify separately whether the existing Transformer was under-capacity, whether older explicit interaction tokens improve prediction, and whether attention extracts more value from identical history than a matched MLP.
- Preserve all earlier Day 7--Day 10, R3, SF4, and V2 artefacts as historical evidence while implementing the expanded experiment as a new V3 protocol.
- Exercise all three primary estimands on a locked 35/5/5 rollout-group split and preserve explicit retrospective-evidence wording.
- Make every expensive training and CARLA action resumable and every scientific gate machine-verifiable before held-out or closed-loop access.
- Finish the smallest matrix that still identifies Capacity, Information, Architecture, and the primary model-by-risk interaction.

**Non-Goals:**

- Claim universal Transformer superiority beyond this bounded CARLA give-way task.
- Interpret B1-versus-`P*` as a pure architecture comparison.
- Tune capacity, history horizon, learning rate, calibration, checkpoint, or deployment choice on fresh-test or closed-loop outcomes.
- Treat test-time zeroing or shuffling as the primary information ablation.
- Store large raster datasets, SavedModels, or CARLA logs in Git.
- Replace the existing supervisor-authority experiment; supervisor authority remains enabled and fixed in the new model-by-risk matrix.

## Decisions

### Decision 1: Version the work as a new V3 study

New builders, manifests, runners, and generated directories use a capacity-history/V3 namespace. Existing V2 model identifiers and frozen evidence remain byte-for-byte interpretable. Mutating the old Day 8 protocol was rejected because it would blur historical and prospective evidence and break provenance checks.

### Decision 2: Use a nine-cell thesis-core matrix

The controlled offline grid is:

| Family | Explicit interaction horizon | Capacity tiers | Role |
|---|---|---|---|
| Head/B1 | none beyond common B0 inputs | large only (1.034208M) | adaptation-allocation reference |
| MLP | 0.0, 0.4, and 1.0 s | large only (~1.034208M) | non-attentional history control |
| Transformer | 0.0, 0.4, and 1.0 s | large; plus small/medium at 1.0 s | attention and capacity study |

This produces nine cells: one large B1, three large MLP horizons, three large Transformer horizons, and two additional 1.0-second Transformer capacity tiers. Every cell modifies the complete MultiPath distribution. Existing small/medium head and non-primary capacity builders remain tested implementation infrastructure but are not executed in the thesis-core matrix.

All history variants retain the six-slot tensor shape. A frozen horizon mask exposes only `{0.0}`, `{-0.4,-0.2,0.0}`, or all six tokens; excluded slots are zero-filled before the encoder. Each horizon is trained independently, but all variants use only samples with a complete valid six-token history. This keeps labels, base inputs, tensor shape, eligibility, and parameter-count accounting fixed. With one valid token, the Transformer cannot perform cross-time mixing and is the negative control for temporal attention.

A deterministic parameter-count search is run for every executed cell before performance is inspected. Large MLP and Transformer counts at each matched horizon and both large adapters versus full B1 must be within five percent of target. The small/medium/large Transformer sequence at 1.0 seconds supplies the capacity trend.

### Decision 3: Define three estimands instead of one model ranking

Let `L(e,h,c)` be rollout-macro NLL for encoder `e`, explicit history horizon `h`, and capacity `c`, where lower is better.

- **Capacity:** `G_cap = L(T,1.0s,small) - L(T,1.0s,large)`. A positive effect, supported by the full small-medium-large trend, indicates that the earlier Transformer was capacity-limited at full history.
- **Information:** `G_hist(e,c) = L(e,0.0s,c) - L(e,1.0s,c)`. A positive effect means older interaction tokens add information for that encoder beyond the current interaction state and common B0 inputs. The 0.4-second horizon tests monotonicity or early saturation.
- **Architecture:** direct matched effects are `A(h,c) = L(MLP,h,c) - L(T,h,c)`. The temporal-attention estimand is `G_attn(c) = G_hist(T,c) - G_hist(MLP,c)`. A positive full-history direct effect plus positive `G_attn` supports the claim that attention extracts historical information better. A similar Transformer advantage at 0.0 and 1.0 seconds supports only a generic encoder-family advantage.

The primary versions use the large tier. Capacity at non-primary horizons and small/medium MLP robustness are omitted because they do not identify an additional primary estimand. Head-versus-encoder contrasts estimate where task-specific capacity is allocated and remain secondary complete-configuration evidence.

### Decision 4: Freeze one common optimisation setting

The nine cells are each trained for seeds 11, 23, and 37 at the prospectively fixed common learning rate `1e-4`, for 27 planned runs. A common learning rate removes 162 optimisation-selection runs and prevents family-specific tuning from confounding the matched comparison. All three seeds proceed to calibration and held-out evaluation; the seed closest to the groups-36--40 median is frozen only for deployment.

The maximum remains 80 epochs with patience 12. Boundary selection is reported as a limitation rather than triggering a post-outcome 120-epoch expansion. The frozen optimiser is AdamW with weight decay `1e-5` and global gradient clipping at norm 10; both encoders use dropout 0.1. Checkpointing and early stopping use exact groups-36--40 rollout-macro mixture NLL. Formal completion retains finite-loss/weight, group/cell support, disjointness, unique-key, finite-input, hash-provenance, and training-health gates.

### Decision 5: Use a locked retrospective 35/5/5 split

The sealed Day7 data are deterministically repartitioned by complete initialisation groups: 1--35 for fitting, 36--40 for checkpoint selection and calibration, and 41--45 for one-pass held-out evaluation. Every group retains all four policy/style cells. Group 41--45 outcomes informed earlier work, so the resulting evidence is explicitly retrospective and claims are bounded accordingly. New groups 51--80 and the trigger-rich challenge collection are deferred beyond the same-day thesis-core scope.

### Decision 6: Cache the frozen backbone exactly and shard across six GPUs

The frozen B0 raw output and final-head input feature are materialised once per sample with example IDs and data/model/source hashes. Large B1 trains only its final Dense layer from cached penultimate features; sequence adapters train from cached B0 output plus the unchanged sequence/mask. Each trained lightweight component is reassembled with B0 and must match the cached path numerically on a fixed audit set before completion. Six workers receive disjoint deterministic run shards through `CUDA_VISIBLE_DEVICES`; a run belongs to exactly one shard and resume skips only hash-valid completions. Data-fraction experiments are removed from the thesis-core scope.

### Decision 7: Make trained horizon the primary information ablation

The 0.0-, 0.4-, and 1.0-second models are independently optimised from the same zero-residual initial function. This measures achievable predictive value under a controlled information set. Frozen-model zeroing and deterministic shuffling from earlier work may be retained as appendix sensitivity checks, but they are not used to claim that history is useful or that attention is superior. A last-token perturbation is unnecessary because the separately trained 0.0-second condition is the cleaner current-state baseline.

### Decision 8: Add interaction-specific metrics and grouped inference

Every retained seed is calibrated on validation only with temperature and covariance scale. Reports include raw and calibrated NLL, probability calibration, one/two/three-sigma coverage and error, top-1 ADE/FDE, oracle metrics, parameter counts, GPU training time, and warmed batch-one latency.

Mechanism reporting adds target speed-profile RMSE, predicted deceleration/response-onset timing error where defined, conflict-zone entry-time error, and predicted probability mass in the conflict zone. Results are stratified into assertive, reactive pre-response, response-onset, and response-active windows. The onset band and all geometric thresholds are frozen in the protocol before model outputs are opened.

Metrics are first macro-averaged by rollout and paired by independent initialisation group. Cluster intervals resample initialisation groups; model-seed variability is reported separately and in a crossed sensitivity analysis. The frozen multiplicity procedure covers the primary capacity, information, and temporal-architecture estimands. Intermediate-horizon, geometry, calibration, response-stratum, B1 allocation, and latency results are supporting or secondary.

### Decision 9: Deploy B1 and the validation-selected best sequence model in a disjoint risk matrix

The deployed sequence model `P*` is selected from the six sequence cells by median groups-36--40 rollout-macro NLL, with deterministic ties resolved by lower trainable parameter count, lower warmed latency, and lexical model identifier. Its family, capacity, history horizon, representative seed, and calibration are frozen before groups 41--45 or closed-loop outcomes are opened. `P*` is compared with large B1 under fixed-medium and adaptive risk, two target styles, and groups 81--90, totalling 80 rollouts. Fixed-aggressive and fixed-conservative response-curve branches are deferred.

For outcome `Y`, the primary interaction is:

`[(Y_P*,adaptive - Y_B1,adaptive) - (Y_P*,fixed-medium - Y_B1,fixed-medium)]`.

Completion and minimum footprint separation are co-primary closed-loop outcomes. Solver, fallback, and supervisor pathways explain translation but do not replace physical outcomes. All formal cells retain supervisor authority; SF4 remains the authority ablation.

### Decision 10: Predeclare result-independent interpretation branches

The evidence generator maps results to bounded statements before fresh-test access:

| Pattern | Licensed interpretation |
|---|---|
| Full-history Transformer improves from small to large | the earlier Transformer was capacity-limited in this task |
| Both encoders improve from 0.0 to 1.0 s | older explicit interaction tokens are useful, independent of whether attention is uniquely useful |
| Neither encoder improves with history | the current interaction state and common B0 inputs contain the usable information under this protocol |
| Transformer beats MLP at 1.0 s and has larger history gain | attention extracts more value from explicit history |
| Transformer beats MLP equally at 0.0 and 1.0 s | a generic encoder-family effect is present, not evidence for temporal attention |
| MLP matches or beats Transformer at matched history/capacity | attention has no demonstrated advantage in this task |
| B1 beats matched history encoders | head adaptation is the stronger complete allocation, without proving that history or attention is intrinsically useless |

Null, adverse, and mixed results remain in the evidence ledger. Thesis integration is gated until required artefacts exist; methods and planned tables may be generated earlier without numerical claims.

## Risks / Trade-offs

- **[The current token already contains speed and relative velocity, so older history may be redundant]** → Treat a null history effect as a substantive result about this task representation, and use response-onset strata to test the most plausible region of benefit.
- **[The held-out set is retrospective and contains only five independent groups]** → Label it explicitly, report cluster uncertainty and seed variability, and avoid new-confirmatory or universal wording.
- **[Capacity matching does not equalise every operation or optimisation geometry]** → Match trainable counts, foundation, history, scope, training, and evaluation; report depth, width, FLOPs, and latency; restrict causal wording to the bounded encoder-family contrast.
- **[A common learning rate may not be optimal for every family]** → Treat it as a fairness control, report the fixed setting, and avoid best-achievable-performance wording.
- **[Cached features could drift from the full model]** → Hash every dependency, reconstruct the deployable model, and hard-fail unless cached/full predictions pass numerical parity.
- **[Fresh CARLA data are expensive and may fail mid-run]** → Use immutable manifests, per-cell completion markers, hash checks, and missing-cell-only resume.
- **[Large Transformers may violate deployment latency]** → Measure warmed batch-one latency before CARLA, block incompatible deployment, and report accuracy-latency Pareto results.
- **[Multiple horizons, seeds, and hyperparameters create many outputs]** → Use deterministic identifiers, manifest-driven orchestration, completion gates, and generated evidence indexes.

## Migration Plan

1. Revise and validate the V3 protocol to the nine-cell, 27-run thesis-core matrix and locked 35/5/5 split.
2. Implement hash-bound frozen-backbone extraction, cached training, full-model reconstruction/parity, and six-way disjoint resume.
3. Execute the 27 runs, freeze calibration/selection on groups 36--40, and evaluate groups 41--45 exactly once.
4. Freeze B1 and validation-selected `P*`, then execute the 80-rollout fixed-medium/adaptive closed-loop matrix on groups 81--90.
5. Generate interaction analysis and thesis-facing evidence with explicit retrospective-evidence limitations.

Rollback consists of abandoning the V3 generated namespace and this OpenSpec change; no historical model, dataset, R3, SF4, or thesis evidence is overwritten.
