#!/usr/bin/env python3
"""Materialise the formula-to-code contract for the supervisor-masking paper.

This is an audit artifact, not a second implementation of the controller.  It
binds manuscript-safe equations to the primary reference and to exact source
locations, and fails closed if the implementation landmarks disappear.
"""

from __future__ import annotations

import sys as _sys
from pathlib import Path as _Path

_MODELS_ROOT_FOR_IMPORTS = _Path(__file__).resolve().parent.parent
for _package_name in ("", "analysis", "data", "experimental", "modeling", "training", "tools"):
    _package_path = _MODELS_ROOT_FOR_IMPORTS / _package_name if _package_name else _MODELS_ROOT_FOR_IMPORTS
    if str(_package_path) not in _sys.path:
        _sys.path.insert(0, str(_package_path))

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "supervisor_method_audit_v2_probability_weighted"
PAPER = "docs/literature/01_predictive_control_uncertain_multimodal_predictions.pdf"
MPC = "core/scripts/carla/utils/mpc_utils.py"
PROBABILITY = "core/scripts/carla/utils/mode_probability_contract.py"
AGENT = "core/scripts/carla/policies/smpc_agent.py"
SCENARIO = "core/scripts/carla/scenarios/run_intersection_scenario.py"
SYNC = "core/scripts/carla/utils/carla_sync_mode.py"
LOSS = "core/scripts/models/experimental/interaction_adapter_v2.py"
GMM = "core/scripts/models/modeling/multipath_gmm_utils.py"
EVAL = "core/scripts/models/training/evaluate_multipath_model_on_dataset.py"
DEPLOY = "core/scripts/models/training/deploy_multipath_model.py"
CONFIG = "core/scripts/carla/scenarios/tuning_configs/give_way_smpc_tuning.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def loc(path: str, lines: str, landmark: str) -> dict[str, str]:
    return {"path": path, "lines": lines, "landmark": landmark}


