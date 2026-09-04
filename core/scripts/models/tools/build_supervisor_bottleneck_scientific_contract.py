#!/usr/bin/env python3
"""Build the frozen scientific contract for the supervisor-bottleneck thesis."""

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
from typing import Any, Iterable


SCHEMA_VERSION = "supervisor_bottleneck_scientific_contract_v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _load_json(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _load_csv(root: Path, relative: str) -> list[dict[str, str]]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _source(root: Path, relative: str, locator: str = "/") -> dict[str, str]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": relative, "sha256": _sha256(path), "locator": locator}


def _require_marker(data: dict[str, Any], *, expected_rollouts: int | None = None) -> None:
    if data.get("status") != "pass" or data.get("formal_evidence") is not True:
        raise ValueError(f"Formal completion marker is not pass: {data.get('schema_version')}")
    if expected_rollouts is not None and data.get("observed_rollouts") != expected_rollouts:
        raise ValueError(
            f"Observed rollout mismatch for {data.get('schema_version')}: "
            f"{data.get('observed_rollouts')} != {expected_rollouts}"
        )


def _row_by(rows: Iterable[dict[str, str]], **criteria: str) -> dict[str, str]:
    matches = [row for row in rows if all(row.get(key) == value for key, value in criteria.items())]
    if len(matches) != 1:
        raise ValueError(f"Expected one row for {criteria}, found {len(matches)}")
    return matches[0]


def _effect(row: dict[str, str]) -> dict[str, Any]:
    def number(key: str) -> float | None:
        value = row.get(key, "")
        return None if value == "" else float(value)

    return {
        "contrast_id": row.get("contrast_id"),
        "metric": row.get("metric"),
        "effect": number("effect"),
        "ci95": [number("ci95_low"), number("ci95_high")],
        "holm_adjusted_p": number("holm_adjusted_p"),
        "independent_groups": int(row["independent_groups"]),
        "evidence_status": row["evidence_status"],
    }


