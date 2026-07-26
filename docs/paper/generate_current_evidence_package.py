#!/usr/bin/env python3
"""Generate paper-oriented evidence tables and SVG figures from current results.

The output is intentionally dependency-free: only the Python standard library is
used so the script can run in the dissertation workspace without matplotlib.
"""

from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path
from collections import Counter


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "core" / "results"
OUT = ROOT / "docs" / "paper" / "generated"
TABLES = OUT / "evidence_tables"
FIGS = OUT / "figures"
DOC = ROOT / "docs" / "paper" / "当前结果证据表与论文图表说明.md"
PAPER_TABLES_DOC = ROOT / "docs" / "paper" / "当前结果论文格式表格.md"
RESULTS_DISCUSSION_DRAFT = ROOT / "docs" / "paper" / "Results_and_Discussion_Draft.md"
PREDICTOR_HISTORY = ROOT / "core" / "scripts" / "models" / "l5kit_multipath_10_carla_finetuned_head_history.json"
PREDICTOR_LOG = ROOT / "core" / "scripts" / "models" / "l5kit_multipath_10_carla_finetuned_head_training_log.csv"


RESULT_PATHS = {
    "supervisor_ablation": RESULTS / "20260725_125938_5init_formal_supervisor_ablation",
    "v10": RESULTS / "20260726_000309_init01_smpc_vs_mpc_v10_executable_approach_brake",
    "v11": RESULTS / "20260726_002752_init01_v11_planner_ownership_fixed_frontier_vs_adaptive",
    "v12": RESULTS / "20260726_004504_init01_v12_close_stop_4p0_fixed_frontier_vs_adaptive",
    "speed_coarse": RESULTS / "20260726_012017_init01_v12_target_speed_sweep",
    "speed_fine": RESULTS / "20260726_130858_init01_v12_target_speed_fine_sweep_around_9p0",
    "a1": RESULTS / "20260726_140716_init01_v12_A1_arrival_gap_sweep",
    "a2": RESULTS / "20260726_152535_init01_v12_A2_phase_ablation_m3p0_p3p0",
    "a3": RESULTS / "20260726_202206_init01_v13_A3_risk_owned_yield",
    "finetuned_validation": RESULTS / "20260718_104740_50init_finetuned_predictor_validation",
}


ARM_LABELS = {
    "smpc_fixed_aggressive": "fixed aggressive",
    "smpc_fixed_medium": "fixed medium",
    "smpc_fixed_conservative": "fixed conservative",
    "smpc_adaptive_floor_weak": "adaptive floor_weak",
    "smpc_adaptive_phase_blind": "adaptive phase-blind",
    "smpc_adaptive_no_preclearance": "adaptive no-pre",
    "smpc_adaptive_no_post_relax": "adaptive no-post",
    "smpc_fixed_risk": "fixed-risk",
    "smpc_var_risk": "adaptive-risk",
}


COLORS = {
    "fixed aggressive": "#D55E00",
    "fixed medium": "#0072B2",
    "fixed conservative": "#009E73",
    "adaptive floor_weak": "#CC79A7",
    "adaptive phase-blind": "#7F7F7F",
    "adaptive no-pre": "#E69F00",
    "adaptive no-post": "#56B4E9",
    "fixed-risk": "#0072B2",
    "adaptive-risk": "#CC79A7",
    "full": "#999999",
    "reduced": "#009E73",
}