def formula_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": "F01_multipath_mixture",
            "layer": "predictor",
            "manuscript_formula": "p(Y|X)=sum_{j=1}^J pi_j(X) p_j(Y|X)",
            "plain_language": "MultiPath assigns a probability to each anchor-defined future and predicts a continuous Gaussian correction around every anchor.",
            "paper_basis": "The primary paper models target predictions as multimodal Gaussian/LTV modes in Eq. (5) and uses MultiPath in its CARLA studies (Sec. IV-B).",
            "implementation": "The online interface supplies a target-centred raster and past state history; four-input variants additionally receive an aligned six-token ego-target interaction sequence and mask. The decoder splits the output into J logits and JxT trajectory parameters, applies softmax to logits, and adds residual means to fixed anchors.",
            "code": [loc(SCENARIO, "1806-1844", "raster, past state and optional interaction sequence construction"), loc(DEPLOY, "143-149", "online predictor input interface"), loc(GMM, "53-96", "decode_multipath_raw; probabilities=softmax_logits; means=residual+anchor")],
            "status": "implemented_extension_of_paper_input_model",
        },
        {
            "id": "F02_per_time_covariance",
            "layer": "predictor",
            "manuscript_formula": "Sigma_{j,t}=R(theta_{j,t}) diag(sigma^2_{j,t,1},sigma^2_{j,t,2}) R(theta_{j,t})^T",
            "plain_language": "Every mode and future instant has its own rotated 2-by-2 position covariance. The model does not predict covariance between different future instants.",
            "paper_basis": "Eq. (5) supplies Gaussian process noise per mode and time; the exact MultiPath output parameterisation is an implementation detail.",
            "implementation": "Raw width is J*T*5+J; each [mode,time] emits dx,dy,two log-scale values and one rotation, producing shape [...,J,T,2,2]. No cross-time covariance tensor is constructed.",
            "code": [loc(GMM, "62-68", "raw layout"), loc(GMM, "91-114", "2x2 covariance construction")],
            "status": "implemented_no_cross_time_covariance",
        },
        {
            "id": "F03_training_objective",
            "layer": "predictor",
            "manuscript_formula": "L_train=-log pi_{j*}+(1/|V|) sum_{t in V}[-log N(y_t;mu_{j*,t},Sigma_{j*,t})]+const,  j*=argmin_j ADE(anchor_j,y)",
            "plain_language": "Training first assigns each example to its nearest anchor, then learns that anchor's probability and Gaussian residual. This is a hard-assignment training loss, not the all-mode mixture likelihood used for testing.",
            "paper_basis": "MultiPath [8] is the paper's predictor; this project's fine-tuning loss is repository-specific.",
            "implementation": "Nearest anchor is selected over valid labels; cross-entropy and selected-mode Gaussian NLL are averaged over valid time steps.",
            "code": [loc(LOSS, "313-350", "masked_multipath_loss")],
            "status": "implemented_hard_assignment_train_nll",
        },
        {
            "id": "F04_heldout_mixture_nll",
            "layer": "predictor",
            "manuscript_formula": "NLL_test=-(1/T) log sum_j pi_j prod_t N(y_t;mu_{j,t},Sigma_{j,t})",
            "plain_language": "Held-out scoring rewards a model only when its complete probability-weighted mixture explains the entire future trajectory.",
            "paper_basis": "Consistent with the multimodal distribution assumed in Eq. (5); the rollout-macro evaluation is repository-specific.",
            "implementation": "Per-mode log densities are summed across time, combined once with log mode probabilities by log-sum-exp, then divided by horizon. This differs deliberately from training's nearest-anchor loss.",
            "code": [loc(EVAL, "469-505", "trajectory mixture log likelihood")],
            "status": "implemented_all_mode_heldout_nll",
        },
        {
            "id": "F05_target_ltv_gaussian",
            "layer": "smpc",
            "manuscript_formula": "o_{k+1|t,j}=T_{k|t,j}o_{k|t,j}+c_{k|t,j}+n_{k|t,j},  n_{k|t,j}~N(0,Sigma_{k|t,j})",
            "plain_language": "For each predicted manoeuvre, target motion is represented as a time-varying linear Gaussian process that the controller can propagate.",
            "paper_basis": "Primary paper Eq. (5).",
            "implementation": "The optimiser holds per-target, per-mode, per-step T, c and 2-by-2 covariance-square-root parameters.",
            "code": [loc(MPC, "586-595", "T_tv, c_tv, Sigma_tv_sqrt parameters")],
            "status": "paper_equivalent_representation",
        },
        {
            "id": "F06_policy_parameterization",
            "layer": "smpc",
            "manuscript_formula": "Delta u_{k|t,j}=h^j_{k|t}+sum_{l=0}^{k-1} M^j_{l,k|t} w_{l|t}+K^j_{k|t}(o_{k|t,j}-mu_{k|t,j})",
            "plain_language": "h is the nominal branch command, M reacts to ego-model disturbance, and K reacts to deviation of the target from its predicted mean.",
            "paper_basis": "Primary paper Eq. (11), stacked in Eqs. (21)-(23).",
            "implementation": "CasADi variables are built and returned as [h,M,K], with branch sharing before the prediction tree splits.",
            "code": [loc(MPC, "661-678", "_return_policy_class creates M,K,h"), loc(MPC, "823-823", "[h,M,K]=self.policy[i]")],
            "status": "paper_equivalent_variables",
        },
        {
            "id": "F07_chance_constraint_semantics",
            "layer": "smpc",
            "manuscript_formula": "P(c_{k,j}(x,o)>=0)>=beta_j, where c>=0 means safe",
            "plain_language": "The sign convention is defined generically: a non-negative safety margin means collision-free. The code's second-order-cone form is an inner approximation of this event.",
            "paper_basis": "Primary paper Eqs. (6d), (12)-(15): the safe event is written with a greater-than-or-equal sign.",
            "implementation": "The collision linearisation creates SOC vectors z,y and imposes ca.soc(z,y)>0. Manuscript exposition must not reverse the safe-margin sign.",
            "code": [loc(MPC, "875-893", "collision affine/SOC constraint")],
            "status": "implemented_with_generic_safe_margin_sign",
        },
        {
            "id": "F08_active_branch_objective",
            "layer": "smpc",
            "manuscript_formula": "min_{h,M,K,beta} sum_{j in J_active} pi_j J_j + J_shared",
            "plain_language": "After the policy tree branches, every complete joint MultiPath mode weights its own tracking and control cost by its normalized probability. Before branching there is one shared policy and its cost has unit weight.",
            "paper_basis": "The source formulation minimizes probability-weighted expected branch cost in Eqs. (6a) and (19).",
            "implementation": "The branch loop collects every branch_cost and the production helper forms their self.probs-weighted expectation. A single unbranched policy uses weight one; shared slack and corridor penalties are added once outside the branch expectation. Old unweighted runtime identifiers are rejected.",
            "code": [loc(PROBABILITY, "14-21", "objective semantic identifier and contract hash"), loc(MPC, "872-880", "shared penalty initialization"), loc(MPC, "906-913", "complete active-branch invariant"), loc(MPC, "1048-1077", "production expected-cost helper receives all active branch costs and probabilities")],
            "status": "paper_equivalent_probability_weighted_expected_cost",
        },
        {
            "id": "F09_adaptive_risk_budget",
            "layer": "risk",
            "manuscript_formula": "sum_j pi_j beta_j >= beta_req,  r_j approximately Phi^{-1}(beta_j)",
            "plain_language": "Mode probabilities influence how the allowed collision risk is distributed: likely modes carry more weight in the total probability-of-safety budget.",
            "paper_basis": "Primary paper Eqs. (15a), (16)-(18), with eta_j=Phi^{-1}(r_j) and a probability-weighted safety budget.",
            "implementation": "mmrisk_std is the tightening variable r-like/eta-like scalar; mmrisk_prob approximates beta through affine inverse-CDF constraints. The same normalized self.probs vector used by the objective weights the total adaptive-risk constraint.",
            "code": [loc(MPC, "836-917", "mmrisk_std/mmrisk_prob and probability-weighted total_prob"), loc(MPC, "1078-1079", "adaptive-risk satisfaction budget")],
            "status": "paper_inspired_piecewise_linear_risk_allocation",
        },
        {
            "id": "F10_receding_horizon_command",
            "layer": "smpc",
            "manuscript_formula": "u_t=pi_SMPC(x_t,o_t)=u^*_{t|t,1}",
            "plain_language": "The optimiser plans all branches but applies only the first command, then resolves after receiving the next state and prediction.",
            "paper_basis": "Primary paper Eq. (7).",
            "implementation": "The first two entries of the root h policy are extracted as u_control.",
            "code": [loc(MPC, "1088-1089", "root first action extraction")],
            "status": "paper_equivalent_receding_horizon_action",
        },
        {
            "id": "F11_dynamic_conflict_point",
            "layer": "scenario_geometry",
            "manuscript_formula": "q*=argmin_{q on ego route} distance(q, target motion line)",
            "plain_language": "The give-way conflict location follows the actual curved ego route and target travel line; it is not a fixed coordinate and it changes with route geometry.",
            "paper_basis": "Scenario-specific extension; the source paper describes an unprotected left turn but does not prescribe this Town05 geometry routine.",
            "implementation": "Every ego-route point is projected onto the target line and the closest projection is selected.",
            "code": [loc(SCENARIO, "819-857", "get_route_conflict_point_rhs")],
            "status": "implemented_dynamic_route_line_geometry",
        },
        {
            "id": "F12_time_discretization",
            "layer": "execution",
            "manuscript_formula": "Delta t_CARLA=1/20=0.05 s; N=10, Delta t_SMPC=0.2 s; horizon=2.0 s",
            "plain_language": "CARLA advances at 20 simulator frames per second, while each ten-step SMPC prediction spans two seconds at 0.2 seconds per optimisation step. Simulator frame rate is not the same quantity as SMPC horizon discretisation or measured solve frequency.",
            "paper_basis": "The primary paper reports dt=0.2 s for CARLA experiments and real-time operation; it does not license calling this repository's optimiser a 10 Hz loop without timing evidence.",
            "implementation": "Scenario JSON fixes fps=20; CarlaSyncMode uses 1/fps; the frozen give-way tuning fixes N=10 and dt=0.2.",
            "code": [loc("core/scripts/carla/scenarios/scenario_uk_give_way.json", "14", "fps=20"), loc(SYNC, "8-21", "fixed_delta_seconds=1/fps"), loc(CONFIG, "8-9", "N=10, dt=0.2")],
            "status": "implemented_two_distinct_time_scales",
        },
        {
            "id": "F13_authority_gated_operator_chain",
            "layer": "cross_layer",
            "manuscript_formula": "Y_hat=P_theta(X); u_nom=C_SMPC(x,Y_hat,beta); u_exec=A_S(x,Y_hat,u_nom), S in {enabled,monitor_only}",
            "plain_language": "The predictor supplies a distribution, risk allocation changes chance-constraint tightening, SMPC proposes a nominal command, and the complete supervisor authority mapping may change solver inputs, bypass the solve, replace the action, or alter state used next time. Monitor-only computes the same candidates but blocks them from factual actuation.",
            "paper_basis": "Prediction-to-SMPC follows the primary paper; A_S is this project's seven-channel rule-based authority layer.",
            "implementation": "Authority gating is applied to pre-solver reference/cost/bypass channels and to post-solver action/state channels. A masking estimand therefore needs aligned same-state command separation before and after the identical authority mapping; trajectory similarity alone is insufficient.",
            "code": [loc(AGENT, "3943-4245", "authority gating before solve"), loc(AGENT, "4650-4809", "bypass and upstream channel audit"), loc(AGENT, "5020-5464", "post-solver authority and executed telemetry")],
            "status": "project_specific_cross_layer_operator",
        },
    ]