def _build_blocks(root: Path) -> list[dict[str, Any]]:
    f1_manifest_path = (
        "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
        "FINETUNE_AUDIT_MANIFEST.json"
    )
    f1_contract_path = (
        "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
        "frozen_test_population_contract.json"
    )
    f1 = _load_json(root, f1_manifest_path)
    if f1.get("status") != "pass" or f1.get("independent_paired_init_groups") != 5:
        raise ValueError("F1 fine-tune audit is not complete")

    v3_training_path = "docs/paper/generated/capacity_history_v3/results/postprocess/training_audit.json"
    v3_selection_path = "docs/paper/generated/capacity_history_v3/results/postprocess/selection_freeze.json"
    v3_training = _load_json(root, v3_training_path)
    v3_selection = _load_json(root, v3_selection_path)
    if v3_training.get("status") != "pass" or v3_training.get("valid_runs") != 27:
        raise ValueError("V3 offline training is incomplete")
    if v3_selection.get("status") != "pass":
        raise ValueError("V3 selection freeze is incomplete")

    r3_root = (
        "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/"
        "server_runs/r3_corrected_formal_v3"
    )
    r3_complete_path = f"{r3_root}/R3_COMPLETE.json"
    r3_contract_path = f"{r3_root}/r3_run_contract.json"
    r3_complete = _load_json(root, r3_complete_path)
    r3_contract = _load_json(root, r3_contract_path)
    _require_marker(r3_complete, expected_rollouts=80)

    v3_closed_complete_path = (
        "docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_COMPLETE.json"
    )
    v3_closed_manifest_path = (
        "docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_MANIFEST.json"
    )
    v3_closed = _load_json(root, v3_closed_complete_path)
    v3_manifest = _load_json(root, v3_closed_manifest_path)
    _require_marker(v3_closed, expected_rollouts=80)

    sf4_root = "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results"
    sf4_complete_path = f"{sf4_root}/SF4_COMPLETE.json"
    sf4_contract_path = f"{sf4_root}/sf4_supervisor_behavioural_authority_run_contract.json"
    sf4_complete = _load_json(root, sf4_complete_path)
    sf4_contract = _load_json(root, sf4_contract_path)
    _require_marker(sf4_complete, expected_rollouts=80)

    blocks = [
        {
            "block_id": "F1_foundation_adaptation",
            "scientific_role": "supporting_task_foundation",
            "population": "Town05 give-way prediction groups 46--50",
            "independent_unit": "held-out ego initialisation group",
            "independent_groups": [46, 47, 48, 49, 50],
            "sample_structure": {"rollouts": 20, "overlapping_full_horizon_windows": 315},
            "treatments": ["B0 pretrained MultiPath", "B1 task-adapted final head"],
            "primary_metrics": ["rollout-macro NLL", "top-1 ADE", "top-1 FDE"],
            "sources": [_source(root, f1_manifest_path), _source(root, f1_contract_path)],
        },
        {
            "block_id": "F4_capacity_information_architecture_v3",
            "scientific_role": "headline_offline_factor_decomposition",
            "population": "Town05 task-trained prediction groups 1--45",
            "independent_unit": "ego initialisation group",
            "independent_groups": {
                "fit": list(range(1, 36)),
                "selection_calibration": list(range(36, 41)),
                "retrospective_heldout": list(range(41, 46)),
            },
            "sample_structure": {"model_cells": 9, "seeds_per_cell": 3, "valid_runs": 27},
            "treatments": ["capacity tier", "history horizon", "MLP/Transformer family"],
            "primary_metrics": ["retrospective held-out rollout-macro NLL"],
            "sources": [_source(root, v3_training_path), _source(root, v3_selection_path)],
        },
        {
            "block_id": "F2_r3_predictor_risk",
            "scientific_role": "broad_closed_loop_predictor_risk_frontier",
            "population": "Town05 corrected R3 ego initialisations 101--105",
            "independent_unit": r3_contract.get("analysis_unit", "ego_init_id"),
            "independent_groups": r3_contract["ego_init_ids"],
            "sample_structure": {"rollouts": 80, "cells": len(r3_contract["cells"])},
            "treatments": {
                "predictors": sorted(r3_contract["predictors"]),
                "risk_policies": r3_contract["risk_policies"],
                "target_styles": sorted({cell["target_style"] for cell in r3_contract["cells"]}),
            },
            "primary_metrics": ["completion time", "minimum footprint separation"],
            "sources": [_source(root, r3_complete_path), _source(root, r3_contract_path)],
        },
        {
            "block_id": "F5_v3_selected_model_closed_loop",
            "scientific_role": "prospective_selected_model_transfer",
            "population": "Town05 V3 closed-loop ego initialisations 81--90",
            "independent_unit": "ego_init_id",
            "independent_groups": v3_manifest["ego_init_ids"],
            "sample_structure": {"rollouts": 80, "cells": 8},
            "treatments": {
                "predictors": v3_manifest["predictors"],
                "risk_policies": v3_manifest["risk_policies"],
                "target_styles": v3_manifest["target_styles"],
                "supervisor_authority": v3_manifest["nuisance_settings"]["supervisor_authority"],
            },
            "primary_metrics": ["completion time", "minimum footprint separation"],
            "sources": [_source(root, v3_closed_complete_path), _source(root, v3_closed_manifest_path)],
        },
        {
            "block_id": "F3_sf4_supervisor_authority",
            "scientific_role": "complete_behavioural_authority_mechanism_ablation",
            "population": "Town05 SF4 ego initialisations 106--115",
            "independent_unit": sf4_contract["independent_unit"],
            "independent_groups": sf4_contract["ego_init_ids"],
            "sample_structure": {"rollouts": 80, "cells": len(sf4_contract["cells"])},
            "treatments": {
                "predictor": sf4_contract["predictor"],
                "risk_policies": sf4_contract["risk_policies"],
                "target_styles": sf4_contract["target_styles"],
                "supervisor_authority": ["on", "off"],
            },
            "primary_metrics": ["failure-penalised completion time", "minimum footprint separation"],
            "sources": [_source(root, sf4_complete_path), _source(root, sf4_contract_path)],
        },
    ]
    signatures = []
    completion_hashes = []
    for block in blocks:
        signature_payload = {
            "block_id": block["block_id"],
            "population": block["population"],
            "independent_groups": block["independent_groups"],
            "treatments": block["treatments"],
        }
        block["population_signature"] = _stable_sha(signature_payload)
        signatures.append(block["population_signature"])
        completion_hashes.append(block["sources"][0]["sha256"])
    if len(signatures) != len(set(signatures)):
        raise ValueError("Evidence-block population signatures are not unique")
    if len(completion_hashes) != len(set(completion_hashes)):
        raise ValueError("Evidence-block primary completion hashes are not unique")
    return blocks