def ensure_dirs() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGS.mkdir(parents=True, exist_ok=True)


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_rows(path: Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        rows = []
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def first_row(path: Path) -> dict[str, str]:
    rows = read_rows(path)
    return rows[0] if rows else {}


def fnum(value: object, default: float = math.nan) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def fmt(value: object, digits: int = 3) -> str:
    v = fnum(value)
    if math.isnan(v):
        return ""
    return f"{v:.{digits}f}"


def gate_summary(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, object] = {"gate_status": data.get("overall_status", "")}
    evaluations = data.get("evaluations") or []
    if not evaluations:
        return out
    ev = evaluations[0]
    out["solver_failure_frac_gate"] = ev.get("solver_failure_frac", "")
    pair = (ev.get("pair_safety") or [{}])[0]
    out["min_center_distance_m"] = pair.get("min_center_distance_m", "")
    out["min_footprint_separation_m"] = pair.get("min_footprint_separation_m", "")
    out["footprint_collision"] = pair.get("footprint_collision", "")
    yield_rules = ev.get("yield_rules") or []
    if yield_rules:
        out["target_clears_before_ego_enters"] = yield_rules[0].get(
            "target_clears_before_ego_enters", ""
        )
    return out


def arm_label(arm: str, policy: str = "") -> str:
    if arm in ARM_LABELS:
        return ARM_LABELS[arm]
    if policy in ARM_LABELS:
        return ARM_LABELS[policy]
    return arm


def collect_arm_result(run_dir: Path, arm: str, run_label: str = "") -> dict[str, object]:
    arm_dir = run_dir / arm
    metrics = first_row(arm_dir / "paper_metrics_summary.csv")
    rollout = first_row(arm_dir / "diagnostics_after_supervisor_feedback" / "rollout_diagnostics.csv")
    gate = gate_summary(arm_dir / "postcarla_trajectory_gate.json")
    return {
        "run": run_label or run_dir.name,
        "arm": arm,
        "policy": metrics.get("policy", ""),
        "label": arm_label(arm, metrics.get("policy", "")),
        "gate_status": gate.get("gate_status", ""),
        "completion_time_s": metrics.get("completion_time", ""),
        "solver_failure_frac": metrics.get("solver_failure_frac", gate.get("solver_failure_frac_gate", "")),
        "feasibility_percent": metrics.get("feasibility_percent", ""),
        "first_stop_distance_to_conflict_m": rollout.get("first_stop_distance_to_conflict_m", ""),
        "waiting_time_after_first_stop_s": rollout.get("waiting_time_after_first_stop_s", ""),
        "delay_after_target_clearance_s": rollout.get("delay_after_target_clearance_s", ""),
        "supervisor_active_fraction": rollout.get("supervisor_active_fraction", ""),
        "solver_bypass_fraction": rollout.get("solver_bypass_fraction", ""),
        "infeasible_fraction": rollout.get("infeasible_fraction", ""),
        "mean_abs_final_minus_nominal_accel": rollout.get("mean_abs_final_minus_nominal_accel", ""),
        "dmin_TV": metrics.get("dmin_TV", ""),
        "min_center_distance_m": gate.get("min_center_distance_m", ""),
        "min_footprint_separation_m": gate.get("min_footprint_separation_m", ""),
        "footprint_collision": gate.get("footprint_collision", ""),
        "target_clears_before_ego_enters": gate.get("target_clears_before_ego_enters", ""),
        "forced_reference_linearization_frac": metrics.get("forced_reference_linearization_frac", ""),
    }


def evidence_ledger() -> list[dict[str, object]]:
    return [
        {
            "question": "Q0 early stop source",
            "status": "strong positive",
            "result_dir": str(RESULT_PATHS["supervisor_ablation"].relative_to(ROOT)),
            "main_evidence": "Reduced supervisor moves first stop from about 8.40m to 5.26m and halves waiting/delay.",
            "paper_claim": "Conservative early stopping mainly comes from supervisor/yield logic.",
        },
        {
            "question": "Q1 close-stop baseline safety",
            "status": "strong positive",
            "result_dir": str(RESULT_PATHS["v12"].relative_to(ROOT)),
            "main_evidence": "v12 close-stop 4.0m passes all four SMPC arms; first stop around 4.51-4.55m.",
            "paper_claim": "Closer give-way stopping is feasible after executable SMPC approach braking and planner-ownership stress.",
        },
        {
            "question": "Q2 target-speed fixed-risk failure",
            "status": "negative replication",
            "result_dir": str(RESULT_PATHS["speed_fine"].relative_to(ROOT)),
            "main_evidence": "Coarse 9.0m/s fixed-conservative failure did not reproduce; fine sweep 16/16 PASS.",
            "paper_claim": "Speed-only difficulty is not sufficient main proof of adaptive advantage.",
        },
        {
            "question": "Q3 arrival-gap hard subset",
            "status": "mixed / limitation",
            "result_dir": str(RESULT_PATHS["a1"].relative_to(ROOT)),
            "main_evidence": "A1 20/20 PASS; adaptive fastest at m3p0 but lowest margin; safest at p3p0 but slower.",
            "paper_claim": "Arrival timing exposes trade-offs but not stable fixed-risk failure.",
        },
        {
            "question": "Q4 phase-aware adaptive mechanism",
            "status": "negative mechanism ablation",
            "result_dir": str(RESULT_PATHS["a2"].relative_to(ROOT)),
            "main_evidence": "Phase-blind is faster with similar margin at p3p0; fixed medium beats full adaptive at m3p0.",
            "paper_claim": "Phase-aware risk is visible in logs but not necessary for current final metrics.",
        },
        {
            "question": "Q5 predictor sanity",
            "status": "partially complete",
            "result_dir": str(RESULT_PATHS["finetuned_validation"].relative_to(ROOT)),
            "main_evidence": "Closed-loop 50-init fine-tuned validation exists; paper still needs ADE/FDE/mode ranking table.",
            "paper_claim": "Use predictor results as sanity support, not as the main contribution.",
        },
        {
            "question": "Q6 infeasibility phase",
            "status": "partially complete",
            "result_dir": str((RESULT_PATHS["supervisor_ablation"] / "formal_supervisor_ablation_analysis").relative_to(ROOT)),
            "main_evidence": "Existing infeasibility summary places failures mainly in critical/pre-clearance phases.",
            "paper_claim": "Solver infeasibility and final closed-loop safety must be reported separately.",
        },
        {
            "question": "Q7 risk-owned-yield / supervisor authority",
            "status": "high-value limitation",
            "result_dir": str(RESULT_PATHS["a3"].relative_to(ROOT)),
            "main_evidence": "A3 12/12 PASS and risk-owned-yield active, but fixed frontier remains competitive.",
            "paper_claim": "Planner risk contribution depends on supervisor authority; adaptive is not universally dominant.",
        },
    ]


def collect_supervisor_table() -> list[dict[str, object]]:
    src = RESULT_PATHS["supervisor_ablation"] / "formal_supervisor_ablation_analysis" / "supervisor_ablation_aggregate.csv"
    rows = read_rows(src)
    return [
        {
            "supervisor_mode": r["supervisor_mode"],
            "policy": r["policy"],
            "n_rollouts": r["n_rollouts"],
            "first_stop_distance_to_conflict_m": r["first_stop_distance_to_conflict_m"],
            "waiting_time_after_first_stop_s": r["waiting_time_after_first_stop_s"],
            "delay_after_target_clearance_s": r["delay_after_target_clearance_s"],
            "supervisor_active_fraction": r["supervisor_active_fraction"],
            "infeasible_fraction": r["infeasible_fraction"],
            "mean_abs_final_minus_nominal_accel": r["mean_abs_final_minus_nominal_accel"],
        }
        for r in rows
    ]


def collect_baseline_progression() -> list[dict[str, object]]:
    specs = [
        ("v10 executable approach braking", RESULT_PATHS["v10"], ["smpc_fixed_medium", "smpc_adaptive_floor_weak"]),
        ("v11 planner-ownership stress", RESULT_PATHS["v11"], ["smpc_fixed_aggressive", "smpc_fixed_medium", "smpc_fixed_conservative", "smpc_adaptive_floor_weak"]),
        ("v12 close-stop 4.0m", RESULT_PATHS["v12"], ["smpc_fixed_aggressive", "smpc_fixed_medium", "smpc_fixed_conservative", "smpc_adaptive_floor_weak"]),
    ]
    rows: list[dict[str, object]] = []
    for label, run_dir, arms in specs:
        for arm in arms:
            row = collect_arm_result(run_dir, arm, label)
            rows.append(row)
    return rows


def read_sweep_summary(run_key: str, summary_name: str) -> list[dict[str, str]]:
    path = RESULT_PATHS[run_key] / summary_name
    return read_rows(path)


def collect_a3_authority() -> list[dict[str, object]]:
    run_dir = RESULT_PATHS["a3"]
    rows: list[dict[str, object]] = []
    for arm_dir in sorted(p for p in run_dir.glob("arrival_offset_*/smpc_*") if p.is_dir()):
        debug_paths = list(arm_dir.glob("*/smpc_debug_steps.jsonl"))
        n = active = applied = direct = hard = emergency = risk_owned = 0
        if debug_paths:
            with debug_paths[0].open(encoding="utf-8") as f:
                for line in f:
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ys = d.get("yield_stop_supervisor") or {}
                    n += 1
                    risk_owned += int(bool(ys.get("risk_owned_yield_enabled")))
                    active += int(bool(ys.get("active")))
                    app = ys.get("applied")
                    if app:
                        applied += 1
                        direct += int(bool(app.get("direct_takeover_required")))
                        hard += int(bool(app.get("hard_stop_required")))
                        emergency += int(bool((app.get("emergency_brake") or {}).get("active")))
        frac = lambda x: x / n if n else math.nan
        rows.append(
            {
                "difficulty": arm_dir.parent.name,
                "arm": arm_dir.name,
                "risk_owned_yield_enabled_frac": frac(risk_owned),
                "yield_active_frac": frac(active),
                "yield_applied_frac": frac(applied),
                "direct_takeover_frac": frac(direct),
                "hard_stop_frac": frac(hard),
                "emergency_brake_active_frac": frac(emergency),
            }
        )
    return rows


def collect_predictor_closed_loop_table() -> list[dict[str, object]]:
    rows = read_rows(RESULT_PATHS["finetuned_validation"] / "paper_metrics_summary.csv")
    out = []
    for r in rows:
        out.append(
            {
                "policy": r.get("policy", ""),
                "completion_time_s": r.get("completion_time", ""),
                "solver_failure_frac": r.get("solver_failure_frac", ""),
                "dmin_TV": r.get("dmin_TV", ""),
                "completion_valid": r.get("completion_valid", ""),
                "note": "Closed-loop validation only; add ADE/FDE and mode-ranking metrics before final paper submission.",
            }
        )
    return out


def collect_predictor_final_table() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    history = {}
    if PREDICTOR_HISTORY.exists():
        history = json.loads(PREDICTOR_HISTORY.read_text(encoding="utf-8"))
    hist = history.get("history") or {}
    val_top = hist.get("val_top_mode_ADE") or []
    train_top = hist.get("top_mode_ADE") or []
    val_loss = hist.get("val_loss") or []
    if val_top:
        best_epoch = min(range(len(val_top)), key=lambda i: val_top[i])
        rows.extend(
            [
                {
                    "evidence_item": "validation top-mode ADE",
                    "split_or_scope": "validation",
                    "value": val_top[best_epoch],
                    "unit": "m",
                    "source": str(PREDICTOR_HISTORY.relative_to(ROOT)),
                    "paper_use": "Shows the fine-tuned prediction head fits the held-out CARLA validation split.",
                    "limitation": "This is top-mode ADE from training history, not a full test-set predictor benchmark.",
                },
                {
                    "evidence_item": "best validation epoch",
                    "split_or_scope": "validation",
                    "value": best_epoch,
                    "unit": "epoch",
                    "source": str(PREDICTOR_HISTORY.relative_to(ROOT)),
                    "paper_use": "Documents the selected fine-tuned checkpoint.",
                    "limitation": "Selection is based on validation top-mode ADE only.",
                },
            ]
        )
    if train_top:
        rows.append(
            {
                "evidence_item": "final training top-mode ADE",
                "split_or_scope": "train",
                "value": train_top[-1],
                "unit": "m",
                "source": str(PREDICTOR_HISTORY.relative_to(ROOT)),
                "paper_use": "Sanity check that fine-tuning converged.",
                "limitation": "Training metric cannot be used as generalization evidence.",
            }
        )
    if val_loss:
        rows.append(
            {
                "evidence_item": "final validation loss",
                "split_or_scope": "validation",
                "value": val_loss[-1],
                "unit": "loss",
                "source": str(PREDICTOR_HISTORY.relative_to(ROOT)),
                "paper_use": "Secondary convergence evidence.",
                "limitation": "Loss scale is model-specific.",
            }
        )
    for key, label in [
        ("train_count_full_horizon", "full-horizon train samples"),
        ("val_count_full_horizon", "full-horizon validation samples"),
    ]:
        if key in history:
            rows.append(
                {
                    "evidence_item": label,
                    "split_or_scope": key.replace("_count_full_horizon", ""),
                    "value": history[key],
                    "unit": "samples",
                    "source": str(PREDICTOR_HISTORY.relative_to(ROOT)),
                    "paper_use": "Documents dataset size used for fine-tuning sanity.",
                    "limitation": "Does not replace a separate held-out test set report.",
                }
            )
    rows.extend(
        [
            {
                "evidence_item": "top1 FDE / minFDE",
                "split_or_scope": "test",
                "value": "MISSING",
                "unit": "m",
                "source": "not found locally",
                "paper_use": "Required before final submission if predictor quality is challenged.",
                "limitation": "Do not claim final predictor benchmark until generated.",
            },
            {
                "evidence_item": "minADE / mode ranking / calibration",
                "split_or_scope": "test",
                "value": "MISSING",
                "unit": "mixed",
                "source": "not found locally",
                "paper_use": "Required to discuss multimodal ranking reliability.",
                "limitation": "Current dissertation can only use predictor as sanity support.",
            },
            {
                "evidence_item": "train/val/test split integrity",
                "split_or_scope": "dataset",
                "value": "MISSING_LOCAL_MANIFEST",
                "unit": "check",
                "source": "prediction_dataset_merged/manifest.json not found locally",
                "paper_use": "Required to rule out leakage.",
                "limitation": "Mention as pending if the manifest is not pulled/generated.",
            },
        ]
    )
    return rows


def phase_summary_from_infeasible(path: Path) -> tuple[int, str]:
    rows = read_rows(path)
    if not rows:
        return 0, "no infeasible steps logged"
    counter: Counter[str] = Counter()
    for row in rows:
        phase = row.get("phase_bucket") or "unknown"
        yield_phase = row.get("yield_phase") or "unknown"
        counter[f"{phase} / {yield_phase}"] += 1
    return len(rows), "; ".join(f"{name}: {count}" for name, count in counter.most_common(3))


def infer_arm_dir_from_summary(run_dir: Path, difficulty: str, arm: str) -> Path:
    direct = run_dir / difficulty / arm
    if direct.exists():
        return direct
    return run_dir / arm


def collect_infeasibility_final_table() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    # Runs with direct per-arm directories and diagnostic files.
    for run_label, run_key, arms in [
        (
            "v12 close-stop baseline",
            "v12",
            ["smpc_fixed_aggressive", "smpc_fixed_medium", "smpc_fixed_conservative", "smpc_adaptive_floor_weak"],
        )
    ]:
        for arm in arms:
            arm_dir = RESULT_PATHS[run_key] / arm
            metrics = first_row(arm_dir / "paper_metrics_summary.csv")
            gate = gate_summary(arm_dir / "postcarla_trajectory_gate.json")
            count, phase = phase_summary_from_infeasible(
                arm_dir / "diagnostics_after_supervisor_feedback" / "infeasible_steps.csv"
            )
            rows.append(
                {
                    "run": run_label,
                    "difficulty": "init01",
                    "arm": arm,
                    "gate_status": gate.get("gate_status", ""),
                    "solver_failure_frac": metrics.get("solver_failure_frac", ""),
                    "feasibility_percent": metrics.get("feasibility_percent", ""),
                    "infeasible_steps_logged": count,
                    "dominant_infeasible_phase": phase,
                    "final_safety_interpretation": "PASS gate; solver failures are low and phase-localized.",
                }
            )

    # Sweep summaries where per-step phase diagnostics were not generated in the run folders.
    for run_label, run_key, summary_name in [
        ("fine target-speed sweep", "speed_fine", "v12_target_speed_sweep_summary.csv"),
        ("A1 arrival-gap sweep", "a1", "v12_claim_sweep_summary.csv"),
        ("A2 phase ablation", "a2", "v12_claim_sweep_summary.csv"),
        ("A3 risk-owned-yield", "a3", "v12_claim_sweep_summary.csv"),
    ]:
        for r in read_sweep_summary(run_key, summary_name):
            arm_dir = infer_arm_dir_from_summary(
                RESULT_PATHS[run_key],
                r.get("difficulty", ""),
                r.get("arm", ""),
            )
            metrics = first_row(arm_dir / "paper_metrics_summary.csv")
            gate = gate_summary(arm_dir / "postcarla_trajectory_gate.json")
            solver_failure_frac = (
                r.get("solver_failure_frac")
                or metrics.get("solver_failure_frac")
                or gate.get("solver_failure_frac_gate", "")
            )
            feasibility_percent = r.get("feasibility_percent") or metrics.get("feasibility_percent", "")
            rows.append(
                {
                    "run": run_label,
                    "difficulty": r.get("difficulty", ""),
                    "arm": r.get("arm", ""),
                    "gate_status": r.get("gate_status", gate.get("gate_status", "")),
                    "solver_failure_frac": solver_failure_frac,
                    "feasibility_percent": feasibility_percent,
                    "infeasible_steps_logged": "",
                    "dominant_infeasible_phase": "phase_not_logged_in_this_sweep_summary",
                    "final_safety_interpretation": "Use solver_failure_frac with post-CARLA gate; do not infer phase without per-step diagnostics.",
                }
            )
    return rows


def scale(values: list[float], lo_px: float, hi_px: float, pad: float = 0.08):
    clean = [v for v in values if not math.isnan(v)]
    if not clean:
        return lambda _: (lo_px + hi_px) / 2
    lo, hi = min(clean), max(clean)
    if abs(hi - lo) < 1e-9:
        lo -= 1.0
        hi += 1.0
    span = hi - lo
    lo -= span * pad
    hi += span * pad
    return lambda v: hi_px - (v - lo) / (hi - lo) * (hi_px - lo_px)


def svg_header(width: int, height: int) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Arial,Helvetica,sans-serif;font-size:12px;fill:#222}.title{font-size:16px;font-weight:bold}.axis{stroke:#333;stroke-width:1}.grid{stroke:#ddd;stroke-width:1}.label{font-size:11px}.legend{font-size:11px}</style>',
    ]