def channel_rows() -> list[dict[str, Any]]:
    common = "debug_payload.supervisor_behavioural_authority.complete_candidate_channel_manifest.channels"
    return [
        {"channel": "reference_shaping", "trigger": "rule-aware yield or release-recovery profile requests a different reference", "position": "before linearisation and SMPC solve", "action": "changes feasible reference states/inputs, including speed and acceleration profile", "telemetry": f"{common}.reference_shaping plus reference.status.rule_aware_reference", "code": [loc(AGENT, "4038-4155", "yield decision and _apply_rule_aware_reference_profile"), loc(AGENT, "5220-5239", "channel manifest")]},
        {"channel": "supervisor_forced_reference_linearization", "trigger": "yield/recovery/reference guard requests reference-based linearisation", "position": "after reference shaping, before SMPC update", "action": "replaces previous-solution linearisation with a reference-horizon slice", "telemetry": f"{common}.supervisor_forced_reference_linearization plus reference.status.forced_reference_linearization", "code": [loc(AGENT, "4195-4245", "linearisation selection"), loc(AGENT, "5240-5259", "channel manifest")]},
        {"channel": "lane_entry_heading_cost", "trigger": "lane-entry heading cost enabled and ego lies inside configured goal window/error guard", "position": "before SMPC solve during cost-profile construction", "action": "adds horizon-varying heading-error weights to each active branch cost", "telemetry": f"{common}.lane_entry_heading_cost plus debug_payload.lane_entry_heading_cost", "code": [loc(AGENT, "1609-1655", "_lane_entry_heading_cost_profile"), loc(AGENT, "4864-4866", "debug payload"), loc(AGENT, "5260-5279", "channel manifest")]},
        {"channel": "rule_smpc_bypass", "trigger": "_rule_yield_smpc_bypass_reason returns a reason and authority is enabled", "position": "immediately before solver execution", "action": "skips the SMPC solve and uses the rule-yield candidate path", "telemetry": f"{common}.rule_smpc_bypass plus supervisor_behavioural_authority.rule_smpc_bypass_channel", "code": [loc(AGENT, "4650-4678", "authority-gated bypass reason"), loc(AGENT, "4765-4772", "bypass telemetry"), loc(AGENT, "5280-5295", "channel manifest")]},
        {"channel": "post_solver_action_and_desired_speed", "trigger": "rule-aware post-solver candidate differs from nominal solver command/speed", "position": "after solver or bypass candidate, before low-level control", "action": "selects nominal or rule candidate acceleration, steering and desired speed according to action-filter mode", "telemetry": f"{common}.post_solver_action_and_desired_speed plus applied.post_solver_action_filter and nominal_solver_u0/v_des", "code": [loc(AGENT, "5020-5110", "candidate and integrate_post_solver_action_filter"), loc(AGENT, "5296-5318", "channel manifest"), loc(AGENT, "5448-5463", "applied telemetry")]},
        {"channel": "release_recovery_state", "trigger": "post-action supervisor state differs from neutral free-drive state", "position": "after action arbitration, persisted across control steps", "action": "updates seen/active/recovery-count/last-acceleration state used by later release and recovery decisions", "telemetry": f"{common}.release_recovery_state plus factual_behaviour_state_after_action and shadow_behaviour_state_after_action", "code": [loc(AGENT, "5114-5199", "factual and shadow recovery state"), loc(AGENT, "5319-5343", "channel manifest") ]},
        {"channel": "next_control_history", "trigger": "executed command differs from the nominal solver command", "position": "after action arbitration, before the next SMPC update", "action": "writes executed u0 to control_prev, changing next-step rate constraints and warm-history semantics", "telemetry": f"{common}.next_control_history plus applied.control_prev_after", "code": [loc(AGENT, "5109-5113", "control_prev receives executed command"), loc(AGENT, "5200-5211", "requested/applied deltas"), loc(AGENT, "5344-5360", "channel manifest") ]},
    ]