def _build_claims(root: Path) -> list[dict[str, Any]]:
    f1_path = (
        "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
        "frozen_test_same_aggregation.csv"
    )
    f1_rows = _load_csv(root, f1_path)
    b0 = _row_by(f1_rows, variant="B0", aggregation_level="rollout_macro")
    b1 = _row_by(f1_rows, variant="B1", aggregation_level="rollout_macro")

    axes_path = "docs/paper/generated/capacity_history_v3/final/table_three_axis_contrasts.csv"
    axes_rows = _load_csv(root, axes_path)
    capacity = _effect(_row_by(axes_rows, contrast_id="H1_capacity_transformer_full_small_minus_large"))
    info_mlp = _effect(_row_by(axes_rows, contrast_id="H2_information_mlp_snapshot_minus_full"))
    info_t = _effect(_row_by(axes_rows, contrast_id="H2_information_transformer_snapshot_minus_full"))
    attention_did = _effect(
        _row_by(axes_rows, contrast_id="H3_attention_history_gain_difference_in_differences")
    )
    direct_t = _effect(
        _row_by(axes_rows, contrast_id="architecture_direct_mlp_minus_transformer__h1p0__large")
    )

    v3_path = "docs/paper/generated/capacity_history_v3/final/table_model_by_risk_contrasts.csv"
    v3_rows = _load_csv(root, v3_path)
    v3_transfer = {
        policy: {
            metric: _effect(
                _row_by(
                    v3_rows,
                    contrast_id=f"{metric}__P_star_minus_B1__{policy}",
                )
            )
            for metric in ("completion_time_s", "min_footprint_separation_m")
        }
        for policy in ("fixed_medium", "adaptive")
    }
    model_risk = {
        metric: _effect(
            _row_by(v3_rows, contrast_id=f"{metric}__model_by_risk__adaptive_minus_fixed_medium")
        )
        for metric in ("completion_time_s", "min_footprint_separation_m")
    }

    r3_verdict_path = (
        "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/"
        "synthesis/table_final_hypothesis_verdicts.csv"
    )
    r3_verdicts = _load_csv(root, r3_verdict_path)
    r3_h4 = _row_by(r3_verdicts, hypothesis="H4")

    sf4_path = (
        "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/"
        "analysis/sf4_inference.json"
    )
    sf4 = _load_json(root, sf4_path)
    completion = sf4["outcomes"]["failure_penalized_completion_time_s"]
    direct = sf4["direct_paired_effects"]["failure_penalized_completion_time_s"]

    common = {
        "new_collection_status": "pending_raw_telemetry_gap_audit",
        "scenario_boundary": "one controlled Town05 right-hand-traffic left-turn give-way distribution",
    }
    claims = [
        {
            "claim_id": "F0_FOUNDATION",
            "hypothesis": "foundation",
            "claim": "Task adaptation materially improves the bounded MultiPath prediction stack relative to pretrained B0.",
            "estimand": "B1 minus B0 rollout-macro NLL/ADE/FDE",
            "population_id": "F1_foundation_adaptation",
            "independent_unit": "5 held-out ego initialisation groups",
            "decision_rule": "All three common metrics favour B1 with paired direction retained across groups.",
            "evidence": {
                "B0": {"NLL": float(b0["trajectory_mixture_NLL_nats_per_step"]), "ADE_m": float(b0["top1_ADE_m"]), "FDE_m": float(b0["top1_FDE_m"])},
                "B1": {"NLL": float(b1["trajectory_mixture_NLL_nats_per_step"]), "ADE_m": float(b1["top1_ADE_m"]), "FDE_m": float(b1["top1_FDE_m"])},
            },
            "verdict": "supported_with_distribution_and_tail_boundary",
            "boundary": "Response-active windows are sparse; calibrated response-tail NLL is a separate diagnostic.",
            "prohibited_overclaim": "Do not call this 100% accuracy or use it as the Capacity hypothesis.",
            "source": _source(root, f1_path, "rows B0/B1; aggregation_level=rollout_macro"),
            **common,
        },
        {
            "claim_id": "H1_CAPACITY",
            "hypothesis": "H1",
            "claim": "Increasing trainable capacity is not a persuasive explanation for the temporal-model result.",
            "estimand": "small minus large Transformer rollout-macro NLL at 1.0 s history",
            "population_id": "F4_capacity_information_architecture_v3",
            "independent_unit": "5 retrospective held-out ego initialisation groups",
            "decision_rule": "Require a coherent monotonic capacity trend and confirmatory paired evidence.",
            "evidence": capacity,
            "verdict": "capacity_limitation_explanation_not_supported",
            "boundary": "The small-to-large direction is positive but tiny; medium-to-large ordering is non-monotonic and multiplicity-adjusted evidence is non-confirmatory.",
            "prohibited_overclaim": "Do not claim capacity never matters outside the tested tiers and training protocol.",
            "source": _source(root, axes_path, "/contrast_id=H1_capacity_transformer_full_small_minus_large"),
            **common,
        },
        {
            "claim_id": "H2_INFORMATION",
            "hypothesis": "H2",
            "claim": "Recent explicit interaction history adds a small, rapidly saturating predictive signal for both encoder families.",
            "estimand": "current-token-only minus 1.0 s history rollout-macro NLL",
            "population_id": "F4_capacity_information_architecture_v3",
            "independent_unit": "5 retrospective held-out ego initialisation groups",
            "decision_rule": "Require a favourable paired direction for both matched large MLP and Transformer models and report the 0.4 s saturation diagnostic.",
            "evidence": {"MLP": info_mlp, "Transformer": info_t},
            "verdict": "supported_as_small_saturating_information_gain",
            "boundary": "Effect sizes are small, groups are retrospective held out, and exact multiplicity-adjusted tests are underpowered.",
            "prohibited_overclaim": "Do not equate input sensitivity with causal intent understanding or a need for attention.",
            "source": _source(root, axes_path, "/contrast_id starts H2_information"),
            **common,
        },
        {
            "claim_id": "H3_ARCHITECTURE",
            "hypothesis": "H3",
            "claim": "The tested Transformer has a bounded direct encoder-family advantage but does not extract more incremental value from history than the matched MLP.",
            "estimand": "matched MLP-minus-Transformer direct NLL and history-gain difference-in-differences",
            "population_id": "F4_capacity_information_architecture_v3",
            "independent_unit": "5 retrospective held-out ego initialisation groups",
            "decision_rule": "An attention-specific claim requires both lower matched NLL and a positive history-gain interaction.",
            "evidence": {"direct_full_history_gap": direct_t, "history_gain_DID": attention_did},
            "verdict": "attention_specific_history_extraction_not_supported",
            "boundary": "A direct family gap remains, but the interaction interval crosses zero under the tested model and optimisation budget.",
            "prohibited_overclaim": "Do not claim Transformers are generally ineffective or MLPs are generally superior.",
            "source": _source(root, axes_path, "/direct architecture and H3 DID rows"),
            **common,
        },
        {
            "claim_id": "H4A_SELECTED_MODEL_TRANSFER",
            "hypothesis": "H4a",
            "claim": "The validation-selected P* remains predictively distinguishable in CARLA, but does not demonstrate a uniform co-primary physical advantage over B1.",
            "estimand": "P* minus B1 completion time and minimum footprint separation within risk",
            "population_id": "F5_v3_selected_model_closed_loop",
            "independent_unit": "10 paired ego initialisation groups",
            "decision_rule": "Require faster completion and no-worse separation without excess binary failures.",
            "evidence": v3_transfer,
            "verdict": "physical_transfer_not_demonstrated_uniformly",
            "boundary": "Supervisor authority is enabled in all cells; this is a full-stack effect, not pure predictor-weight causality.",
            "prohibited_overclaim": "Do not infer that improved prediction is useless or that the supervisor is the sole attenuator.",
            "source": _source(root, v3_path, "/P_star_minus_B1 contrasts"),
            **common,
        },
        {
            "claim_id": "H4B_RISK_FRONTIER",
            "hypothesis": "H4b",
            "claim": "Adaptive risk is a context-dependent operating point rather than a universal replacement for fixed risk.",
            "estimand": "adaptive minus fixed-risk completion/separation frontier contrasts",
            "population_id": "F2_r3_predictor_risk and F5_v3_selected_model_closed_loop (reported separately)",
            "independent_unit": "R3: 5 groups; V3: 10 groups",
            "decision_rule": "Universal dominance requires no-worse efficiency and separation plus one strict gain and no excess binary failures in every declared comparator.",
            "evidence": {"R3": r3_h4["paper_claim"], "V3_model_by_risk_interaction": model_risk},
            "verdict": "context_dependent_not_universally_dominant",
            "boundary": "R3 and V3 populations are never pooled; zero observed collisions create a binary ceiling.",
            "prohibited_overclaim": "Do not claim adaptive risk is useless, equivalent to fixed risk or universally safer.",
            "source": _source(root, r3_verdict_path, "/hypothesis=H4"),
            **common,
        },
        {
            "claim_id": "H4C_SUPERVISOR_AUTHORITY",
            "hypothesis": "H4c",
            "claim": "Complete rule-based supervisor authority has a large common effect on nominal completion/yielding in both tested risk arms.",
            "estimand": sf4["primary_estimand"],
            "population_id": "F3_sf4_supervisor_authority",
            "independent_unit": sf4["independent_unit"],
            "decision_rule": "Report direct authority effects for each risk and the risk-by-authority DID; retain adverse outcomes and floor saturation.",
            "evidence": {
                "authority_effect_adaptive": direct["authority_effect_adaptive"],
                "authority_effect_fixed_medium": direct["authority_effect_fixed_medium"],
                "primary_DID": completion,
            },
            "verdict": "large_common_authority_effect_selective_masking_not_supported",
            "boundary": "Authority-off has 0/40 completion and substantial adverse outcomes, producing floor saturation; the supervisor is a seven-channel behavioural bundle.",
            "prohibited_overclaim": "Do not report statistical equivalence, selective masking as established, or the supervisor as the sole cause of trajectory similarity.",
            "source": _source(root, sf4_path, "/outcomes/failure_penalized_completion_time_s"),
            **common,
        },
    ]
    return claims