def write_svg(path: Path, parts: list[str]) -> None:
    path.write_text("\n".join(parts + ["</svg>\n"]), encoding="utf-8")


def bar_chart(path: Path, title: str, rows: list[dict[str, object]], value_key: str, group_key: str, series_key: str, ylabel: str) -> None:
    width, height = 860, 440
    margin = dict(left=70, right=30, top=55, bottom=90)
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    groups = list(dict.fromkeys(str(r[group_key]) for r in rows))
    series = list(dict.fromkeys(str(r[series_key]) for r in rows))
    values = [fnum(r[value_key]) for r in rows]
    max_v = max([v for v in values if not math.isnan(v)] or [1.0])
    y = lambda v: margin["top"] + plot_h - (v / (max_v * 1.15)) * plot_h
    parts = svg_header(width, height)
    parts += [
        f'<text x="{width/2}" y="28" text-anchor="middle" class="title">{html.escape(title)}</text>',
        f'<line x1="{margin["left"]}" y1="{margin["top"]+plot_h}" x2="{width-margin["right"]}" y2="{margin["top"]+plot_h}" class="axis"/>',
        f'<line x1="{margin["left"]}" y1="{margin["top"]}" x2="{margin["left"]}" y2="{margin["top"]+plot_h}" class="axis"/>',
        f'<text x="18" y="{margin["top"]+plot_h/2}" transform="rotate(-90 18 {margin["top"]+plot_h/2})" text-anchor="middle">{html.escape(ylabel)}</text>',
    ]
    for t in range(5):
        v = max_v * t / 4
        yy = y(v)
        parts.append(f'<line x1="{margin["left"]}" y1="{yy:.1f}" x2="{width-margin["right"]}" y2="{yy:.1f}" class="grid"/>')
        parts.append(f'<text x="{margin["left"]-8}" y="{yy+4:.1f}" text-anchor="end" class="label">{v:.1f}</text>')
    group_w = plot_w / max(len(groups), 1)
    bar_w = group_w / (len(series) + 1.2)
    lookup = {(str(r[group_key]), str(r[series_key])): r for r in rows}
    for gi, group in enumerate(groups):
        gx = margin["left"] + gi * group_w
        for si, serie in enumerate(series):
            r = lookup.get((group, serie))
            if not r:
                continue
            v = fnum(r[value_key], 0.0)
            x = gx + (si + 0.6) * bar_w
            yy = y(v)
            h = margin["top"] + plot_h - yy
            color = COLORS.get(serie, COLORS.get(group, "#666"))
            parts.append(f'<rect x="{x:.1f}" y="{yy:.1f}" width="{bar_w*0.82:.1f}" height="{h:.1f}" fill="{color}"/>')
        parts.append(f'<text x="{gx+group_w/2:.1f}" y="{height-52}" text-anchor="middle" class="label">{html.escape(group)}</text>')
    lx, ly = margin["left"], height - 28
    for i, serie in enumerate(series):
        color = COLORS.get(serie, "#666")
        x = lx + i * 150
        parts.append(f'<rect x="{x}" y="{ly-10}" width="12" height="12" fill="{color}"/>')
        parts.append(f'<text x="{x+17}" y="{ly}" class="legend">{html.escape(serie)}</text>')
    write_svg(path, parts)