LANDMARKS = {
    MPC: ["[h,M,K]=self.policy[i]", "active_branch_costs.append(branch_cost)", "_probability_weighted_active_branch_cost(", "total_prob+=mmr_p[j]*self.probs[i][j]", "self.opti[i].subject_to(total_prob>=self.risk_target_prob_min[i])"],
    PROBABILITY: ["OBJECTIVE_WEIGHTING_ID", "OBJECTIVE_WEIGHTING_CONTRACT_SHA256", "normalize_probability_vector", "joint_mode_probabilities"],
    GMM: ["K * T * [dx, dy, raw_std_1, raw_std_2, theta] + K logits", "covariances[..., 0, 1] = off_diagonal"],
    LOSS: ["nearest_mode = tf.argmin", "return tf.reduce_mean(class_loss + regression)"],
    EVAL: ["mode_trajectory_logpdf[mode_index] += logpdf", "trajectory_mixture_NLL_per_step"],
    DEPLOY: ["def predict_instance(", "interaction_context=None"],
    AGENT: ["reference_shaping", "supervisor_forced_reference_linearization", "lane_entry_heading_cost", "rule_smpc_bypass", "post_solver_action_and_desired_speed", "release_recovery_state", "next_control_history"],
    SCENARIO: ["def get_route_conflict_point_rhs", "return projected[int(np.argmin(distances))]"],
    SYNC: ["self.delta_seconds = 1.0 / fps", "settings.fixed_delta_seconds = self.delta_seconds"],
    CONFIG: ['"N": 10', '"dt": 0.2'],
}


