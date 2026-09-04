#!/usr/bin/env python3
"""Build a population-separated H1--H3 supervisor-masking evidence audit.

The independent unit is always the declared scenario/initialisation group.  The
analyser juxtaposes foundation, CIA, V3, R3, SF4, timing and legacy evidence but
never creates a pooled estimate across those populations.  Causal ``masking``
is reserved for aligned same-state command pairs or a non-saturated factorial
policy-by-authority interaction; absent either design, the strongest licensed
verdict remains explicitly weaker.

An optional V3 raw-telemetry summary can be supplied as an external audit
input.  It must use ``v3_server_command_transmission_audit_v1`` and carry a
complete provenance inventory.  Missing or malformed requested inputs fail
closed.  Different factual trajectories remain descriptive even when paired by
initialisation; they are not promoted to same-state counterfactual evidence.
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
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "supervisor_masking_evidence_analysis_v1"
ALIGNED_SCHEMA_VERSION = "aligned_supervisor_policy_commands_v1"
SHADOW_ANALYSIS_SCHEMA_VERSION = "shadow_command_transmission_analysis_v1"
V3_EXTERNAL_SCHEMA_VERSION = "v3_server_command_transmission_audit_v1"
BOOTSTRAP_REPLICATES = 10_000
BOOTSTRAP_SEED = 20260825
DENOMINATOR_EPSILON = 1.0e-9

F1_ROWS = Path(
    "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
    "frozen_test_same_aggregation.csv"
)
CIA_CELLS = Path("docs/paper/generated/capacity_history_v3/final/table_offline_model_cells.csv")
CIA_CONTRASTS = Path(
    "docs/paper/generated/capacity_history_v3/final/table_three_axis_contrasts.csv"
)
V3_ROWS = Path(
    "docs/paper/generated/capacity_history_v3/results/closed_loop/closed_loop_rows.json"
)
V3_COMPLETE = Path(
    "docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_COMPLETE.json"
)
V3_CONTRASTS = Path(
    "docs/paper/generated/capacity_history_v3/final/table_model_by_risk_contrasts.csv"
)
R3_COMPLETE = Path(
    "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/"
    "server_runs/r3_corrected_formal_v3/R3_COMPLETE.json"
)
R3_FRONTIER = Path(
    "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/"
    "synthesis/table_r3_h4_dominance.csv"
)
R3_RISK_MANIPULATION = Path(
    "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/"
    "server_runs/r3_corrected_formal_v3/analysis/r3_risk_manipulation_checks.csv"
)
SF4_ROWS = Path(
    "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/"
    "analysis/sf4_rollout_outcomes.csv"
)
SF4_INFERENCE = Path(
    "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/"
    "analysis/sf4_inference.json"
)
SF4_COMPLETE = Path(
    "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/"
    "analysis/SF4_ANALYSIS_COMPLETE.json"
)
TIMING_COMPLETE = Path(
    "docs/paper/generated/day12/timing_synthesis/DAY12_TIMING_SYNTHESIS_COMPLETE.json"
)
TIMING_CONTRASTS = Path(
    "docs/paper/generated/day12/timing_synthesis/day12_timing_paired_contrasts.csv"
)
LEGACY_COMPLETE = Path("docs/paper/generated/day6/DAY6_COMPLETE.json")
LEGACY_AUDIT = Path("docs/paper/generated/day6/day6_collection_audit.json")
TELEMETRY_COMPLETE = Path(
    "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/"
    "TELEMETRY_AUDIT_COMPLETE.json"
)
TELEMETRY_SOLVER = Path(
    "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/"
    "solver_path_reconciliation.json"
)
TELEMETRY_ATTENUATION = Path(
    "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/"
    "attenuation_claim_audit.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Refusing empty canonical CSV: {path}")
    return rows


def _finite(value: Any, *, field: str = "value") -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} is missing or non-numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field} is non-finite")
    return result


def _integer(value: Any, *, field: str = "value") -> int:
    result = _finite(value, field=field)
    if not result.is_integer():
        raise ValueError(f"{field} is not integral")
    return int(result)


def _one(rows: Sequence[Mapping[str, Any]], **criteria: str) -> Mapping[str, Any]:
    found = [row for row in rows if all(str(row.get(key)) == value for key, value in criteria.items())]
    if len(found) != 1:
        raise ValueError(f"Expected one row for {criteria}, found {len(found)}")
    return found[0]


def _source(root: Path, relative: Path) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return {
        "path": str(relative),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
    }


def _percentile(values: Sequence[float], q: float) -> float:
    if not values:
        raise ValueError("Cannot take a percentile of no values")
    index = int(q * (len(values) - 1))
    return sorted(values)[index]


def _bootstrap_mean_ci(
    values: Sequence[float], *, seed: int, draws: int = BOOTSTRAP_REPLICATES
) -> list[float]:
    """Percentile bootstrap over already-aggregated independent groups."""
    if not values:
        raise ValueError("Cannot bootstrap no independent groups")
    if draws < 100:
        raise ValueError("At least 100 bootstrap draws are required")
    values = list(values)
    rng = random.Random(seed)
    estimates = [fmean(rng.choice(values) for _ in values) for _ in range(draws)]
    return [_percentile(estimates, 0.025), _percentile(estimates, 0.975)]


def _bootstrap_ratio_ci(
    pairs: Sequence[tuple[float, float]], *, seed: int, draws: int
) -> list[float]:
    """Bootstrap ratio of group-mean post distance to group-mean pre distance."""
    if not pairs or any(pre <= DENOMINATOR_EPSILON for pre, _ in pairs):
        raise ValueError("Degenerate pre-supervisor denominator")
    rng = random.Random(seed)
    estimates = []
    for _ in range(draws):
        sampled = [rng.choice(pairs) for _ in pairs]
        pre = fmean(item[0] for item in sampled)
        post = fmean(item[1] for item in sampled)
        if pre <= DENOMINATOR_EPSILON:
            raise ValueError("Degenerate bootstrap denominator")
        estimates.append(post / pre)
    return [_percentile(estimates, 0.025), _percentile(estimates, 0.975)]


def _euclidean(left: Sequence[Any], right: Sequence[Any]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Command vectors must have the same non-zero dimension")
    differences = [
        _finite(a, field="command component") - _finite(b, field="command component")
        for a, b in zip(left, right)
    ]
    return math.sqrt(sum(value * value for value in differences))


def analyze_aligned_attenuation(
    records: Sequence[Mapping[str, Any]],
    *,
    policy_pair: Sequence[str],
    draws: int = BOOTSTRAP_REPLICATES,
    seed: int = BOOTSTRAP_SEED,
) -> dict[str, Any]:
    """Estimate same-state nominal-to-executed policy-distance retention.

    Required row fields are ``alignment_id``, ``group_id``, ``policy``,
    ``nominal_command``, ``executed_command`` and boolean ``supervisor_active``.
    Exactly one row per alignment/policy is required.  A zero nominal-policy
    distance is a scientific non-identification result, never a ratio of zero.
    """

    if len(policy_pair) != 2 or policy_pair[0] == policy_pair[1]:
        raise ValueError("policy_pair must contain two distinct policy names")
    expected = set(policy_pair)
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in records:
        alignment = str(row.get("alignment_id", "")).strip()
        if not alignment:
            raise ValueError("alignment_id is required")
        if str(row.get("policy")) not in expected:
            raise ValueError("Unexpected aligned-evidence policy")
        if type(row.get("supervisor_active")) is not bool:
            raise ValueError("supervisor_active must be boolean")
        if str(row.get("group_id", "")).strip() == "":
            raise ValueError("group_id is required")
        grouped[alignment].append(row)
    if not grouped:
        raise ValueError("Aligned evidence contains no records")

    paired: list[dict[str, Any]] = []
    for alignment, rows in sorted(grouped.items()):
        if len(rows) != 2 or {str(row["policy"]) for row in rows} != expected:
            raise ValueError(f"Alignment {alignment} lacks exactly one row per policy")
        left = next(row for row in rows if row["policy"] == policy_pair[0])
        right = next(row for row in rows if row["policy"] == policy_pair[1])
        if left["group_id"] != right["group_id"]:
            raise ValueError(f"Alignment {alignment} crosses independent groups")
        if left["supervisor_active"] != right["supervisor_active"]:
            raise ValueError(f"Alignment {alignment} has policy-dependent activity label")
        paired.append(
            {
                "alignment_id": alignment,
                "group_id": str(left["group_id"]),
                "supervisor_active": bool(left["supervisor_active"]),
                "pre_supervisor_distance": _euclidean(
                    left.get("nominal_command", []), right.get("nominal_command", [])
                ),
                "post_supervisor_distance": _euclidean(
                    left.get("executed_command", []), right.get("executed_command", [])
                ),
            }
        )

    def summarize(label: str, subset: Sequence[Mapping[str, Any]], offset: int) -> dict[str, Any]:
        if not subset:
            return {
                "stratum": label,
                "status": "unavailable_no_aligned_states",
                "retention_ratio": None,
                "retention_ratio_ci95": None,
                "verdict": "not_identified",
            }
        by_group: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in subset:
            by_group[str(row["group_id"])].append(row)
        group_pairs = [
            (
                fmean(float(row["pre_supervisor_distance"]) for row in rows),
                fmean(float(row["post_supervisor_distance"]) for row in rows),
            )
            for _, rows in sorted(by_group.items())
        ]
        pre = fmean(item[0] for item in group_pairs)
        post = fmean(item[1] for item in group_pairs)
        if pre <= DENOMINATOR_EPSILON:
            return {
                "stratum": label,
                "status": "fail_closed_degenerate_denominator",
                "independent_groups": len(group_pairs),
                "aligned_states": len(subset),
                "pre_supervisor_distance": pre,
                "post_supervisor_distance": post,
                "retention_ratio": None,
                "retention_ratio_ci95": None,
                "verdict": "controller_insensitivity_not_supervisor_masking",
            }
        ratio = post / pre
        ci = _bootstrap_ratio_ci(group_pairs, seed=seed + offset, draws=draws)
        if label == "active" and ci[1] < 1.0:
            verdict = "causally_identified_command_level_masking"
        elif ratio < 1.0:
            verdict = "attenuated_consistent_with_masking"
        elif ratio > 1.0:
            verdict = "amplified"
        else:
            verdict = "retained"
        return {
            "stratum": label,
            "status": "estimated",
            "independent_groups": len(group_pairs),
            "aligned_states": len(subset),
            "pre_supervisor_distance": pre,
            "post_supervisor_distance": post,
            "retention_ratio": ratio,
            "retention_ratio_ci95": ci,
            "bootstrap_unit": "group_id",
            "bootstrap_replicates": draws,
            "verdict": verdict,
        }

    strata = [
        summarize("all", paired, 0),
        summarize("active", [row for row in paired if row["supervisor_active"]], 101),
        summarize("inactive", [row for row in paired if not row["supervisor_active"]], 202),
    ]
    active = next(row for row in strata if row["stratum"] == "active")
    identified = active.get("verdict") == "causally_identified_command_level_masking"
    return {
        "schema_version": "aligned_command_attenuation_analysis_v1",
        "status": "pass",
        "alignment_rule": "exact alignment_id, group_id and supervisor activity; one command per policy",
        "policy_pair": list(policy_pair),
        "paired_records": paired,
        "strata": strata,
        "causal_command_masking_identified": identified,
        "trajectory_level_causal_claim_licensed": False,
        "boundary": "Aligned shadow commands identify only the immediate command mapping on the logged factual state distribution.",
    }


def _sf4_group_effect(
    rows: Sequence[Mapping[str, Any]], metric: str, *, binary: bool, seed: int
) -> dict[str, Any]:
    grouped: dict[tuple[int, str], list[float]] = defaultdict(list)
    for row in rows:
        grouped[(_integer(row["ego_init_id"], field="ego_init_id"), str(row["supervisor_authority_mode"]))].append(
            _finite(row[metric], field=metric)
        )
    init_ids = sorted({key[0] for key in grouped})
    if init_ids != list(range(106, 116)):
        raise ValueError("SF4 initialisation population is not 106--115")
    effects = []
    on_values = []
    off_values = []
    for init_id in init_ids:
        if len(grouped[(init_id, "on")]) != 4 or len(grouped[(init_id, "off")]) != 4:
            raise ValueError("SF4 authority arm is not balanced within initialisation")
        on = fmean(grouped[(init_id, "on")])
        off = fmean(grouped[(init_id, "off")])
        on_values.append(on)
        off_values.append(off)
        effects.append(on - off)
    return {
        "metric": metric,
        "effect_direction": "authority_on_minus_off",
        "authority_on_group_mean": fmean(on_values),
        "authority_off_group_mean": fmean(off_values),
        "mean_effect": fmean(effects),
        "cluster_bootstrap_95ci": _bootstrap_mean_ci(effects, seed=seed),
        "independent_groups": len(init_ids),
        "aggregation": "four balanced risk-by-target rollouts averaged within ego_init_id",
        "binary_metric": binary,
    }


def _build_h1(
    sf4_rows: list[dict[str, str]], sf4_complete: Mapping[str, Any], solver: Mapping[str, Any]
) -> dict[str, Any]:
    if len(sf4_rows) != 80 or sf4_complete.get("status") != "pass":
        raise ValueError("Canonical SF4 population is incomplete")
    by_authority: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in sf4_rows:
        by_authority[row["supervisor_authority_mode"]].append(row)
    if set(by_authority) != {"on", "off"} or any(len(rows) != 40 for rows in by_authority.values()):
        raise ValueError("SF4 must contain 40 rollouts per authority arm")

    arms = {}
    for authority, rows in sorted(by_authority.items()):
        arms[authority] = {
            "rollouts": len(rows),
            "independent_groups": len({row["ego_init_id"] for row in rows}),
            "completion_successes": sum(_integer(row["completion_success"]) for row in rows),
            "yield_rule_failures": sum(_integer(row["yield_rule_failure"]) for row in rows),
            "adverse_collision_rollouts": sum(_integer(row["adverse_collision_any"]) for row in rows),
            "mean_minimum_margin_adjusted_bbox_separation_m": fmean(
                _finite(row["minimum_margin_adjusted_bbox_separation_m"])
                for row in rows
            ),
        }
    expected = {
        "on": (40, 0, 0),
        "off": (0, 38, 21),
    }
    for authority, values in expected.items():
        observed = (
            arms[authority]["completion_successes"],
            arms[authority]["yield_rule_failures"],
            arms[authority]["adverse_collision_rollouts"],
        )
        if observed != values:
            raise ValueError(f"SF4 canonical H1 totals changed for authority={authority}: {observed}")

    activity = sf4_complete.get("observed_first_stage_activity", {}).get("by_authority", {})
    if set(activity) != {"on", "off"}:
        raise ValueError("SF4 first-stage authority mechanism summary is missing")
    solver_totals = solver.get("totals", {})
    canonical_solver = {
        "factual_solver_attempts": 18552,
        "controller_accepted_attempts": 17822,
        "fallback_or_nonaccepted_attempts": 730,
        "bypass_applied_steps": 1393,
    }
    if any(_integer(solver_totals.get(key), field=key) != value for key, value in canonical_solver.items()):
        raise ValueError("SF4 solver-path totals do not reconcile")

    effects = [
        _sf4_group_effect(sf4_rows, "completion_success", binary=True, seed=BOOTSTRAP_SEED + 1),
        _sf4_group_effect(sf4_rows, "yield_rule_failure", binary=True, seed=BOOTSTRAP_SEED + 2),
        _sf4_group_effect(sf4_rows, "adverse_collision_any", binary=True, seed=BOOTSTRAP_SEED + 3),
        _sf4_group_effect(
            sf4_rows,
            "minimum_margin_adjusted_bbox_separation_m",
            binary=False,
            seed=BOOTSTRAP_SEED + 4,
        ),
    ]
    return {
        "hypothesis": "H1",
        "question": "Does complete rule-based supervisor authority achieve nominal yielding in the tested Town05 give-way task?",
        "population_id": "F3_sf4_supervisor_authority",
        "independent_unit": "ego_init_id",
        "authority_channels": 7,
        "arms": arms,
        "group_level_effects": effects,
        "mechanism": {
            "authority_on_any_channel_requested_fraction": activity["on"]["any_channel_requested_fraction"],
            "authority_on_post_action_requested_fraction": activity["on"]["post_action_requested_fraction"],
            "authority_on_applied_fraction": activity["on"]["authority_applied_fraction"],
            "authority_on_actual_accel_abs_delta_mean_mps2": activity["on"]["actual_accel_abs_delta_mean_mps2"],
            "authority_on_rule_bypass_requested_fraction": activity["on"]["rule_smpc_bypass_requested_fraction"],
            "authority_on_rule_bypass_applied_fraction": activity["on"]["rule_smpc_bypass_applied_fraction"],
            "authority_on_factual_solver_attempted_fraction": activity["on"]["factual_solver_attempted_fraction"],
            "authority_off_any_channel_requested_fraction": activity["off"]["any_channel_requested_fraction"],
            "authority_off_post_action_requested_fraction": activity["off"]["post_action_requested_fraction"],
            "authority_off_applied_fraction": activity["off"]["authority_applied_fraction"],
            "authority_off_rule_bypass_requested_fraction": activity["off"]["rule_smpc_bypass_requested_fraction"],
            "authority_off_rule_bypass_applied_fraction": activity["off"]["rule_smpc_bypass_applied_fraction"],
            "authority_off_factual_solver_attempted_fraction": activity["off"]["factual_solver_attempted_fraction"],
            "solver_paths": canonical_solver,
        },
        "verdict": "supported_nominal_yielding_in_all_tested_authority_on_rollouts",
        "boundary": "This is an observed common effect of a seven-channel bundle in one Town05 geometry, not formal, general or real-road safety.",
    }


def _contrast(rows: Sequence[Mapping[str, Any]], contrast_id: str) -> dict[str, Any]:
    row = _one(rows, contrast_id=contrast_id)
    return {
        "contrast_id": contrast_id,
        "metric": row["metric"],
        "effect": _finite(row["effect"], field=f"{contrast_id}.effect"),
        "ci95": [
            _finite(row["ci95_low"], field=f"{contrast_id}.ci95_low"),
            _finite(row["ci95_high"], field=f"{contrast_id}.ci95_high"),
        ],
        "holm_adjusted_p": None
        if row.get("holm_adjusted_p") in (None, "")
        else _finite(row["holm_adjusted_p"]),
        "independent_groups": _integer(row["independent_groups"]),
        "evidence_status": row["evidence_status"],
    }


def _build_h2(
    f1_rows: list[dict[str, str]],
    cia_cells: list[dict[str, str]],
    cia_contrasts: list[dict[str, str]],
    v3_rows: list[dict[str, Any]],
    v3_contrasts: list[dict[str, str]],
    external_v3: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if len(cia_cells) != 9 or len(v3_rows) != 80:
        raise ValueError("CIA or V3 canonical population is incomplete")
    foundation = []
    for variant in ("B0", "B1"):
        row = _one(f1_rows, variant=variant, aggregation_level="rollout_macro")
        foundation.append(
            {
                "predictor": variant,
                "rollout_macro_nll": _finite(row["trajectory_mixture_NLL_nats_per_step"]),
                "top1_ADE_m": _finite(row["top1_ADE_m"]),
                "top1_FDE_m": _finite(row["top1_FDE_m"]),
                "independent_groups": 5,
            }
        )
    capacity = [
        {
            "model_cell_id": row["model_cell_id"],
            "trainable_parameters": _integer(row["trainable_parameters"]),
            "heldout_rollout_macro_nll": _finite(row["heldout_rollout_macro_nll_mean"]),
        }
        for row in cia_cells
        if row["model_cell_id"].startswith("transformer-h1p0-")
    ]
    if len(capacity) != 3:
        raise ValueError("Capacity tiers are incomplete")

    upstream = {
        "foundation": {
            "population_id": "F1_foundation_adaptation",
            "status": "available_supporting_not_pooled",
            "rows": foundation,
        },
        "capacity": {
            "population_id": "F4_capacity_information_architecture_v3",
            "status": "non_monotonic_capacity_effect",
            "cells": capacity,
            "primary_contrast": _contrast(
                cia_contrasts, "H1_capacity_transformer_full_small_minus_large"
            ),
        },
        "information": {
            "population_id": "F4_capacity_information_architecture_v3",
            "status": "small_saturating_history_gain",
            "contrasts": [
                _contrast(cia_contrasts, "H2_information_mlp_snapshot_minus_full"),
                _contrast(cia_contrasts, "H2_information_transformer_snapshot_minus_full"),
            ],
            "deployed_cell": "P_star=transformer-h0p4-large, selected without CARLA/test outcomes",
        },
        "architecture": {
            "population_id": "F4_capacity_information_architecture_v3",
            "status": "direct_gap_but_no_attention_specific_history_gain",
            "direct_full_history": _contrast(
                cia_contrasts, "architecture_direct_mlp_minus_transformer__h1p0__large"
            ),
            "history_gain_difference_in_differences": _contrast(
                cia_contrasts, "H3_attention_history_gain_difference_in_differences"
            ),
        },
    }
    inloop = [
        _contrast(v3_contrasts, f"inloop_top1_ADE_m__P_star_minus_B1__{risk}")
        for risk in ("fixed_medium", "adaptive")
    ]
    physical = [
        _contrast(v3_contrasts, f"{metric}__P_star_minus_B1__{risk}")
        for metric in ("completion_time_s", "min_footprint_separation_m")
        for risk in ("fixed_medium", "adaptive")
    ]
    intervention = [
        _contrast(v3_contrasts, f"supervisor_active_fraction__P_star_minus_B1__{risk}")
        for risk in ("fixed_medium", "adaptive")
    ]
    command_layer: dict[str, Any]
    if external_v3 is None:
        command_layer = {
            "status": "unavailable_no_provenance_bound_raw_summary",
            "candidate_control": None,
            "executed_control": None,
            "missing_not_imputed": True,
        }
    else:
        command_layer = {
            "status": "available_unmatched_factual_trajectories_descriptive_only",
            "predictor_contrasts": _external_command_contrasts(external_v3, axis="predictor"),
            "same_state_aligned": False,
        }
    return {
        "hypothesis": "H2",
        "question": "Do predictor improvements transfer through the common supervised control stack?",
        "blocks_are_juxtaposed_not_pooled": True,
        "upstream": upstream,
        "in_loop_prediction": {
            "population_id": "F5_v3_selected_model_closed_loop",
            "status": "difference_retained_in_at_least_one_risk_context",
            "contrasts": inloop,
        },
        "candidate_and_executed_control": command_layer,
        "supervisor_intervention": {
            "population_id": "F5_v3_selected_model_closed_loop",
            "contrasts": intervention,
        },
        "physical_outcomes": {
            "population_id": "F5_v3_selected_model_closed_loop",
            "status": "no_uniform_detected_transfer",
            "contrasts": physical,
        },
        "verdict": "consistent_with_masking_but_not_causally_identified",
        "causal_masking_identified": False,
        "boundary": "CIA policies were not all deployed; V3 shares authority-on supervision and lacks a same-state alternative-predictor mapping.",
    }


def _validate_external_v3(payload: Mapping[str, Any]) -> None:
    if payload.get("schema_version") != V3_EXTERNAL_SCHEMA_VERSION or payload.get("status") != "pass":
        raise ValueError("V3 external audit schema/status is invalid")
    population = payload.get("population")
    if not isinstance(population, Mapping):
        raise ValueError("V3 external audit population is absent")
    if population.get("rollouts") != 80 or population.get("ego_init_ids") != list(range(81, 91)):
        raise ValueError("V3 external audit population does not match the frozen protocol")
    if population.get("step_rows_are_not_independent_units") is not True:
        raise ValueError("V3 external audit does not preserve the group-level unit")
    rows = payload.get("rollout_summaries")
    sources = payload.get("source_inventory")
    if not isinstance(rows, list) or len(rows) != 80:
        raise ValueError("V3 external audit must contain 80 rollout summaries")
    if not isinstance(sources, list) or len(sources) != 80:
        raise ValueError("V3 external audit must contain 80 provenance records")
    keys = set()
    for row in rows:
        key = (row.get("predictor"), row.get("risk"), row.get("target"), row.get("ego_init_id"))
        if key in keys:
            raise ValueError("V3 external audit contains duplicate rollout keys")
        keys.add(key)
        for metric in (
            "mean_tightening",
            "mean_nominal_accel_mps2",
            "mean_actual_accel_mps2",
            "mean_abs_supervisor_accel_delta_mps2",
        ):
            _finite(row.get(metric), field=f"external V3 {metric}")
    for source in sources:
        if not isinstance(source, Mapping):
            raise ValueError("V3 provenance record is malformed")
        digest = str(source.get("sha256", ""))
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest.lower()):
            raise ValueError("V3 provenance SHA-256 is malformed")
        if _integer(source.get("line_count"), field="source line_count") <= 0:
            raise ValueError("V3 provenance line_count must be positive")
        if _integer(source.get("bytes"), field="source bytes") <= 0:
            raise ValueError("V3 provenance byte count must be positive")
    if payload.get("same_state_alternative_commands_present") is not False:
        raise ValueError("This audit version cannot assert same-state alternative commands")


def _external_command_contrasts(payload: Mapping[str, Any], *, axis: str) -> list[dict[str, Any]]:
    _validate_external_v3(payload)
    rows = payload["rollout_summaries"]
    keyed = {
        (row["predictor"], row["risk"], row["target"], int(row["ego_init_id"])): row
        for row in rows
    }
    metrics = (
        "mean_tightening",
        "mean_nominal_accel_mps2",
        "mean_actual_accel_mps2",
        "mean_abs_supervisor_accel_delta_mps2",
    )
    contrasts = []
    if axis == "risk":
        contexts = [
            (predictor, target, "adaptive", "fixed_medium")
            for predictor in ("B1", "P_star")
            for target in ("assertive_constant_speed", "defensive_reactive")
        ]
        context_names = ("predictor", "target", "left", "right")
    elif axis == "predictor":
        contexts = [
            (risk, target, "P_star", "B1")
            for risk in ("adaptive", "fixed_medium")
            for target in ("assertive_constant_speed", "defensive_reactive")
        ]
        context_names = ("risk", "target", "left", "right")
    else:
        raise ValueError("axis must be predictor or risk")
    for index, context in enumerate(contexts):
        values = dict(zip(context_names, context))
        effects: dict[str, Any] = {}
        for metric_index, metric in enumerate(metrics):
            diffs = []
            for init_id in range(81, 91):
                if axis == "risk":
                    left_key = (values["predictor"], values["left"], values["target"], init_id)
                    right_key = (values["predictor"], values["right"], values["target"], init_id)
                else:
                    left_key = (values["left"], values["risk"], values["target"], init_id)
                    right_key = (values["right"], values["risk"], values["target"], init_id)
                if left_key not in keyed or right_key not in keyed:
                    raise ValueError(f"V3 external audit lacks pair {left_key}/{right_key}")
                diffs.append(_finite(keyed[left_key][metric]) - _finite(keyed[right_key][metric]))
            effects[metric] = {
                "mean_effect": fmean(diffs),
                "cluster_bootstrap_95ci": _bootstrap_mean_ci(
                    diffs,
                    seed=BOOTSTRAP_SEED + 1000 + index * 31 + metric_index,
                ),
            }
        contrasts.append(
            {
                **values,
                "contrast": f"{values['left']}_minus_{values['right']}",
                "independent_groups": 10,
                "effects": effects,
                "alignment": "paired ego_init_id, different factual state sequences",
                "causal_attenuation_licensed": False,
            }
        )
    return contrasts


def _build_h3(
    r3_frontier: list[dict[str, str]],
    r3_risk_manipulation: list[dict[str, str]],
    v3_contrasts: list[dict[str, str]],
    sf4_inference: Mapping[str, Any],
    timing_contrasts: list[dict[str, str]],
    legacy_complete: Mapping[str, Any],
    legacy_audit: Mapping[str, Any],
    attenuation: Mapping[str, Any],
    external_v3: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if len(r3_frontier) != 12:
        raise ValueError(f"R3 fixed frontier must retain all 12 comparisons, found {len(r3_frontier)}")
    expected_frontier = {
        (predictor, target, fixed)
        for predictor in ("B0", "B1")
        for target in ("assertive", "reactive")
        for fixed in ("fixed_aggressive", "fixed_medium", "fixed_conservative")
    }
    observed_frontier = {
        (row["predictor"], row["target_style"], row["fixed_comparator"])
        for row in r3_frontier
    }
    if observed_frontier != expected_frontier:
        raise ValueError("R3 frontier is incomplete or outcome-selected")
    if len(r3_risk_manipulation) != 16:
        raise ValueError("R3 risk-manipulation block must retain all 16 cells")
    if any(row.get("manipulation_status") != "observed" for row in r3_risk_manipulation):
        raise ValueError("R3 risk-manipulation check did not pass in every cell")
    adaptive_manipulation = [
        {
            "predictor": row["predictor"],
            "target_style": row["target_style"],
            "risk_tightening_mean": _finite(row["risk_tightening_mean"]),
            "adaptive_risk_solver_fraction": _finite(row["adaptive_risk_solver_fraction"]),
            "rollouts_with_within_rollout_adaptive_variation": _integer(
                row["rollouts_with_within_rollout_adaptive_variation"]
            ),
            "rollouts": _integer(row["rollouts"]),
        }
        for row in r3_risk_manipulation
        if row["risk_policy"] == "adaptive"
    ]
    if len(adaptive_manipulation) != 4 or any(
        row["adaptive_risk_solver_fraction"] != 1.0
        or row["rollouts_with_within_rollout_adaptive_variation"] != row["rollouts"]
        for row in adaptive_manipulation
    ):
        raise ValueError("R3 adaptive-risk first-stage manipulation is incomplete")
    r3_rows = [
        {
            **dict(row),
            "paired_init_groups": _integer(row["paired_init_groups"]),
            "mean_adaptive_minus_fixed_completion_s": _finite(
                row["mean_adaptive_minus_fixed_completion_s"]
            ),
            "mean_adaptive_minus_fixed_separation_m": _finite(
                row["mean_adaptive_minus_fixed_separation_m"]
            ),
        }
        for row in r3_frontier
    ]
    v3_physical = [
        _contrast(v3_contrasts, f"{metric}__model_by_risk__adaptive_minus_fixed_medium")
        for metric in ("completion_time_s", "min_footprint_separation_m")
    ]
    direct = sf4_inference.get("direct_paired_effects", {})
    sf4_risk = {}
    for metric in (
        "failure_penalized_completion_time_s",
        "minimum_margin_adjusted_bbox_separation_m",
        "actual_minus_nominal_accel_abs_mean_mps2",
    ):
        effects = direct.get(metric)
        if not isinstance(effects, Mapping):
            raise ValueError(f"SF4 inference lacks {metric}")
        sf4_risk[metric] = {
            key: effects[key]
            for key in ("risk_effect_authority_on", "risk_effect_authority_off")
        }
    primary_name = sf4_inference.get("primary_estimand")
    primary_outcome = sf4_inference.get("primary_outcome")
    primary_result = sf4_inference.get("outcomes", {}).get(primary_outcome)
    if not isinstance(primary_name, str) or not isinstance(primary_result, Mapping):
        raise ValueError("SF4 primary risk-by-authority estimand is missing")
    primary = {
        "estimand": primary_name,
        "outcome": primary_outcome,
        "result": primary_result,
    }

    timing_rows = [
        {
            "contrast": row["contrast"],
            "metric": row["metric"],
            "effect": _finite(row["left_minus_right_mean"]),
            "ci95": [_finite(row["ci95_low"]), _finite(row["ci95_high"])],
            "independent_groups": _integer(row["independent_init_groups"]),
            "holm_adjusted_p": _finite(row["holm_adjusted_p_within_scope"]),
        }
        for row in timing_contrasts
        if row["inference_scope"] == "synthesis_policy_by_offset_primary"
        and row["contrast"].startswith("adaptive_minus_fixed_medium")
        and row["metric"]
        in {"target_clearance_adjusted_completion_delay_s", "min_footprint_separation_m"}
    ]
    if len(timing_rows) != 12:
        raise ValueError(f"Timing context block must retain 12 risk contrasts, found {len(timing_rows)}")
    if legacy_complete.get("status") != "pass" or legacy_complete.get("rollout_count") != 200:
        raise ValueError("Legacy Day6 population is incomplete")
    if legacy_audit.get("status") != "pass" or legacy_audit.get("rollouts_per_cell") != {
        "S0_ADAPTIVE": 50,
        "S0_FIXED": 50,
        "S1_ADAPTIVE": 50,
        "S1_FIXED": 50,
    }:
        raise ValueError("Legacy Day6 cells do not reconcile")

    command_layer: dict[str, Any]
    if external_v3 is None:
        command_layer = {
            "status": "unavailable_no_provenance_bound_raw_summary",
            "constraint_tightening": None,
            "nominal_control": None,
            "executed_control": None,
            "missing_not_imputed": True,
        }
    else:
        command_layer = {
            "status": "available_descriptive_different_factual_trajectories",
            "contrasts": _external_command_contrasts(external_v3, axis="risk"),
            "same_state_aligned": False,
            "interpretation": "Allocator differences are measurable at tightening and can contract at nominal-command level; these rollout means do not identify supervisor-specific attenuation.",
        }
    return {
        "hypothesis": "H3",
        "question": "Do fixed/adaptive risk-allocation differences transfer through SMPC and supervisor authority?",
        "blocks_are_juxtaposed_not_pooled": True,
        "r3_full_fixed_frontier": {
            "population_id": "F2_r3_predictor_risk",
            "comparisons": r3_rows,
            "declared_comparisons": 12,
            "adaptive_dominates": sum(row["dominance_status"] == "dominates" for row in r3_rows),
        },
        "r3_constraint_manipulation": {
            "population_id": "F2_r3_predictor_risk",
            "status": "adaptive_allocator_and_within_rollout_variation_observed",
            "adaptive_cells": adaptive_manipulation,
            "all_16_risk_cells_retained": True,
        },
        "v3_physical_transfer": {
            "population_id": "F5_v3_selected_model_closed_loop",
            "contrasts": v3_physical,
        },
        "v3_constraint_candidate_executed_transfer": command_layer,
        "sf4_risk_by_authority": {
            "population_id": "F3_sf4_supervisor_authority",
            "risk_effects": sf4_risk,
            "primary_risk_by_authority_estimand": primary,
            "authority_off_completion_floor": attenuation["floor_saturation"],
            "non_saturated_factorial_comparator": False,
        },
        "timing_context_sensitivity": {
            "population_id": "legacy_day10_day11_arrival_timing_synthesis",
            "comparisons": timing_rows,
            "pooling_permission": "must_not_pool_with_R3_V3_or_SF4",
        },
        "legacy_day6": {
            "population_id": "legacy_day6_target_response_collection",
            "rollouts": 200,
            "rollouts_per_cell": legacy_audit["rollouts_per_cell"],
            "collision_event_counts": legacy_audit["safety_summary"]["collision_events_per_cell"],
            "role": "appendix endpoint-definition evidence only",
            "boundary": "Repeated CARLA callback events are not rollout-level collision incidence and are not pooled with formal risk experiments.",
        },
        "verdict": "consistent_with_masking_but_not_causally_identified",
        "causal_masking_identified": False,
        "boundary": "R3 lacks authority variation; V3 lacks same-state alternatives; SF4 authority-off is floor-saturated and toggles seven channels together.",
    }


def _load_aligned_evidence(path: Path) -> tuple[Mapping[str, Any], dict[str, Any]]:
    payload = _read_json(path)
    if payload.get("status") != "pass":
        raise ValueError("Aligned evidence status is invalid")
    if payload.get("schema_version") == SHADOW_ANALYSIS_SCHEMA_VERSION:
        integrity = payload.get("integrity")
        aggregates = payload.get("aggregates")
        source = payload.get("source")
        if not isinstance(integrity, Mapping) or not isinstance(aggregates, list) or not aggregates:
            raise ValueError("Shadow-command analysis is missing integrity or aggregates")
        if not isinstance(source, Mapping):
            raise ValueError("Shadow-command analysis is missing source provenance")
        source_digest = str(source.get("sha256", ""))
        if len(source_digest) != 64 or any(
            char not in "0123456789abcdef" for char in source_digest.lower()
        ):
            raise ValueError("Shadow-command source SHA-256 is malformed")
        if _integer(source.get("rows"), field="shadow source rows") <= 0:
            raise ValueError("Shadow-command source row count must be positive")
        if integrity.get("shadow_actuation_count") != 0 or integrity.get("all_factual_parity") is not True:
            raise ValueError("Shadow-command actuation/parity gate failed")
        if payload.get("causal_scope") != "same-state immediate longitudinal command transmission only":
            raise ValueError("Shadow-command causal scope is absent or changed")
        identified_cells: dict[str, list[dict[str, Any]]] = {"predictor": [], "risk": []}
        for row in aggregates:
            axis = row.get("axis")
            if axis not in identified_cells:
                raise ValueError("Shadow-command aggregate has an unexpected axis")
            monitor = _finite(row.get("monitor_separation_accel_mps2"), field="monitor separation")
            enabled = _finite(row.get("enabled_separation_accel_mps2"), field="enabled separation")
            ratio = row.get("retention_ratio")
            if ratio is not None:
                ratio = _finite(ratio, field="retention ratio")
                if monitor <= DENOMINATOR_EPSILON:
                    raise ValueError("Shadow-command retention ratio has a degenerate denominator")
                if not math.isclose(ratio, enabled / monitor, rel_tol=1.0e-9, abs_tol=1.0e-12):
                    raise ValueError("Shadow-command retention ratio does not reconcile")
            if row.get("verdict") == "command_level_masking_identified":
                identified_cells[axis].append(dict(row))
        analysis = {
            "schema_version": "aligned_command_attenuation_analysis_v1",
            "status": "pass",
            "alignment_rule": "same factual_rollout_id/state_key 2x2 predictor-risk mapping under enabled and monitor-only supervisor",
            "strata": aggregates,
            "identified_cells_by_axis": identified_cells,
            "identified_axes": [axis for axis, rows in identified_cells.items() if rows],
            "causal_command_masking_identified": any(identified_cells.values()),
            "trajectory_level_causal_claim_licensed": False,
            "boundary": payload.get("prohibited_overclaim"),
        }
        return payload, analysis
    if payload.get("schema_version") != ALIGNED_SCHEMA_VERSION:
        raise ValueError("Aligned evidence schema is invalid")
    if not isinstance(payload.get("alignment_rule"), str) or not payload["alignment_rule"].strip():
        raise ValueError("Aligned evidence must state its alignment rule")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError("Aligned evidence requires provenance sources")
    for source in sources:
        digest = str(source.get("sha256", ""))
        if len(digest) != 64:
            raise ValueError("Aligned evidence source SHA-256 is malformed")
    analysis = analyze_aligned_attenuation(
        payload.get("records", []), policy_pair=payload.get("policy_pair", [])
    )
    return payload, analysis


def build_analysis(
    root: Path,
    output_path: Path,
    *,
    v3_command_audit_path: Path | None = None,
    aligned_evidence_path: Path | None = None,
) -> dict[str, Any]:
    """Build and atomically write the versioned evidence analysis."""

    root = root.resolve()
    canonical_paths = (
        F1_ROWS,
        CIA_CELLS,
        CIA_CONTRASTS,
        V3_ROWS,
        V3_COMPLETE,
        V3_CONTRASTS,
        R3_COMPLETE,
        R3_FRONTIER,
        R3_RISK_MANIPULATION,
        SF4_ROWS,
        SF4_INFERENCE,
        SF4_COMPLETE,
        TIMING_COMPLETE,
        TIMING_CONTRASTS,
        LEGACY_COMPLETE,
        LEGACY_AUDIT,
        TELEMETRY_COMPLETE,
        TELEMETRY_SOLVER,
        TELEMETRY_ATTENUATION,
    )
    sources = [_source(root, relative) for relative in canonical_paths]

    f1_rows = _read_csv(root / F1_ROWS)
    cia_cells = _read_csv(root / CIA_CELLS)
    cia_contrasts = _read_csv(root / CIA_CONTRASTS)
    v3_rows = _read_json(root / V3_ROWS)
    v3_complete = _read_json(root / V3_COMPLETE)
    v3_contrasts = _read_csv(root / V3_CONTRASTS)
    r3_complete = _read_json(root / R3_COMPLETE)
    r3_frontier = _read_csv(root / R3_FRONTIER)
    r3_risk_manipulation = _read_csv(root / R3_RISK_MANIPULATION)
    sf4_rows = _read_csv(root / SF4_ROWS)
    sf4_inference = _read_json(root / SF4_INFERENCE)
    sf4_complete = _read_json(root / SF4_COMPLETE)
    timing_complete = _read_json(root / TIMING_COMPLETE)
    timing_contrasts = _read_csv(root / TIMING_CONTRASTS)
    legacy_complete = _read_json(root / LEGACY_COMPLETE)
    legacy_audit = _read_json(root / LEGACY_AUDIT)
    telemetry_complete = _read_json(root / TELEMETRY_COMPLETE)
    solver = _read_json(root / TELEMETRY_SOLVER)
    attenuation = _read_json(root / TELEMETRY_ATTENUATION)

    if v3_complete.get("status") != "pass" or len(v3_rows) != 80:
        raise ValueError("V3 canonical completion gate failed")
    if r3_complete.get("status") != "pass" or r3_complete.get("observed_rollouts") != 80:
        raise ValueError("R3 canonical completion gate failed")
    if timing_complete.get("status") != "pass" or timing_complete.get("rollouts") != 120:
        raise ValueError("Timing canonical completion gate failed")
    if telemetry_complete.get("status") != "pass" or attenuation.get("status") != "pass":
        raise ValueError("Telemetry audit gate failed")

    external_v3 = None
    external_source = None
    if v3_command_audit_path is not None:
        if not v3_command_audit_path.is_file():
            raise FileNotFoundError(v3_command_audit_path)
        external_v3 = _read_json(v3_command_audit_path)
        _validate_external_v3(external_v3)
        external_source = {
            "path": str(v3_command_audit_path),
            "sha256": _sha256(v3_command_audit_path),
            "schema_version": external_v3["schema_version"],
            "provenance_records": len(external_v3["source_inventory"]),
            "population_id": "F5_v3_selected_model_closed_loop",
        }

    aligned_payload = None
    aligned_analysis = None
    aligned_source = None
    if aligned_evidence_path is not None:
        if not aligned_evidence_path.is_file():
            raise FileNotFoundError(aligned_evidence_path)
        aligned_payload, aligned_analysis = _load_aligned_evidence(aligned_evidence_path)
        aligned_source = {
            "path": str(aligned_evidence_path),
            "sha256": _sha256(aligned_evidence_path),
            "population_id": aligned_payload.get("population_id"),
        }

    h1 = _build_h1(sf4_rows, sf4_complete, solver)
    h2 = _build_h2(
        f1_rows, cia_cells, cia_contrasts, v3_rows, v3_contrasts, external_v3
    )
    h3 = _build_h3(
        r3_frontier,
        r3_risk_manipulation,
        v3_contrasts,
        sf4_inference,
        timing_contrasts,
        legacy_complete,
        legacy_audit,
        attenuation,
        external_v3,
    )

    aligned_identified = bool(
        aligned_analysis and aligned_analysis.get("causal_command_masking_identified")
    )
    if aligned_analysis and "identified_axes" in aligned_analysis:
        h2_identified = "predictor" in aligned_analysis["identified_axes"]
        h3_identified = "risk" in aligned_analysis["identified_axes"]
    else:
        aligned_pair = set(aligned_payload.get("policy_pair", [])) if aligned_payload else set()
        h2_identified = aligned_identified and aligned_pair == {"B1", "P_star"}
        h3_identified = aligned_identified and aligned_pair == {"adaptive", "fixed_medium"}
    if h2_identified:
        h2["verdict"] = "causally_identified_immediate_command_level_masking"
        h2["causal_masking_identified"] = True
    if h3_identified:
        h3["verdict"] = "causally_identified_immediate_command_level_masking"
        h3["causal_masking_identified"] = True
    identification = {
        "ladder": [
            "retained_upstream_difference",
            "attenuated_candidate_difference",
            "compressed_executed_difference",
            "not_transferred_or_not_identified",
            "consistent_with_masking",
            "causally_identified_command_level_masking",
        ],
        "same_state_alternative_commands_available": aligned_analysis is not None,
        "non_saturated_policy_by_authority_factorial_available": False,
        "authority_off_floor_saturated": True,
        "H2_strongest_licensed_verdict": (
            "causally_identified_command_level_masking"
            if h2_identified
            else "consistent_with_masking"
        ),
        "H3_strongest_licensed_verdict": (
            "causally_identified_command_level_masking"
            if h3_identified
            else "consistent_with_masking"
        ),
        "selective_channel_masking_identified": False,
        "reason": (
            "Aligned immediate-command evidence is present; its scope does not identify long-horizon physical masking or an individual supervisor channel."
            if aligned_analysis is not None
            else "No same-state alternative-policy command mapping exists, and SF4 authority-off physical outcomes are floor-saturated."
        ),
    }
    populations = [
        "F1_foundation_adaptation",
        "F4_capacity_information_architecture_v3",
        "F5_v3_selected_model_closed_loop",
        "F2_r3_predictor_risk",
        "F3_sf4_supervisor_authority",
        "legacy_day10_day11_arrival_timing_synthesis",
        "legacy_day6_target_response_collection",
    ]
    checks = {
        "h1_40_on_0_off_completion": h1["arms"]["on"]["completion_successes"] == 40
        and h1["arms"]["off"]["completion_successes"] == 0,
        "h1_yield_and_collision_totals_reconcile": h1["arms"]["off"]["yield_rule_failures"] == 38
        and h1["arms"]["off"]["adverse_collision_rollouts"] == 21,
        "sf4_solver_paths_reconcile": solver.get("status") == "pass",
        "h2_layers_separately_labelled": all(
            key in h2
            for key in (
                "upstream",
                "in_loop_prediction",
                "candidate_and_executed_control",
                "supervisor_intervention",
                "physical_outcomes",
            )
        ),
        "h3_all_12_frontier_comparisons": h3["r3_full_fixed_frontier"]["declared_comparisons"] == 12,
        "populations_unique_and_not_pooled": len(populations) == len(set(populations))
        and h2["blocks_are_juxtaposed_not_pooled"]
        and h3["blocks_are_juxtaposed_not_pooled"],
        "missing_cross_layer_cells_not_imputed": (
            external_v3 is not None
            or (
                h2["candidate_and_executed_control"]["missing_not_imputed"]
                and h3["v3_constraint_candidate_executed_transfer"]["missing_not_imputed"]
            )
        ),
        "masking_language_respects_identification": not (
            identification["H2_strongest_licensed_verdict"].startswith("causally")
            or identification["H3_strongest_licensed_verdict"].startswith("causally")
        )
        or aligned_identified,
    }
    if not all(checks.values()):
        raise ValueError(f"Supervisor masking evidence audit failed: {checks}")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "independent_unit_policy": "Aggregate repeated steps and target/risk replicates within the declared ego initialisation group before uncertainty estimation.",
        "population_separation": {
            "population_ids": populations,
            "pooling_policy": "juxtapose_only_no_cross_population_estimand",
            "pooled_cross_population_estimates": 0,
        },
        "H1_authority": h1,
        "H2_predictor_transfer": h2,
        "H3_risk_transfer": h3,
        "identification_verdicts": identification,
        "attenuation_summaries": {
            "existing_sf4_factual_authority_mapping": {
                "status": "available_common_authority_effect_only",
                "selective_masking_identified": attenuation["selective_masking_identified"],
                "floor_saturation": attenuation["floor_saturation"],
            },
            "aligned_same_state": aligned_analysis
            if aligned_analysis is not None
            else {
                "status": "unavailable",
                "retention_ratio": None,
                "reason": "same-state alternative commands absent; no denominator is invented",
            },
        },
        "external_audit_input_schema": {
            "schema_version": V3_EXTERNAL_SCHEMA_VERSION,
            "requested": v3_command_audit_path is not None,
            "source": external_source,
            "fail_closed_if_requested_missing_or_invalid": True,
            "identification_boundary": "paired initialisations on different factual trajectories are descriptive, not same-state counterfactuals",
        },
        "aligned_evidence_source": aligned_source,
        "sources": sources,
        "checks": checks,
        "headline_boundary": "H1 is bounded to nominal outcomes in the tested geometry. H2/H3 use causal masking only when aligned command evidence identifies it; otherwise non-transfer, compression and non-identification remain distinct.",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output_path)
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "docs/paper/generated/supervisor_masking_v2/evidence/supervisor_masking_evidence.json"
        ),
    )
    parser.add_argument(
        "--v3-command-audit",
        type=Path,
        help="Optional pulled v3_server_command_transmission_audit_v1 JSON",
    )
    parser.add_argument(
        "--aligned-evidence",
        type=Path,
        help="Optional aligned_supervisor_policy_commands_v1 JSON",
    )
    args = parser.parse_args()
    root = args.root.resolve()

    def resolve(path: Path | None) -> Path | None:
        if path is None:
            return None
        return path if path.is_absolute() else root / path

    result = build_analysis(
        root,
        resolve(args.output),
        v3_command_audit_path=resolve(args.v3_command_audit),
        aligned_evidence_path=resolve(args.aligned_evidence),
    )
    print(json.dumps({"status": result["status"], "checks": result["checks"]}, indent=2))


if __name__ == "__main__":
    main()