def scatter_chart(path: Path, title: str, rows: list[dict[str, object]], x_key: str, y_key: str, label_key: str, group_key: str, xlabel: str, ylabel: str) -> None:
    width, height = 860, 520
    margin = dict(left=75, right=45, top=55, bottom=75)
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    xs = [fnum(r[x_key]) for r in rows]
    ys = [fnum(r[y_key]) for r in rows]
    x_clean = [v for v in xs if not math.isnan(v)]
    y_clean = [v for v in ys if not math.isnan(v)]
    if not x_clean or not y_clean:
        return
    xmin, xmax = min(x_clean), max(x_clean)
    ymin, ymax = min(y_clean), max(y_clean)
    xpad = max((xmax - xmin) * 0.08, 0.2)
    ypad = max((ymax - ymin) * 0.08, 0.05)
    xmin -= xpad
    xmax += xpad
    ymin -= ypad
    ymax += ypad
    xmap = lambda v: margin["left"] + (v - xmin) / (xmax - xmin) * plot_w
    ymap = lambda v: margin["top"] + plot_h - (v - ymin) / (ymax - ymin) * plot_h
    parts = svg_header(width, height)
    parts += [
        f'<text x="{width/2}" y="28" text-anchor="middle" class="title">{html.escape(title)}</text>',
        f'<line x1="{margin["left"]}" y1="{margin["top"]+plot_h}" x2="{width-margin["right"]}" y2="{margin["top"]+plot_h}" class="axis"/>',
        f'<line x1="{margin["left"]}" y1="{margin["top"]}" x2="{margin["left"]}" y2="{margin["top"]+plot_h}" class="axis"/>',
        f'<text x="{margin["left"]+plot_w/2}" y="{height-26}" text-anchor="middle">{html.escape(xlabel)}</text>',
        f'<text x="20" y="{margin["top"]+plot_h/2}" transform="rotate(-90 20 {margin["top"]+plot_h/2})" text-anchor="middle">{html.escape(ylabel)}</text>',
    ]
    for t in range(5):
        xv = xmin + (xmax - xmin) * t / 4
        yv = ymin + (ymax - ymin) * t / 4
        xx = xmap(xv)
        yy = ymap(yv)
        parts.append(f'<line x1="{xx:.1f}" y1="{margin["top"]}" x2="{xx:.1f}" y2="{margin["top"]+plot_h}" class="grid"/>')
        parts.append(f'<line x1="{margin["left"]}" y1="{yy:.1f}" x2="{width-margin["right"]}" y2="{yy:.1f}" class="grid"/>')
        parts.append(f'<text x="{xx:.1f}" y="{margin["top"]+plot_h+18}" text-anchor="middle" class="label">{xv:.1f}</text>')
        parts.append(f'<text x="{margin["left"]-8}" y="{yy+4:.1f}" text-anchor="end" class="label">{yv:.2f}</text>')
    for r in rows:
        x, yv = fnum(r[x_key]), fnum(r[y_key])
        if math.isnan(x) or math.isnan(yv):
            continue
        group = str(r[group_key])
        label = str(r[label_key])
        color = COLORS.get(group, "#444")
        xx, yy = xmap(x), ymap(yv)
        parts.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="5.5" fill="{color}" opacity="0.85"/>')
        parts.append(f'<text x="{xx+7:.1f}" y="{yy-7:.1f}" class="label">{html.escape(label)}</text>')
    legend_groups = list(dict.fromkeys(str(r[group_key]) for r in rows))
    for i, group in enumerate(legend_groups):
        x = margin["left"] + i * 165
        y = height - 8
        parts.append(f'<rect x="{x}" y="{y-11}" width="12" height="12" fill="{COLORS.get(group, "#444")}"/>')
        parts.append(f'<text x="{x+17}" y="{y}" class="legend">{html.escape(group)}</text>')
    write_svg(path, parts)


def line_chart(path: Path, title: str, rows: list[dict[str, object]], x_key: str, y_key: str, series_key: str, xlabel: str, ylabel: str) -> None:
    width, height = 860, 480
    margin = dict(left=75, right=45, top=55, bottom=75)
    plot_w = width - margin["left"] - margin["right"]
    plot_h = height - margin["top"] - margin["bottom"]
    xs = [fnum(r[x_key]) for r in rows]
    ys = [fnum(r[y_key]) for r in rows]
    clean_x = [x for x in xs if not math.isnan(x)]
    clean_y = [y for y in ys if not math.isnan(y)]
    if not clean_x or not clean_y:
        return
    xmin, xmax = min(clean_x), max(clean_x)
    ymin, ymax = min(clean_y), max(clean_y)
    ypad = max((ymax - ymin) * 0.1, 0.05)
    ymin -= ypad
    ymax += ypad
    xmap = lambda v: margin["left"] + (v - xmin) / (xmax - xmin or 1.0) * plot_w
    ymap = lambda v: margin["top"] + plot_h - (v - ymin) / (ymax - ymin) * plot_h
    parts = svg_header(width, height)
    parts += [
        f'<text x="{width/2}" y="28" text-anchor="middle" class="title">{html.escape(title)}</text>',
        f'<line x1="{margin["left"]}" y1="{margin["top"]+plot_h}" x2="{width-margin["right"]}" y2="{margin["top"]+plot_h}" class="axis"/>',
        f'<line x1="{margin["left"]}" y1="{margin["top"]}" x2="{margin["left"]}" y2="{margin["top"]+plot_h}" class="axis"/>',
        f'<text x="{margin["left"]+plot_w/2}" y="{height-25}" text-anchor="middle">{html.escape(xlabel)}</text>',
        f'<text x="20" y="{margin["top"]+plot_h/2}" transform="rotate(-90 20 {margin["top"]+plot_h/2})" text-anchor="middle">{html.escape(ylabel)}</text>',
    ]
    series = list(dict.fromkeys(str(r[series_key]) for r in rows))
    for s in series:
        pts = sorted((fnum(r[x_key]), fnum(r[y_key])) for r in rows if str(r[series_key]) == s)
        pts = [(x, y) for x, y in pts if not math.isnan(x) and not math.isnan(y)]
        if not pts:
            continue
        color = COLORS.get(s, "#444")
        d = " ".join(f"{xmap(x):.1f},{ymap(y):.1f}" for x, y in pts)
        parts.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="2"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{xmap(x):.1f}" cy="{ymap(y):.1f}" r="4.5" fill="{color}"/>')
    for i, s in enumerate(series):
        x = margin["left"] + i * 165
        y = height - 7
        parts.append(f'<rect x="{x}" y="{y-11}" width="12" height="12" fill="{COLORS.get(s, "#444")}"/>')
        parts.append(f'<text x="{x+17}" y="{y}" class="legend">{html.escape(s)}</text>')
    write_svg(path, parts)


def markdown_table(rows: list[dict[str, object]], cols: list[str], max_rows: int | None = None) -> str:
    numeric_cols = {
        "completion_time",
        "completion_time_s",
        "solver_failure_frac",
        "feasibility_percent",
        "first_stop_distance_to_conflict_m",
        "waiting_time_after_first_stop_s",
        "delay_after_target_clearance_s",
        "supervisor_active_fraction",
        "yield_active_frac",
        "direct_takeover_frac",
        "emergency_brake_active_frac",
        "risk_owned_yield_enabled_frac",
        "min_footprint_separation_m",
        "critical_pre_tightening",
        "near_post_tightening",
        "dmin_TV",
    }
    show = rows if max_rows is None else rows[:max_rows]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for r in show:
        vals = []
        for c in cols:
            v = r.get(c, "")
            if c == "value" and str(r.get("unit", "")) in {"m", "loss"} and not math.isnan(fnum(v)):
                vals.append(fmt(v))
            elif c in numeric_cols and not math.isnan(fnum(v)):
                vals.append(fmt(v))
            elif isinstance(v, float):
                vals.append(fmt(v))
            else:
                vals.append(str(v))
        lines.append("| " + " | ".join(vals) + " |")
    if max_rows is not None and len(rows) > max_rows:
        lines.append(f"| ... | ... | ... | ... | ... |")
    return "\n".join(lines)