def build(repo: Path) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for relative, needles in LANDMARKS.items():
        text = (repo / relative).read_text(encoding="utf-8")
        for needle in needles:
            checks[f"{relative}:{needle}"] = needle in text
    formulas = formula_rows()
    channels = channel_rows()
    checks.update({
        "paper_exists": (repo / PAPER).is_file(),
        "formula_ids_unique": len({r["id"] for r in formulas}) == len(formulas),
        "seven_channels_exact": [r["channel"] for r in channels] == [
            "reference_shaping", "supervisor_forced_reference_linearization",
            "lane_entry_heading_cost", "rule_smpc_bypass",
            "post_solver_action_and_desired_speed", "release_recovery_state",
            "next_control_history",
        ],
        "objective_probability_weighting_explicit": next(r for r in formulas if r["id"] == "F08_active_branch_objective")["status"] == "paper_equivalent_probability_weighted_expected_cost",
        "probabilities_shared_by_objective_and_risk": "same normalized self.probs vector" in next(r for r in formulas if r["id"] == "F09_adaptive_risk_budget")["implementation"],
        "timing_claim_separates_scales": "not the same quantity" in next(r for r in formulas if r["id"] == "F12_time_discretization")["plain_language"],
    })
    if not all(checks.values()):
        failed = [key for key, value in checks.items() if not value]
        raise RuntimeError(f"Method audit failed closed: {failed}")
    sources = sorted({PAPER, *LANDMARKS})
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "scope": "formula-to-code and complete seven-channel supervisor method contract",
        "source_hashes_sha256": {path: sha256(repo / path) for path in sources},
        "formula_to_code": formulas,
        "supervisor_channels": channels,
        "mandatory_corrections": {
            "objective": "Write the implemented post-branch objective as sum_j pi_j J_j plus shared penalties; the unbranched policy has unit weight.",
            "probability_use": "One normalized joint-mode probability vector weights both expected branch cost and the adaptive-risk budget.",
            "chance_sign": "Define c>=0 as safe.",
            "policy_variables": "Use h, M and K.",
            "covariance": "Use one 2x2 covariance per mode and time; do not imply cross-time covariance.",
            "nll": "Distinguish nearest-anchor training NLL from all-mode held-out trajectory-mixture NLL.",
            "conflict_geometry": "Conflict point is route-versus-target-line geometry, not a fixed coordinate or 12 m zone.",
            "timing": "CARLA is 20 Hz; N=10 and dt=0.2 s define a 2 s SMPC horizon; solve frequency requires timing evidence.",
        },
        "checks": checks,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            flat = dict(row)
            flat["code"] = "; ".join(f"{x['path']}:{x['lines']} ({x['landmark']})" for x in row["code"])
            writer.writerow({key: flat.get(key, "") for key in fields})


