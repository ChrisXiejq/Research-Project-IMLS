#!/usr/bin/env python3
"""Pre-specified paired analysis for the Day 11 timing-shift robustness matrix."""

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
import json
import math
import statistics
from pathlib import Path
from typing import Any

from analyze_day10_closed_loop import (
    PRIMARY_METRICS,
    as_float,
    bootstrap_mean_ci,
    exact_sign_flip_p,
    finite_extreme,
    read_csv,
    read_json,
    weighted_mean,
    write_csv,
)


def load_rollouts(root: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    complete=read_json(root/"DAY11_COMPLETE.json"); audit=read_json(root/"day11_closed_loop_audit.json"); contract=read_json(root/"day11_run_contract.json")
    if complete.get("status")!="pass" or audit.get("status")!="pass": raise ValueError("Day 11 is not complete/audited")
    audit_cells={item["cell_id"]:item for item in audit["evaluations"]}; expected=set(map(int,contract["ego_init_ids"])); rows=[]
    for cell in contract["cells"]:
        cell_dir=root/cell["cell_id"]
        metrics={int(row["initial"]):row for row in read_csv(cell_dir/"df_full.csv")}
        gate=read_json(cell_dir/"postcarla_trajectory_gate.json")
        gates={int(Path(item["scenario_dir"]).name.split("_ego_init_")[1].split("_")[0]):item for item in gate["evaluations"]}
        mechanisms={}
        for row in read_csv(cell_dir/"risk_by_conflict_distance_summary.csv"): mechanisms.setdefault(int(row["initial"]),[]).append(row)
        audited={int(item["ego_init_id"]):item for item in audit_cells[cell["cell_id"]]["rollouts"]}
        if set(metrics)&set(gates)&set(mechanisms)&set(audited)!=expected: raise ValueError(f"Incomplete cell {cell['cell_id']}")
        for init_id in sorted(expected):
            metric=metrics[init_id]; mechanism=mechanisms[init_id]; safety=gates[init_id]["pair_safety"][0]; yield_rule=gates[init_id]["yield_rules"][0]
            start=finite_extreme(mechanism,"sim_time_start_s",min); end=finite_extreme(mechanism,"sim_time_end_s",max); completion=as_float(metric["completion_time"])
            if not math.isclose(start+completion-end,0.0,abs_tol=1e-6): raise ValueError(f"Clock mismatch {cell['cell_id']}/init{init_id}")
            rows.append({
                **{key:cell[key] for key in ("cell_id","predictor","risk_policy","target_style","offset_label","target_offset_m")},
                "ego_init_id":init_id,"completion_time_s":completion,
                "target_clearance_adjusted_completion_delay_s":start+completion-as_float(yield_rule["target_exit_time_s"]),
                "min_footprint_separation_m":as_float(safety["min_footprint_separation_m"]),
                "solver_failure_fraction":as_float(metric["solver_failure_frac"]),
                "supervisor_active_fraction":weighted_mean(mechanism,"supervisor_active_frac"),
                "footprint_collision":as_float(safety["footprint_collision"]),
                "yield_order_valid":as_float(yield_rule["target_clears_before_ego_enters"]),
                "reactive_active_samples":int(audited[init_id]["reactive_active_samples"]),
            })
    if len(rows)!=int(contract["expected_rollouts"]): raise ValueError("Day 11 rollout count mismatch")
    return rows,{"complete":complete,"audit":audit,"contract":contract}


def paired(rows: list[dict[str, Any]], left_filter: dict[str, Any], right_filter: dict[str, Any], pair_fields: tuple[str,...], label: str, inference_scope: str) -> list[dict[str, Any]]:
    def select(filters):
        selected={}
        for row in rows:
            if all(row[key]==value for key,value in filters.items()): selected[tuple(row[key] for key in pair_fields)]=row
        return selected
    left,right=select(left_filter),select(right_filter)
    if set(left)!=set(right) or not left: raise ValueError(f"Unbalanced contrast {label}")
    output=[]
    for metric in PRIMARY_METRICS:
        deltas=[left[key][metric]-right[key][metric] for key in sorted(left)]
        init_position=pair_fields.index("ego_init_id")
        by_init: dict[Any,list[float]]={}
        for key,delta in zip(sorted(left),deltas): by_init.setdefault(key[init_position],[]).append(delta)
        cluster_means=[statistics.fmean(values) for _,values in sorted(by_init.items())]
        low,high=bootstrap_mean_ci(cluster_means,f"day11:init_cluster:{label}:{metric}")
        output.append({"inference_scope":inference_scope,"contrast":label,"metric":metric,"left_minus_right_mean":statistics.fmean(deltas),"ci95_low":low,"ci95_high":high,"exact_init_cluster_sign_flip_p":exact_sign_flip_p(cluster_means),"condition_pairs":len(deltas),"independent_init_groups":len(cluster_means)})
    return output


def difference_in_differences(
    rows: list[dict[str, Any]],
    a_plus: dict[str, Any],
    a_minus: dict[str, Any],
    b_plus: dict[str, Any],
    b_minus: dict[str, Any],
    pair_fields: tuple[str, ...],
    label: str,
    inference_scope: str,
) -> list[dict[str, Any]]:
    def select(filters: dict[str, Any]) -> dict[tuple[Any, ...], dict[str, Any]]:
        return {
            tuple(row[key] for key in pair_fields): row
            for row in rows
            if all(row[key] == value for key, value in filters.items())
        }
    groups=[select(item) for item in (a_plus,a_minus,b_plus,b_minus)]
    keys=set(groups[0])
    if not keys or any(set(group)!=keys for group in groups[1:]): raise ValueError(f"Unbalanced interaction {label}")
    output=[]
    for metric in PRIMARY_METRICS:
        ordered_keys=sorted(keys)
        deltas=[(groups[0][key][metric]-groups[1][key][metric])-(groups[2][key][metric]-groups[3][key][metric]) for key in ordered_keys]
        init_position=pair_fields.index("ego_init_id")
        by_init: dict[Any,list[float]]={}
        for key,delta in zip(ordered_keys,deltas): by_init.setdefault(key[init_position],[]).append(delta)
        cluster_means=[statistics.fmean(values) for _,values in sorted(by_init.items())]
        low,high=bootstrap_mean_ci(cluster_means,f"day11:init_cluster:{label}:{metric}")
        output.append({"inference_scope":inference_scope,"contrast":label,"metric":metric,"left_minus_right_mean":statistics.fmean(deltas),"ci95_low":low,"ci95_high":high,"exact_init_cluster_sign_flip_p":exact_sign_flip_p(cluster_means),"condition_pairs":len(deltas),"independent_init_groups":len(cluster_means)})
    return output


def add_holm_adjustment(contrasts: list[dict[str, Any]]) -> None:
    scopes: dict[str, list[dict[str, Any]]] = {}
    for contrast in contrasts:
        scopes.setdefault(contrast["inference_scope"], []).append(contrast)
    for rows in scopes.values():
        ordered = sorted(rows, key=lambda row: row["exact_init_cluster_sign_flip_p"])
        running = 0.0
        total = len(ordered)
        for rank, row in enumerate(ordered):
            adjusted = min(1.0, (total - rank) * row["exact_init_cluster_sign_flip_p"])
            running = max(running, adjusted)
            row["holm_adjusted_p_within_scope"] = running


def analyze(root: Path, output_dir: Path) -> dict[str, Any]:
    rows,sources=load_rollouts(root); output_dir.mkdir(parents=True,exist_ok=True)
    summaries=[]
    for key in sorted({(r["predictor"],r["risk_policy"],r["target_style"],r["target_offset_m"]) for r in rows}):
        subset=[r for r in rows if (r["predictor"],r["risk_policy"],r["target_style"],r["target_offset_m"])==key]
        summaries.append({"predictor":key[0],"risk_policy":key[1],"target_style":key[2],"target_offset_m":key[3],"rollouts":len(subset),**{f"mean_{metric}":statistics.fmean(r[metric] for r in subset) for metric in PRIMARY_METRICS},"collisions":sum(r["footprint_collision"] for r in subset),"yield_order_failures":sum(1-r["yield_order_valid"] for r in subset)})
    contrasts=[]
    for policy in ("fixed_medium","adaptive"):
        contrasts+=paired(rows,{"predictor":"B1","risk_policy":policy},{"predictor":"B0","risk_policy":policy},("target_style","target_offset_m","ego_init_id"),f"B1_minus_B0__{policy}","predictor_primary")
    for predictor in ("B1","B0"):
        contrasts+=paired(rows,{"predictor":predictor,"risk_policy":"adaptive"},{"predictor":predictor,"risk_policy":"fixed_medium"},("target_style","target_offset_m","ego_init_id"),f"adaptive_minus_fixed_medium__{predictor}","policy_primary")
    # Difference-in-differences across offsets, evaluated for every predictor/policy combination.
    for predictor in ("B1","B0"):
        for policy in ("fixed_medium","adaptive"):
            contrasts+=paired(rows,{"predictor":predictor,"risk_policy":policy,"target_offset_m":3.0},{"predictor":predictor,"risk_policy":policy,"target_offset_m":-3.0},("target_style","ego_init_id"),f"offset_p3_minus_m3__{predictor}__{policy}","offset_primary")
    for policy in ("fixed_medium","adaptive"):
        contrasts+=difference_in_differences(
            rows,
            {"predictor":"B1","risk_policy":policy,"target_offset_m":3.0},
            {"predictor":"B1","risk_policy":policy,"target_offset_m":-3.0},
            {"predictor":"B0","risk_policy":policy,"target_offset_m":3.0},
            {"predictor":"B0","risk_policy":policy,"target_offset_m":-3.0},
            ("target_style","ego_init_id"),f"predictor_x_offset__{policy}","predictor_x_offset_primary",
        )
    for predictor in ("B1","B0"):
        contrasts+=difference_in_differences(
            rows,
            {"predictor":predictor,"risk_policy":"adaptive","target_offset_m":3.0},
            {"predictor":predictor,"risk_policy":"adaptive","target_offset_m":-3.0},
            {"predictor":predictor,"risk_policy":"fixed_medium","target_offset_m":3.0},
            {"predictor":predictor,"risk_policy":"fixed_medium","target_offset_m":-3.0},
            ("target_style","ego_init_id"),f"policy_x_offset__{predictor}","policy_x_offset_primary",
        )
    add_holm_adjustment(contrasts)
    write_csv(output_dir/"day11_rollout_metrics.csv",rows); write_csv(output_dir/"day11_cell_summary.csv",summaries); write_csv(output_dir/"day11_paired_contrasts.csv",contrasts)
    payload={"schema_version":"day11_timing_shift_analysis_v3","status":"pass","analysis_unit":"rollout-condition effects aggregated within ego_init_id before inference; five independent init clusters","rollouts":len(rows),"cells":len(summaries),"primary_metrics":list(PRIMARY_METRICS),"pre_registered_contrasts":contrasts,"multiplicity_control":"Holm family-wise adjustment within each declared inference_scope","statistical_notes":["Effect means use all balanced rollout conditions.","Bootstrap intervals and exact sign-flip p-values operate on five ego-init cluster means, not 20 Hz steps or repeated conditions.","With five init clusters, the smallest attainable two-sided exact p-value is 0.0625 before multiplicity correction."],"safety_gate":{"collisions":sum(r["footprint_collision"] for r in rows),"yield_order_failures":sum(1-r["yield_order_valid"] for r in rows)},"source_contract_schema":sources["contract"]["schema_version"]}
    (output_dir/"day11_analysis_summary.json").write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    return payload


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--results-dir",required=True,type=Path); parser.add_argument("--output-dir",required=True,type=Path); args=parser.parse_args()
    payload=analyze(args.results_dir.resolve(),args.output_dir.resolve()); print(json.dumps({"status":payload["status"],"rollouts":payload["rollouts"],"output_dir":str(args.output_dir.resolve())},indent=2))


if __name__=="__main__": main()
