# Dissertation gap report after the SF4 authority audit

## Audit target

- Authoritative source: `../Jiaqi-Xie-Dissertation/main.tex`
- Bibliography: `../Jiaqi-Xie-Dissertation/main.bib`
- Current reading copy: 15 pages, 36 bibliography entries, all 36 cited
- Required top-level sequence: Introduction; Literature Survey; Problem Formulation; Methodology; Experimental Design; Result Analysis; Conclusion

## What already passes

1. The seven required top-level sections exist in the required order.
2. The problem formulation explicitly states right-hand traffic, ego left turn, opposing target straight, target priority, conflict-zone yielding and route completion.
3. H1--H3 already distinguish Capacity, Information and Architecture and use the correct controlled contrasts.
4. The draft reports the frozen B0/B1 foundation, V3, R3 and earlier SF4 scalar results without pooling their independent groups.
5. The main bibliography has 36 cited entries spanning prediction, calibration, SMPC, risk allocation, simulation and closed-loop evaluation.
6. Detailed metrics, complete offline cells and experiment inventories are already routed to appendices.

## Required revisions before release

| Priority | Section | Gap | Required repair | Evidence source |
| --- | --- | --- | --- | --- |
| P0 | Title and abstract | The current framing ends at predictor/risk transfer and underweights supervisory authority. The abstract also says differences are “compressed” before the new mechanism audit has licensed selective compression. | Reframe around cross-layer translation and the large common rule-supervisor authority effect; state that selective masking is not identified. Add the 40/40 versus 0/40 authority result and retain floor saturation. | `paper_release/tables/table08_sf4_authority_cells.csv`; `telemetry_audit/attenuation_claim_audit.json` |
| P0 | Result Analysis H4 | The current final sentence says the experiment “does not selectively erase” adaptive-risk advantage. A null/floor-limited interaction cannot establish absence of masking. | Replace with: the experiment identifies a common authority effect but neither establishes selective masking nor establishes its absence. | `sf4_inference.json`; `attenuation_claim_audit.json` |
| P0 | Result Analysis H4 | The physical mechanism result omits the most interpretable finite-sample outcomes and command-path manipulation. | Add authority-on 40/40 completion, 0 yield failures and 0 adverse collisions; authority-off 0/40 completion, 38/40 yield failures and 21/40 adverse collisions. Add requested/applied action fractions and the command-delta interpretation. | SF4 rollout table and telemetry audit |
| P0 | Figures | Four main figures still point to legacy integrated-story PNGs, some generated through hand-written SVG. | Replace with the four final Python/Matplotlib PDF figures: task/cross-layer system, Capacity--Information--Architecture, predictor--risk transfer and SF4 authority. | `paper_release/figures/FIGURE_MANIFEST.json` |
| P1 | Methodology | The SMPC description is too generic and does not clearly state how the implementation relates to Nair et al. | Describe the paper-derived ingredients: Frenet/kinematic ego model, multimodal Gaussian target predictions, mode-probability-weighted cost, chance constraints, tree/feedback-policy formulation, fixed versus variable risk, horizon 10 at 0.2 s, and solver. State that the present stack additionally contains a seven-channel rule supervisor and therefore does not claim a supervisor-free safety filter. | Provided 14-page SMPC paper; `mpc_utils.py`; SF4 run contract |
| P1 | Experimental Design | The authority intervention is described as if it only blocks a post-action command. | State that full behavioural authority jointly toggles seven channels, including reference/linearisation shaping, post-solver action and rule bypass, while adaptive-risk allocation remains the authorised risk-specific influence. | SF4 preregistration and manipulation audit |
| P1 | Discussion | The current limitations mention separate populations but not authority-off floor saturation, incomplete phase clocks or controller-acceptance semantics. | Add these three study-internal limitations and separate observed finite-sample safety outcomes from formal feasibility or recursive-feasibility claims. | Telemetry audit and limitations table |
| P2 | Figure 1 | The previous overview is a result collage rather than a one-glance project architecture. | Use the new exact give-way geometry plus prediction–risk–SMPC–supervisor–execution measurement diagram. | Python Figure 1 |
| P2 | Appendix | No appendix table documents solver-path accounting or the incomplete phase-event availability boundary. | Add 18,552 factual attempts, 17,822 accepted, 730 fallback/nonaccepted and 1,393 effective bypass steps; state that missing phase events are never imputed. | `solver_path_reconciliation.json`; `phase_contrast_availability.json` |

## Frozen one-sentence argument

In a controlled Town05 right-hand-traffic left-turn give-way task, task-specific adaptation and short interaction history improve bounded multimodal prediction, but capacity, attention and adaptive risk do not uniformly improve executed behaviour; complete rule-based supervisor authority is decisive for nominal yielding and completion in the tested sample, while selective masking of a predictor or risk policy is not identified.

## Reader-facing boundary

The dissertation may claim controlled cross-layer evidence for this CARLA distribution. It may not claim general safety, statistical equivalence, universal adaptive-risk superiority, attention-specific temporal understanding, recursive feasibility, or that the supervisor is the sole cause of trajectory similarity.