def materialize(repo: Path, output: Path) -> dict[str, Any]:
    payload = build(repo)
    output.mkdir(parents=True, exist_ok=True)
    (output / "formula_to_code.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(output / "formula_to_code.csv", payload["formula_to_code"], ["id", "layer", "manuscript_formula", "plain_language", "paper_basis", "implementation", "status", "code"])
    (output / "seven_channel_contract.json").write_text(json.dumps({"schema_version": SCHEMA_VERSION, "status": "pass", "supervisor_channels": payload["supervisor_channels"]}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    write_csv(output / "seven_channel_contract.csv", payload["supervisor_channels"], ["channel", "trigger", "position", "action", "telemetry", "code"])
    marker = {"schema_version": SCHEMA_VERSION, "status": "pass", "formula_count": len(payload["formula_to_code"]), "supervisor_channel_count": len(payload["supervisor_channels"]), "artifacts_sha256": {name: sha256(output / name) for name in ["formula_to_code.json", "formula_to_code.csv", "seven_channel_contract.json", "seven_channel_contract.csv"]}}
    (output / "METHOD_AUDIT_COMPLETE.json").write_text(json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return marker


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--output", type=Path, default=Path("docs/paper/generated/supervisor_masking_v2/method_audit"))
    args = parser.parse_args()
    print(json.dumps(materialize(args.repo.resolve(), (args.repo / args.output).resolve() if not args.output.is_absolute() else args.output), indent=2))


if __name__ == "__main__":
    main()