def make_outputs() -> None:
    ensure_dirs()

    ledger = evidence_ledger()
    supervisor = collect_supervisor_table()
    baseline = collect_baseline_progression()
    speed_fine = read_sweep_summary("speed_fine", "v12_target_speed_sweep_summary.csv")
    a1 = read_sweep_summary("a1", "v12_claim_sweep_summary.csv")
    a2 = read_sweep_summary("a2", "v12_claim_sweep_summary.csv")
    a3 = read_sweep_summary("a3", "v12_claim_sweep_summary.csv")
    a3_authority = collect_a3_authority()
    predictor_closed_loop = collect_predictor_closed_loop_table()
    predictor_final = collect_predictor_final_table()
    infeasibility_final = collect_infeasibility_final_table()
    infeasibility = read_rows(
        RESULT_PATHS["supervisor_ablation"]
        / "formal_supervisor_ablation_analysis"
        / "infeasibility_phase_summary.csv"
    )

    write_rows(TABLES / "evidence_ledger.csv", ledger)
    write_rows(TABLES / "supervisor_ablation_table.csv", supervisor)
    write_rows(TABLES / "baseline_progression_table.csv", baseline)
    write_rows(TABLES / "target_speed_fine_sweep_table.csv", speed_fine)
    write_rows(TABLES / "arrival_gap_a1_table.csv", a1)
    write_rows(TABLES / "phase_ablation_a2_table.csv", a2)
    write_rows(TABLES / "risk_owned_yield_a3_table.csv", a3)
    write_rows(TABLES / "a3_authority_metrics_table.csv", a3_authority)
    write_rows(TABLES / "infeasibility_phase_table.csv", infeasibility)
    write_rows(TABLES / "infeasibility_final_table.csv", infeasibility_final)
    write_rows(TABLES / "predictor_closed_loop_sanity_table.csv", predictor_closed_loop)
    write_rows(TABLES / "predictor_sanity_final_table.csv", predictor_final)

    supervisor_plot_rows = []
    for r in supervisor:
        supervisor_plot_rows.append({**r, "series": r["policy"], "group": r["supervisor_mode"]})
    bar_chart(
        FIGS / "fig_01_supervisor_first_stop.svg",
        "Supervisor ablation: first stop distance",
        supervisor_plot_rows,
        "first_stop_distance_to_conflict_m",
        "group",
        "series",
        "distance to conflict (m)",
    )
    bar_chart(
        FIGS / "fig_02_supervisor_wait_delay.svg",
        "Supervisor ablation: waiting time",
        supervisor_plot_rows,
        "waiting_time_after_first_stop_s",
        "group",
        "series",
        "seconds",
    )

    baseline_for_scatter = [
        r for r in baseline if r["run"] in {"v11 planner-ownership stress", "v12 close-stop 4.0m"}
    ]
    scatter_chart(
        FIGS / "fig_03_v11_v12_frontier_scatter.svg",
        "v11/v12 fixed frontier vs adaptive: completion vs footprint margin",
        baseline_for_scatter,
        "completion_time_s",
        "min_footprint_separation_m",
        "label",
        "label",
        "completion time (s)",
        "min footprint separation (m)",
    )

    a1_plot = [
        {
            **r,
            "label": r["difficulty"].replace("arrival_offset_", ""),
            "group": arm_label(r["arm"], r.get("policy", "")),
        }
        for r in a1
        if r.get("arm") in {"smpc_fixed_aggressive", "smpc_fixed_medium", "smpc_fixed_conservative", "smpc_adaptive_floor_weak"}
    ]
    scatter_chart(
        FIGS / "fig_04_a1_arrival_gap_frontier.svg",
        "A1 arrival-gap sweep: completion vs footprint margin",
        a1_plot,
        "completion_time",
        "min_footprint_separation_m",
        "label",
        "group",
        "completion time (s)",
        "min footprint separation (m)",
    )

    a2_plot = [
        {
            **r,
            "label": r["difficulty"].replace("arrival_offset_", ""),
            "group": arm_label(r["arm"], r.get("policy", "")),
        }
        for r in a2
    ]
    scatter_chart(
        FIGS / "fig_05_a2_mechanism_ablation.svg",
        "A2 phase/mechanism ablation: completion vs footprint margin",
        a2_plot,
        "completion_time",
        "min_footprint_separation_m",
        "label",
        "group",
        "completion time (s)",
        "min footprint separation (m)",
    )

    a3_plot = [
        {
            **r,
            "label": r["difficulty"].replace("arrival_offset_", ""),
            "group": arm_label(r["arm"], r.get("policy", "")),
        }
        for r in a3
    ]
    scatter_chart(
        FIGS / "fig_06_a3_risk_owned_yield.svg",
        "A3 risk-owned-yield: completion vs footprint margin",
        a3_plot,
        "completion_time",
        "min_footprint_separation_m",
        "label",
        "group",
        "completion time (s)",
        "min footprint separation (m)",
    )

    speed_plot = [
        {
            **r,
            "target_speed_float": fnum(r.get("target_speed")),
            "group": arm_label(r["arm"], r.get("policy", "")),
        }
        for r in speed_fine
    ]
    line_chart(
        FIGS / "fig_07_speed_fine_completion.svg",
        "Fine target-speed sweep: completion time",
        speed_plot,
        "target_speed_float",
        "completion_time",
        "group",
        "target speed (m/s)",
        "completion time (s)",
    )

    a3_auth_plot = [{**r, "group": arm_label(r["arm"]), "label": r["difficulty"].replace("arrival_offset_", "")} for r in a3_authority]
    scatter_chart(
        FIGS / "fig_08_a3_authority_vs_margin.svg",
        "A3 authority: yield-active fraction vs footprint margin",
        [
            {
                **r,
                "min_footprint_separation_m": next(
                    (
                        ar["min_footprint_separation_m"]
                        for ar in a3
                        if ar["difficulty"] == r["difficulty"] and ar["arm"] == r["arm"]
                    ),
                    "",
                ),
            }
            for r in a3_auth_plot
        ],
        "yield_active_frac",
        "min_footprint_separation_m",
        "label",
        "group",
        "yield active fraction",
        "min footprint separation (m)",
    )

    write_document(
        ledger=ledger,
        supervisor=supervisor,
        baseline=baseline,
        speed_fine=speed_fine,
        a1=a1,
        a2=a2,
        a3=a3,
        a3_authority=a3_authority,
        predictor_closed_loop=predictor_closed_loop,
        predictor_final=predictor_final,
        infeasibility=infeasibility,
        infeasibility_final=infeasibility_final,
    )
    write_paper_tables_document(
        ledger=ledger,
        supervisor=supervisor,
        baseline=baseline,
        speed_fine=speed_fine,
        a1=a1,
        a2=a2,
        a3=a3,
        a3_authority=a3_authority,
        predictor_final=predictor_final,
        infeasibility_final=infeasibility_final,
    )
    write_results_discussion_draft(
        supervisor=supervisor,
        baseline=baseline,
        speed_fine=speed_fine,
        a1=a1,
        a2=a2,
        a3=a3,
        a3_authority=a3_authority,
        predictor_final=predictor_final,
        infeasibility_final=infeasibility_final,
    )


def rel(path: Path) -> str:
    return str(path.relative_to(DOC.parent))


def figure_md(filename: str, caption: str) -> str:
    return f"![{caption}]({rel(FIGS / filename)})\n\n*{caption}*"