def _build_terminology() -> list[dict[str, str]]:
    rows = [
        ("MultiPath mixture predictor", "A fixed-anchor Gaussian-mixture trajectory predictor.", "p(Y|X)=sum_k pi_k N(mu_k,Sigma_k)", "multipath_output", "MultiPath"),
        ("B0", "Pretrained MultiPath control stack without task adaptation.", "B_0", "predictor=B0", "pretrained baseline"),
        ("B1", "MultiPath stack with the final prediction head adapted to the give-way task.", "B_1", "predictor=B1 or head-large", "task-adapted reference"),
        ("P*", "Validation-frozen best V3 sequence model: large Transformer with 1.0 s history.", "P^*", "predictor=P_star; transformer-h1p0-large", "selected sequence model"),
        ("interaction history", "Six-token explicit ego-target interaction sequence with a fixed valid-token mask.", "H_t", "history_horizon_s", "history tokens"),
        ("rollout-macro NLL", "Trajectory mixture NLL averaged within rollout before aggregation.", "NLL_macro", "rollout_macro_nll", "NLL"),
        ("adaptive risk", "Risk allocation recomputed from the interaction state within rollout.", "alpha_t", "risk_policy=adaptive", "variable risk"),
        ("fixed risk", "A time-invariant declared risk allocation profile.", "alpha", "risk_policy=fixed_*", "static risk"),
        ("SMPC", "Stochastic model predictive controller using multimodal predictions and chance-constraint tightening.", "pi_SMPC", "smpc_agent", "controller"),
        ("rule-based supervisor", "Seven-channel rule-aware layer that may shape references, bypass solving, change commands and manage recovery state.", "S_theta", "supervisor_behavioural_authority", "supervisor"),
        ("supervisor behavioural authority", "Whether supervisor candidates are applied to the factual control path.", "A in {on,off}", "yield_supervisor_behavioural_authority_mode", "authority"),
        ("nominal solver command", "Command produced by the factual SMPC solve before post-solver rule arbitration.", "u_nom", "nominal_solver_command", "nominal action"),
        ("supervisor candidate command", "Counterfactual command requested by the rule supervisor.", "u_sup", "supervisor_candidate_command", "candidate action"),
        ("executed command", "Command placed on the factual control path after authority arbitration.", "u_exec", "actual_command", "actual action"),
        ("controller acceptance", "An attempted solver output accepted for execution, including accepted SUBOPTIMAL status.", "A_ctrl", "is_opt/controller_accepted", "feasibility"),
        ("fallback", "Attempted solve whose output was not controller-accepted and used the declared fallback path.", "F_ctrl", "fallback_or_nonaccepted", "solver failure"),
        ("ego vehicle", "Vehicle that turns left and must yield before entering the conflict zone.", "E", "role=ego", "turning vehicle"),
        ("target vehicle", "Opposing priority vehicle proceeding straight through the intersection.", "T", "role=target", "oncoming vehicle"),
        ("minimum footprint separation", "Minimum separation between oriented CARLA vehicle bounding boxes.", "d_min", "min_footprint_separation_m", "safety margin"),
        ("initialisation group", "One paired scenario initialisation used as the independent analysis cluster.", "g", "ego_init_id", "seed"),
    ]
    return [
        {"canonical_term": a, "definition": b, "symbol": c, "code_evidence_mapping": d, "avoid_as_synonym": e}
        for a, b, c, d, e in rows
    ]


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: json.dumps(row[field], sort_keys=True) if isinstance(row.get(field), (dict, list)) else row.get(field)
                    for field in fields
                }
            )