def write_document(**data: list[dict[str, object]]) -> None:
    ledger = data["ledger"]
    supervisor = data["supervisor"]
    baseline = data["baseline"]
    a1 = data["a1"]
    a2 = data["a2"]
    a3 = data["a3"]
    a3_authority = data["a3_authority"]
    speed_fine = data["speed_fine"]
    predictor_closed_loop = data["predictor_closed_loop"]
    predictor_final = data["predictor_final"]
    infeasibility = data["infeasibility"]
    infeasibility_final = data["infeasibility_final"]

    doc = f"""# 当前结果证据表与论文图表说明

本文档把当前 dissertation 的已完成结果整理成论文 Results/Discussion 可用的 evidence tables 和 figures。它不替代主指导书；主指导书仍是 `论文实验与写作统一指导.md`。本文档的作用是把“现有哪些证据、每张表/图服务哪个论点、哪些 claim 不能写”收束到一处。

## 1. 当前论文主线

推荐主线不是 `adaptive-risk SMPC universally dominates fixed-risk SMPC`，而是：

```text
Risk-aware SMPC under rule-aware safety supervision:
when does adaptive risk allocation affect closed-loop behaviour,
and when is it hidden by the supervisor's nominal yield authority?
```

当前最稳的总判断：

- 系统性正结果：supervisor diagnosis 和 v12 close-stop baseline 是强证据。
- fixed/adaptive 对比结果：fixed-risk frontier 很强，adaptive-risk 没有稳定 final-metric dominance。
- 研究价值：A1/A2/A3 把问题推进到 supervisor authority / risk ownership，而不是单纯参数胜负。
- 论文写法：强调 risk-aware planner 的贡献必须和 runtime safety authority 一起评价。

## 2. Evidence Ledger

CSV: [`evidence_ledger.csv`]({rel(TABLES / "evidence_ledger.csv")})

{markdown_table(ledger, ["question", "status", "main_evidence", "paper_claim"])}

## 3. Table Set for Paper Results

| Table | 文件 | 论文用途 |
| --- | --- | --- |
| T1 Evidence ledger | [`evidence_ledger.csv`]({rel(TABLES / "evidence_ledger.csv")}) | Results 开头总览：哪些问题已解决，哪些是 limitation。 |
| T2 Supervisor ablation | [`supervisor_ablation_table.csv`]({rel(TABLES / "supervisor_ablation_table.csv")}) | 回答 early stop 是否来自 supervisor。 |
| T3 Baseline progression | [`baseline_progression_table.csv`]({rel(TABLES / "baseline_progression_table.csv")}) | 说明 v10→v11→v12 如何从 early braking 到 close-stop baseline。 |
| T4 Fine target-speed sweep | [`target_speed_fine_sweep_table.csv`]({rel(TABLES / "target_speed_fine_sweep_table.csv")}) | 说明 speed-only failure 不稳定，不能作为主证据。 |
| T5 A1 arrival-gap sweep | [`arrival_gap_a1_table.csv`]({rel(TABLES / "arrival_gap_a1_table.csv")}) | 展示 interaction-timing sensitivity 和 fixed frontier 强度。 |
| T6 A2 mechanism ablation | [`phase_ablation_a2_table.csv`]({rel(TABLES / "phase_ablation_a2_table.csv")}) | 展示 phase-aware adaptive 未转化为 stable final advantage。 |
| T7 A3 risk-owned-yield | [`risk_owned_yield_a3_table.csv`]({rel(TABLES / "risk_owned_yield_a3_table.csv")}) | 展示降低 supervisor authority 后仍 PASS，但 adaptive 不 dominate。 |
| T8 A3 authority metrics | [`a3_authority_metrics_table.csv`]({rel(TABLES / "a3_authority_metrics_table.csv")}) | 验证 A3 regime 确实启用，并量化接管比例。 |
| T9 Infeasibility phase | [`infeasibility_phase_table.csv`]({rel(TABLES / "infeasibility_phase_table.csv")}) | formal supervisor ablation 的 phase-level infeasibility 证据。 |
| T10 Infeasibility final table | [`infeasibility_final_table.csv`]({rel(TABLES / "infeasibility_final_table.csv")}) | 汇总 v12 / speed / A1 / A2 / A3 的 solver failure、gate 和 phase 可用性。 |
| T11 Predictor final sanity | [`predictor_sanity_final_table.csv`]({rel(TABLES / "predictor_sanity_final_table.csv")}) | 当前可写 predictor sanity；明确 FDE/minADE/mode-ranking 仍缺原始结果。 |
| T12 Predictor closed-loop sanity | [`predictor_closed_loop_sanity_table.csv`]({rel(TABLES / "predictor_closed_loop_sanity_table.csv")}) | predictor 作为闭环系统输入时的 sanity check。 |

## 4. Figure Set for Paper Results

### Fig. 1 Supervisor Causes Conservative Early Stop

{figure_md("fig_01_supervisor_first_stop.svg", "Fig. 1. Full vs reduced supervisor: first-stop distance moves from about 8.4m to 5.26m.")}

论文用途：直接回应老师关于 early stop 的问题。这个结果应写成 supervisor/yield logic diagnosis，不能写成 adaptive-risk contribution。

### Fig. 2 Reduced Supervisor Improves Waiting Behaviour

{figure_md("fig_02_supervisor_wait_delay.svg", "Fig. 2. Full vs reduced supervisor: waiting time decreases under reduced intervention.")}

论文用途：说明 reduced intervention 改善 conservative behaviour，同时仍需 post-CARLA safety gate 约束。

### Fig. 3 v11/v12 Shared Baseline Frontier

{figure_md("fig_03_v11_v12_frontier_scatter.svg", "Fig. 3. v11/v12 fixed frontier and adaptive floor_weak in completion-margin space.")}

论文用途：说明 v12 close-stop 是 shared baseline improvement。它解决停车距离问题，但不证明 adaptive 优势。

### Fig. 4 A1 Arrival-Gap Sweep

{figure_md("fig_04_a1_arrival_gap_frontier.svg", "Fig. 4. A1 arrival-gap sweep: interaction timing changes trade-off but does not create stable fixed-risk failure.")}

论文用途：A1 是 sensitivity analysis。可写：arrival timing matters, but fixed frontier remains competitive。

### Fig. 5 A2 Mechanism Ablation

{figure_md("fig_05_a2_mechanism_ablation.svg", "Fig. 5. A2 phase/mechanism ablation: full phase-aware adaptive does not dominate phase-blind or fixed frontier.")}

论文用途：这是重要 negative mechanism ablation。要写成 limitation：phase-aware allocation 在 solver logs 可见，但 final metrics 未稳定受益。

### Fig. 6 A3 Risk-Owned-Yield

{figure_md("fig_06_a3_risk_owned_yield.svg", "Fig. 6. A3 risk-owned-yield: lower supervisor authority remains safe but fixed frontier is still competitive.")}

论文用途：A3 是 supervisor-authority / risk-ownership experiment。可写：降低 nominal takeover 后 policy separation 更可见；不可写 adaptive dominates fixed。

### Fig. 7 Fine Target-Speed Sweep

{figure_md("fig_07_speed_fine_completion.svg", "Fig. 7. Fine speed sweep around 9.0m/s: coarse fixed-conservative failure is not reproduced.")}

论文用途：解释为什么 speed-only sweep 不作为主证据。

### Fig. 8 A3 Authority Metric

{figure_md("fig_08_a3_authority_vs_margin.svg", "Fig. 8. A3 yield-active fraction vs footprint margin.")}

论文用途：补充说明 lower-authority regime 下仍有 emergency/footprint guard activity；评价 planner 必须同时看 final safety 和 authority boundary。

## 5. Key Result Tables Embedded

### 5.1 Supervisor Ablation

{markdown_table(supervisor, ["supervisor_mode", "policy", "n_rollouts", "first_stop_distance_to_conflict_m", "waiting_time_after_first_stop_s", "delay_after_target_clearance_s", "supervisor_active_fraction"])}

Interpretation:

- `full` supervisor creates far early stopping around `8.40m`.
- `reduced` supervisor moves first stop to about `5.26m`, and reduces waiting / post-clearance delay.
- Fixed and adaptive both benefit similarly, so this is shared architecture evidence.

### 5.2 Baseline Progression

{markdown_table(baseline, ["run", "label", "gate_status", "completion_time_s", "first_stop_distance_to_conflict_m", "min_footprint_separation_m", "solver_failure_frac"], max_rows=14)}

Interpretation:

- v10 fixes executable approach braking.
- v11 reduces supervisor ownership of early slowing.
- v12 proves close-stop 4.0m is safe for hard init01 under shared settings.
- None of these alone proves adaptive-risk superiority.

### 5.3 A3 Risk-Owned-Yield Summary

{markdown_table(a3, ["difficulty", "arm", "gate_status", "completion_time", "solver_failure_frac", "min_footprint_separation_m", "critical_pre_tightening", "near_post_tightening"])}

Interpretation:

- 12/12 PASS: lower nominal supervisor authority does not break safety.
- `risk_owned_yield_enabled` is active, but adaptive remains slower or lower-margin than parts of fixed frontier except as a high-margin point at `p3p0`.
- Use A3 to discuss risk ownership and limitation, not adaptive dominance.

### 5.4 A3 Authority Metrics

{markdown_table(a3_authority, ["difficulty", "arm", "risk_owned_yield_enabled_frac", "yield_active_frac", "direct_takeover_frac", "emergency_brake_active_frac"])}

Interpretation:

- A3 regime is genuinely active for almost all frames.
- Emergency brake is not the dominant observed action in these runs.
- Remaining yield-active fraction marks the runtime safety boundary that should be analysed separately from planner quality.

### 5.5 Predictor Final Sanity

{markdown_table(predictor_final, ["evidence_item", "split_or_scope", "value", "unit", "paper_use", "limitation"])}

Interpretation:

- The local repository contains the fine-tuning history and closed-loop validation, but not a complete test-set predictor benchmark.
- Use this table as predictor sanity, not as a claim that prediction is solved.
- Keep the missing FDE/minADE/mode-ranking rows visible until those metrics are generated or pulled.

### 5.6 Infeasibility Final Table

{markdown_table(infeasibility_final, ["run", "difficulty", "arm", "gate_status", "solver_failure_frac", "infeasible_steps_logged", "dominant_infeasible_phase"], max_rows=20)}

Interpretation:

- v12 has phase-level infeasibility logs; failures are low and localized.
- Sweep summaries mostly provide solver failure fractions but not per-step phase logs.
- The dissertation should report solver-layer infeasibility separately from post-CARLA safety gates.

### 5.7 Predictor Closed-Loop Sanity

{markdown_table(predictor_closed_loop, ["policy", "completion_time_s", "solver_failure_frac", "dmin_TV", "completion_valid", "note"])}

Remaining predictor gap:

```text
The current final table records available top-mode ADE fine-tuning evidence.
The final dissertation still needs test-set top1 FDE, minADE/minFDE,
mode ranking / calibration, and split integrity if the examiner asks for
a full predictor benchmark.
```

## 6. Claims Supported by Current Evidence

Strong claims:

1. Conservative early stopping is mainly caused by the rule-aware supervisor / yield logic.
2. Reduced intervention plus executable SMPC approach braking can move the system toward closer, safe give-way behaviour.
3. v12 close-stop 4.0m is a valid shared baseline for hard init01.
4. Fixed-risk should be evaluated as a frontier, not as a single baseline.

Moderate claims:

1. Adaptive risk provides interpretable phase-dependent risk tightening/relaxation.
2. Runtime supervisor authority can hide planner/risk-layer differences in final executed metrics.
3. A3 shows lower nominal supervisor authority can remain safe, but it does not make adaptive dominate fixed.

Unsupported claims:

1. Adaptive-risk robustly outperforms the fixed-risk frontier in final closed-loop metrics.
2. Phase awareness is necessary for the current final performance.
3. Speed-only or arrival-gap-only sweeps expose a stable fixed-risk failure mode.

## 7. Recommended Results Narrative

Recommended Results chapter order:

1. Predictor sanity: show the predictor is adequate for closed-loop evaluation, but not the main novelty.
2. Supervisor ablation: diagnose early stop and supervisor masking.
3. Baseline progression: v10/v11/v12 show the system can safely stop closer.
4. Fixed-risk frontier and difficulty sweeps: fixed frontier is strong; speed/arrival timing alone do not expose stable failure.
5. Adaptive mechanism ablations: A2 is negative/mixed, which prevents overclaiming phase-aware dominance.
6. Supervisor-authority experiment: A3 shows risk ownership is a meaningful axis, but fixed frontier remains competitive.
7. Discussion: the dissertation contribution is a closed-loop analysis of risk-aware SMPC under runtime safety authority, including where adaptive risk is useful and where it is masked or not dominant.

## 8. Immediate Next Work

Do not start another parameter sweep by default. The highest-value next tasks are:

1. Use `Results_and_Discussion_Draft.md` as the starting point for writing.
2. If time permits, generate or pull the missing predictor test-set metrics.
3. Convert the SVG figures into the final dissertation template style if required.
"""
    DOC.write_text(doc, encoding="utf-8")