def build_contract(root: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    blocks = _build_blocks(root)
    claims = _build_claims(root)
    terms = _build_terminology()

    argument = (
        "In a controlled Town05 right-hand-traffic left-turn give-way task, task-specific "
        "adaptation and short interaction history improve bounded multimodal prediction, "
        "but capacity, attention and adaptive risk do not uniformly improve executed "
        "behaviour; complete rule-based supervisor authority is essential for nominal "
        "yielding and completion in the tested sample, while selective masking of one "
        "upstream method is not established."
    )
    hypotheses = {
        "H1": {
            "axis": "Capacity",
            "statement": "At fixed 1.0 s history, increasing Transformer trainable capacity materially and coherently reduces held-out rollout-macro NLL.",
            "current_verdict": "not_supported_as_main_explanation",
        },
        "H2": {
            "axis": "Information",
            "statement": "At matched large capacity, explicit recent interaction history improves rollout-macro NLL beyond the current interaction token for both encoder families.",
            "current_verdict": "supported_as_small_saturating_gain",
        },
        "H3": {
            "axis": "Architecture",
            "statement": "At matched capacity and information, attention extracts more incremental value from history than an MLP.",
            "current_verdict": "attention_specific_gain_not_supported",
        },
        "H4": {
            "axis": "Closed-loop system utility",
            "statement": "Predictor and adaptive-risk improvements retain useful physical effects under the coupled stack, while complete supervisor authority mediates the executed outcome.",
            "current_verdict": "conditional_transfer_context_dependent_risk_large_common_authority_effect",
        },
    }
    contract = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "paper_argument": argument,
        "scenario": {
            "map": "Town05",
            "traffic_side": "right-hand traffic",
            "junction": "unsignalised give-way",
            "ego_manoeuvre": "left turn across opposing traffic",
            "target_manoeuvre": "straight priority movement",
            "required_phases": ["approach", "yield before conflict", "resume after clearance"],
        },
        "foundation_result": "B0 versus B1 is supporting task-foundation evidence, not H1 Capacity.",
        "hypotheses": hypotheses,
        "evidence_blocks": [block["block_id"] for block in blocks],
        "claim_ids": [claim["claim_id"] for claim in claims],
        "global_boundaries": [
            "No cross-map or real-road generalisation.",
            "Zero observed collisions are event counts, not a safety proof.",
            "Retrospective held-out V3 groups are not a fresh confirmatory test.",
            "Controller acceptance is not mathematical feasibility.",
            "SF4 authority-off floor saturation prevents equivalence or no-masking claims.",
        ],
    }

    evidence_path = output_dir / "evidence_blocks.json"
    claims_json_path = output_dir / "claim_evidence_boundary.json"
    claims_csv_path = output_dir / "claim_evidence_boundary.csv"
    terms_path = output_dir / "terminology_ledger.csv"
    contract_path = output_dir / "thesis_contract.json"
    markdown_path = output_dir / "THESIS_CONTRACT.md"

    evidence_path.write_text(json.dumps({"schema_version": "evidence_block_registry_v1", "status": "pass", "blocks": blocks}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    claims_json_path.write_text(json.dumps({"schema_version": "claim_evidence_boundary_matrix_v1", "status": "pass", "claims": claims}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_csv(
        claims_csv_path,
        claims,
        ["claim_id", "hypothesis", "claim", "estimand", "population_id", "independent_unit", "decision_rule", "evidence", "verdict", "boundary", "prohibited_overclaim", "source", "new_collection_status", "scenario_boundary"],
    )
    _write_csv(
        terms_path,
        terms,
        ["canonical_term", "definition", "symbol", "code_evidence_mapping", "avoid_as_synonym"],
    )
    contract_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# Frozen thesis scientific contract",
        "",
        "## One-sentence argument",
        "",
        argument,
        "",
        "## Hypotheses",
        "",
    ]
    for hid, item in hypotheses.items():
        lines.append(f"- **{hid} — {item['axis']}:** {item['statement']} **Current verdict:** `{item['current_verdict']}`.")
    lines.extend([
        "",
        "## Reader boundary",
        "",
        "B0 versus B1 establishes the task foundation before H1. H4 is reported as three separate estimands: selected-model transfer, the risk frontier and complete supervisor authority. The paper does not claim selective masking unless a same-state or valid interaction analysis identifies it.",
        "",
        "## Evidence blocks",
        "",
    ])
    for block in blocks:
        lines.append(f"- `{block['block_id']}` — {block['scientific_role']}; independent unit: {block['independent_unit']}.")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    products = [evidence_path, claims_json_path, claims_csv_path, terms_path, contract_path, markdown_path]
    complete = {
        "schema_version": "supervisor_bottleneck_scientific_contract_complete_v1",
        "status": "pass",
        "products": {path.name: _sha256(path) for path in products},
        "source_files": {
            source["path"]: source["sha256"]
            for block in blocks
            for source in block["sources"]
        },
        "evidence_blocks": len(blocks),
        "claims": len(claims),
        "terminology_entries": len(terms),
        "population_signatures_unique": True,
        "completion_hashes_unique": True,
    }
    complete_path = output_dir / "SCIENTIFIC_CONTRACT_COMPLETE.json"
    complete_path.write_text(json.dumps(complete, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return complete


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[4]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "docs/paper/generated/supervisor_bottleneck_v1/scientific_contract",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = build_contract(args.root.resolve(), args.output_dir.resolve())
    print(json.dumps({"status": result["status"], "claims": result["claims"], "evidence_blocks": result["evidence_blocks"]}))


if __name__ == "__main__":
    main()