def row_lookup(rows: list[dict[str, object]], **conditions: str) -> dict[str, object]:
    for row in rows:
        ok = True
        for key, value in conditions.items():
            if str(row.get(key, "")) != value:
                ok = False
                break
        if ok:
            return row
    return {}


def compact_metric_table(rows: list[dict[str, object]], cols: list[str], title: str) -> str:
    return f"### {title}\n\n" + markdown_table(rows, cols) + "\n"


def write_paper_tables_document(**data: list[dict[str, object]]) -> None:
    supervisor = data["supervisor"]
    baseline = data["baseline"]
    speed_fine = data["speed_fine"]
    a1 = data["a1"]
    a2 = data["a2"]
    a3 = data["a3"]
    a3_authority = data["a3_authority"]
    predictor_final = data["predictor_final"]
    infeasibility_final = data["infeasibility_final"]

    baseline_v12 = [r for r in baseline if r.get("run") == "v12 close-stop 4.0m"]
    speed_9 = [r for r in speed_fine if r.get("target_speed") == "9.0"]
    for row in speed_9:
        if row.get("solver_failure_frac"):
            continue
        match = row_lookup(
            infeasibility_final,
            run="fine target-speed sweep",
            difficulty=row.get("difficulty", ""),
            arm=row.get("arm", ""),
        )
        if match:
            row["solver_failure_frac"] = match.get("solver_failure_frac", "")
    a1_extremes = [r for r in a1 if r.get("difficulty") in {"arrival_offset_m3p0", "arrival_offset_p3p0"}]
    a2_key = [r for r in a2 if r.get("difficulty") in {"arrival_offset_m3p0", "arrival_offset_p3p0"}]
    a3_key = [r for r in a3 if r.get("difficulty") in {"arrival_offset_m3p0", "arrival_offset_p0p0", "arrival_offset_p3p0"}]
    infeasibility_key = [
        r
        for r in infeasibility_final
        if r.get("run") in {"v12 close-stop baseline", "A3 risk-owned-yield"}
    ]

    doc = f"""# 当前结果论文格式表格

本文档把自动生成的完整 CSV 精简成论文正文可直接使用的 table 版本。完整数据仍在 `docs/paper/generated/evidence_tables/`。

## Table R1. Supervisor ablation

{markdown_table(supervisor, ["supervisor_mode", "policy", "n_rollouts", "first_stop_distance_to_conflict_m", "waiting_time_after_first_stop_s", "delay_after_target_clearance_s", "supervisor_active_fraction"])}

Caption draft: Full supervisor produces far conservative stops around 8.4 m before the conflict boundary. Reduced intervention moves the first stop to about 5.26 m and reduces waiting and post-clearance delay for both fixed-risk and adaptive-risk policies.

## Table R2. v12 close-stop baseline

{markdown_table(baseline_v12, ["label", "gate_status", "completion_time_s", "first_stop_distance_to_conflict_m", "min_footprint_separation_m", "solver_failure_frac"])}

Caption draft: v12 close-stop baseline validates the shared planner/supervisor architecture. All fixed frontier arms and adaptive floor_weak pass the post-CARLA gate with first stop distances around 4.5 m.

## Table R3. Fine target-speed replication around 9.0 m/s

{markdown_table(speed_9, ["target_speed", "arm", "gate_status", "completion_time", "solver_failure_frac", "min_footprint_separation_m"])}

Caption draft: The previously observed coarse fixed-conservative failure at 9.0 m/s is not reproduced in the fine sweep, so speed-only variation is not used as main evidence of adaptive advantage.

## Table R4. A1 arrival-gap sensitivity at selected offsets

{markdown_table(a1_extremes, ["difficulty", "arm", "gate_status", "completion_time", "min_footprint_separation_m", "critical_pre_tightening", "near_post_tightening"])}

Caption draft: Arrival timing changes the safety-efficiency trade-off, but all arms pass and the fixed-risk frontier remains competitive.

## Table R5. A2 mechanism ablation

{markdown_table(a2_key, ["difficulty", "arm", "gate_status", "completion_time", "min_footprint_separation_m", "critical_pre_tightening", "near_post_tightening"])}

Caption draft: Phase-aware adaptive risk does not produce stable final-metric superiority. Phase-blind and fixed-risk frontier points remain competitive under the shared supervisor.

## Table R6. A3 risk-owned-yield

{markdown_table(a3_key, ["difficulty", "arm", "gate_status", "completion_time", "solver_failure_frac", "min_footprint_separation_m", "critical_pre_tightening", "near_post_tightening"])}

Caption draft: Lowering nominal supervisor authority remains safe but does not make adaptive risk dominate the fixed-risk frontier. Adaptive forms a high-safety point at `arrival_offset_p3p0`, while fixed medium/conservative remain faster.

## Table R7. A3 authority metrics

{markdown_table(a3_authority, ["difficulty", "arm", "risk_owned_yield_enabled_frac", "yield_active_frac", "direct_takeover_frac", "emergency_brake_active_frac"])}

Caption draft: A3 genuinely runs in the risk-owned-yield regime for almost all frames. Residual yield-active fractions quantify the runtime safety boundary that remains even when nominal takeover is reduced.

## Table R8. Predictor sanity

{markdown_table(predictor_final, ["evidence_item", "split_or_scope", "value", "unit", "paper_use", "limitation"])}

Caption draft: The fine-tuned predictor has available top-mode ADE and closed-loop sanity evidence, but a complete test-set predictor benchmark remains a separate pending item.

## Table R9. Infeasibility and final safety

{markdown_table(infeasibility_key, ["run", "difficulty", "arm", "gate_status", "solver_failure_frac", "infeasible_steps_logged", "dominant_infeasible_phase"], max_rows=24)}

Caption draft: Solver infeasibility must be interpreted separately from final safety. v12 has phase-localized infeasible steps and still passes the post-CARLA gate; A3 reports solver failure fractions and gate status but not per-step phase logs.
"""
    PAPER_TABLES_DOC.write_text(doc, encoding="utf-8")


def write_results_discussion_draft(**data: list[dict[str, object]]) -> None:
    supervisor = data["supervisor"]
    baseline = data["baseline"]
    a2 = data["a2"]
    a3 = data["a3"]
    predictor_final = data["predictor_final"]
    infeasibility_final = data["infeasibility_final"]

    full_fixed = row_lookup(supervisor, supervisor_mode="full", policy="fixed-risk")
    reduced_fixed = row_lookup(supervisor, supervisor_mode="reduced", policy="fixed-risk")
    v12_adaptive = row_lookup(baseline, run="v12 close-stop 4.0m", label="adaptive floor_weak")
    a2_m3_adaptive = row_lookup(a2, difficulty="arrival_offset_m3p0", arm="smpc_adaptive_floor_weak")
    a2_m3_fixed_medium = row_lookup(a2, difficulty="arrival_offset_m3p0", arm="smpc_fixed_medium")
    a3_p3_adaptive = row_lookup(a3, difficulty="arrival_offset_p3p0", arm="smpc_adaptive_floor_weak")
    a3_p3_fixed_medium = row_lookup(a3, difficulty="arrival_offset_p3p0", arm="smpc_fixed_medium")

    doc = f"""# Results and Discussion Draft

This draft is written as dissertation prose. It should be edited into the final chapter style, but the claim boundaries should be preserved.

## 5. Results

### 5.1 Predictor sanity check

The prediction module is used as an uncertainty input to the downstream SMPC planner, rather than as the main contribution of this dissertation. The available fine-tuning history shows that the CARLA-specific prediction head converged on the validation split: the best validation top-mode ADE is reported in Table R8, with the fine-tuning history stored in `core/scripts/models/l5kit_multipath_10_carla_finetuned_head_history.json`. The closed-loop validation run also completed for both fixed-risk and adaptive-risk SMPC with low solver failure fractions.

This evidence is sufficient to justify using the predictor in closed-loop planning experiments, but it should not be overclaimed. The local repository does not yet contain a complete test-set predictor benchmark with top1 FDE, minADE/minFDE, mode-ranking accuracy, calibration, and split-leakage checks. Therefore, the dissertation should present the predictor as a sanity-checked component of the planning stack, not as an independently solved prediction problem.

### 5.2 Supervisor ablation: source of conservative early stopping

The formal supervisor ablation answers the first major experimental question: whether the conservative early stopping is caused by the SMPC risk policy or by the rule-aware supervisor. Under the full supervisor, the fixed-risk policy first stops at approximately `{fmt(full_fixed.get("first_stop_distance_to_conflict_m"))}` m from the conflict boundary, with about `{fmt(full_fixed.get("waiting_time_after_first_stop_s"))}` s of waiting after the first stop. Under the reduced-intervention supervisor, the corresponding first stop distance decreases to approximately `{fmt(reduced_fixed.get("first_stop_distance_to_conflict_m"))}` m, and the waiting time drops to about `{fmt(reduced_fixed.get("waiting_time_after_first_stop_s"))}` s.

The same pattern appears for the adaptive-risk policy, so the improvement cannot be attributed to adaptive risk alone. The result supports a clear interpretation: the original conservative behaviour is primarily a consequence of the shared rule-aware yield logic. This is a strong result because it separates planner-layer risk allocation from runtime safety authority.

### 5.3 Baseline progression: from early braking to close-stop v12

The v10-v12 progression establishes the final shared baseline used by the later frontier and ablation experiments. v10 makes the SMPC approach braking executable by forcing shaped-reference linearization. v11 introduces planner-ownership stress, reducing early nominal takeover by the supervisor. v12 then moves the stop clearance to 4.0 m while preserving the post-CARLA safety gate.

In v12, all fixed-risk frontier arms and the adaptive floor_weak arm pass. The adaptive arm completes in `{fmt(v12_adaptive.get("completion_time_s"))}` s with a first stop distance of `{fmt(v12_adaptive.get("first_stop_distance_to_conflict_m"))}` m and a minimum footprint separation of `{fmt(v12_adaptive.get("min_footprint_separation_m"))}` m. This validates v12 as a close-stop shared baseline. It does not, however, establish adaptive superiority, because the fixed-risk frontier also passes with similar final behaviour.

### 5.4 Fixed-risk frontier and difficulty sweeps

The target-speed and arrival-gap sweeps test whether simple scenario difficulty reveals a stable fixed-risk weakness. The coarse target-speed sweep produced one boundary event for fixed conservative at 9.0 m/s, but the fine sweep around the same speed did not reproduce it. This prevents using speed-only variation as a main proof of adaptive advantage.

The A1 arrival-gap sweep is more informative as a sensitivity study. At `arrival_offset_m3p0`, adaptive floor_weak is fast but has the lowest footprint margin. At `arrival_offset_p3p0`, adaptive has the highest safety margin but is slower than fixed aggressive and fixed medium. Therefore, arrival timing changes the trade-off surface, but it does not create a stable fixed-risk failure mode. The correct conclusion is that fixed risk must be evaluated as a frontier rather than as a single baseline.

### 5.5 Adaptive mechanism ablation

A2 tests whether the phase-aware adaptive risk mechanism is necessary for the observed final performance. The result is negative but useful. At `arrival_offset_m3p0`, full adaptive completes in `{fmt(a2_m3_adaptive.get("completion_time"))}` s with footprint separation `{fmt(a2_m3_adaptive.get("min_footprint_separation_m"))}` m, while fixed medium completes in `{fmt(a2_m3_fixed_medium.get("completion_time"))}` s with footprint separation `{fmt(a2_m3_fixed_medium.get("min_footprint_separation_m"))}` m. At `arrival_offset_p3p0`, phase-blind adaptive is faster than full adaptive with nearly the same margin.

This means phase-aware risk allocation is visible in the risk tightening buckets, but it does not reliably transfer into better final executed metrics under the shared supervisor. This negative result is important: it prevents the dissertation from overclaiming adaptive-risk dominance and motivates the later supervisor-authority experiment.

### 5.6 A3 risk-owned-yield: lowering nominal supervisor authority

A3 changes the architecture rather than the scenario difficulty. The reduced supervisor no longer takes over for nominal overlap/hold conditions; emergency braking-distance and footprint-clearance guards remain active. This tests whether risk policy differences become more visible when nominal yield ownership shifts from deterministic supervisor logic toward the SMPC/risk layer.

The experiment remains safe: all A3 runs pass the post-CARLA gate, and `yield_risk_owned_yield_enabled` is active for almost all frames. However, adaptive risk still does not dominate the fixed-risk frontier. At `arrival_offset_p3p0`, adaptive achieves the highest footprint margin, `{fmt(a3_p3_adaptive.get("min_footprint_separation_m"))}` m, but it completes in `{fmt(a3_p3_adaptive.get("completion_time"))}` s, while fixed medium completes in `{fmt(a3_p3_fixed_medium.get("completion_time"))}` s with a lower but still passing margin of `{fmt(a3_p3_fixed_medium.get("min_footprint_separation_m"))}` m.

The result supports the supervisor-authority thesis but not an adaptive-dominance thesis. Lowering nominal supervisor authority makes policy separation more meaningful and preserves safety, but fixed-risk frontier points remain competitive. Adaptive risk is best described as a high-safety trade-off point in this scenario.

### 5.7 Solver infeasibility and final safety

Solver infeasibility is reported separately from final post-CARLA safety. In v12, infeasible steps are low and phase-localized, mainly around critical pre-clearance phases. The larger sweep summaries provide solver failure fractions and final gates, but not per-step phase diagnostics for every run. The paper should therefore avoid a single aggregate feasibility statement. The correct interpretation is that solver-layer infeasibility can occur locally while the closed-loop system still passes the final safety gate.

## 6. Discussion

### 6.1 What the experiments prove

The strongest result is not that adaptive risk beats fixed risk. The strongest result is the decomposition of closed-loop give-way behaviour into planner risk allocation and runtime safety authority. The supervisor ablation shows that conservative early stopping is primarily caused by shared rule-aware yield logic. The v10-v12 progression shows that the system can be tuned from far early stops to a close-stop 4.0 m baseline while retaining safety. These results directly address the practical concerns raised during supervision.

### 6.2 Why adaptive risk does not dominate in final metrics

The fixed-risk frontier remains strong across v12, A1, A2, and A3. This is not simply a failed adaptive experiment. It shows that in a rule-constrained scenario with a runtime safety supervisor, final executed trajectories are partly compressed by shared safety logic and reference shaping. A planner can have different risk allocation internally, but that difference may not appear as a better final trajectory if the supervisor still defines the effective yield boundary.

### 6.3 Supervisor authority as the central research axis

A3 provides the most research-oriented result. By reducing nominal supervisor takeover, it tests whether risk policy differences become more visible when responsibility shifts toward the SMPC layer. The answer is mixed: the system remains safe and policy separation is visible, but fixed risk remains competitive. This supports the broader claim that adaptive risk should be evaluated together with responsibility allocation and supervisor burden, not only through final completion time and safety margin.

### 6.4 Limitations

There are three main limitations. First, the predictor evidence is currently a sanity check rather than a complete benchmark; test-set FDE, minADE/minFDE, mode ranking, and split integrity should be added if the thesis needs a stronger prediction section. Second, the experiments focus on a specific give-way scenario and a hard init01 family of difficulty variations; claims should not generalize to all intersections. Third, adaptive risk is only evaluated through the implemented phase-aware design and risk-owned-yield variant. Other adaptive risk formulations may behave differently.

### 6.5 Final thesis position

The final thesis should claim that risk-aware SMPC under rule-aware supervision can be diagnosed and tuned to produce closer, safe give-way behaviour, and that supervisor authority determines whether adaptive risk allocation is visible in closed-loop metrics. It should not claim universal adaptive-risk superiority over a fixed-risk frontier. The negative and mixed adaptive results are part of the contribution because they reveal where risk adaptation is masked by runtime safety architecture.
"""
    RESULTS_DISCUSSION_DRAFT.write_text(doc, encoding="utf-8")


def main() -> None:
    make_outputs()
    print(f"Wrote {DOC}")
    print(f"Wrote tables under {TABLES}")
    print(f"Wrote figures under {FIGS}")


if __name__ == "__main__":
    main()
