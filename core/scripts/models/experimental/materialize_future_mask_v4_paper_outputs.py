#!/usr/bin/env python3
"""Materialise paper-ready tables and update guidance from audited V4 evidence."""

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
from pathlib import Path
from typing import Any, Iterable, Mapping

from capacity_study_v3_protocol import atomic_json, sha256_file, sha256_payload


PAPER_OUTPUTS_MANIFEST = "PAPER_OUTPUTS_MANIFEST.json"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def hash_valid(payload: Mapping[str, Any], field: str) -> bool:
    value = dict(payload)
    recorded = value.pop(field, None)
    return recorded == sha256_payload(value)


def produced_output_files(output_dir: Path) -> list[str]:
    """Return release payload files, excluding the self-referential manifest.

    The materializer is deliberately idempotent.  A previous manifest may be
    present when the finalizer is rerun, but that manifest cannot safely hash
    itself because its contents change when any payload hash changes.
    """

    return sorted(
        path.name
        for path in output_dir.iterdir()
        if path.is_file() and path.name != PAPER_OUTPUTS_MANIFEST
    )


def macro(metrics: Mapping[str, Any], key: str) -> float | None:
    value = metrics.get("rollout_aggregation", {}).get("macro_mean", {}).get(
        key, metrics.get(key)
    )
    return None if value is None else float(value)


def write_csv(path: Path, rows: list[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def latex_escape(value: Any) -> str:
    return str(value).replace("_", r"\_").replace("%", r"\%")


def fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "--"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return latex_escape(value)


def contrast_map(synthesis: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    axes = synthesis.get("three_axes", synthesis)
    rows = [
        *axes["primary_contrasts"],
        *synthesis.get("direct_architecture_contrasts", []),
        *synthesis.get("supporting_contrasts", axes.get("supporting_contrasts", [])),
    ]
    return {str(row["contrast_id"]): row for row in rows}


def crossed_map(synthesis: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(row["contrast_id"]): row
        for row in synthesis.get("crossed_seed_init_sensitivity", [])
    }


def model_seed_rows(
    root: Path,
    freeze: Mapping[str, Any],
    formal_report_audit: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows = []
    cell_lookup = {row["model_cell_id"]: row for row in freeze["cells"]}
    audited_runs = {
        str(row["run_id"]): row for row in formal_report_audit.get("rows", [])
    }
    if (
        formal_report_audit.get("status") != "pass"
        or formal_report_audit.get("runs") != 27
        or len(audited_runs) != 27
        or not formal_report_audit.get(
            "training_freeze_selection_heldout_identity_chain_verified"
        )
    ):
        raise ValueError("Formal per-run report audit is incomplete")
    for frozen in sorted(freeze["runs"], key=lambda row: row["run_id"]):
        run_id = frozen["run_id"]
        if run_id not in audited_runs:
            raise ValueError(f"Run is absent from formal report audit: {run_id}")
        audited = audited_runs[run_id]
        completion = load(root / "training" / run_id / "TRAINING_COMPLETE.json")
        health = load(root / "training" / run_id / "training_health.json")
        selection = load(root / "postprocess/calibration" / run_id / "selection_metrics.json")
        calibration = load(root / "postprocess/calibration" / run_id / "calibration.json")
        heldout = load(root / "postprocess/heldout" / run_id / "heldout_metrics.json")
        if not all(
            (
                hash_valid(completion, "completion_sha256"),
                hash_valid(selection, "evaluation_sha256"),
                hash_valid(calibration, "calibration_sha256"),
                hash_valid(heldout, "evaluation_sha256"),
            )
        ):
            raise ValueError(f"Paper table source hash failed: {run_id}")
        model_identity = completion["best_model"].get("sha256_tree") or completion[
            "best_model"
        ].get("sha256")
        if (
            completion.get("completion_sha256")
            != frozen.get("training_completion_sha256")
            or model_identity != frozen.get("model_identity")
            or completion.get("cached_weights", {}).get("sha256")
            != frozen.get("cached_weights_sha256")
            or calibration.get("calibration_sha256")
            != frozen.get("calibration_sha256")
            or heldout.get("selection_freeze_sha256") != freeze.get("freeze_sha256")
            or heldout.get("training_completion_sha256")
            != completion.get("completion_sha256")
            or selection.get("evaluation_sha256")
            != audited.get("selection_evaluation_sha256")
            or heldout.get("evaluation_sha256")
            != audited.get("heldout_evaluation_sha256")
            or completion.get("completion_sha256")
            != audited.get("training_completion_sha256")
            or calibration.get("calibration_sha256")
            != audited.get("calibration_sha256")
            or model_identity != audited.get("model_identity")
            or completion.get("cached_weights", {}).get("sha256")
            != audited.get("cached_weights_sha256")
            or completion.get("cache_complete_sha256")
            != audited.get("cache_complete_sha256")
            or completion.get("dataset_complete_sha256")
            != audited.get("dataset_complete_sha256")
            or selection.get("sample_membership_sha256")
            != audited.get("selection_membership_sha256")
            or heldout.get("sample_membership_sha256")
            != audited.get("heldout_membership_sha256")
            or selection["calibrated"]["future_validity"].get("mask_sha256")
            != audited.get("selection_mask_sha256")
            or heldout["calibrated"]["future_validity"].get("mask_sha256")
            != audited.get("heldout_mask_sha256")
        ):
            raise ValueError(f"Paper table frozen-run identity mismatch: {run_id}")
        sel = selection["calibrated"]
        test = heldout["calibrated"]
        validity_sel = sel["future_validity"]
        validity_test = test["future_validity"]
        cell = cell_lookup[frozen["model_cell_id"]]
        rows.append(
            {
                "run_id": run_id,
                "model_cell_id": frozen["model_cell_id"],
                "seed": int(frozen["seed"]),
                "trainable_parameters": int(cell["trainable_parameters"]),
                "best_epoch": int(completion["best_epoch"]),
                "epochs_completed": int(health["epochs_completed"]),
                "boundary_limited": bool(health["boundary_limited"]),
                "model_identity": frozen["model_identity"],
                "cached_weights_sha256": frozen["cached_weights_sha256"],
                "selection_samples": int(selection["samples"]),
                "selection_partial_samples": int(validity_sel["partial_horizon_samples"]),
                "selection_valid_future_steps": int(validity_sel["valid_future_steps"]),
                "selection_invalid_future_steps": int(validity_sel["invalid_future_steps"]),
                "selection_rollout_macro_nll": macro(sel, "trajectory_mixture_NLL_per_step_mean"),
                "selection_top1_ADE_m": macro(sel, "top1_ADE_mean"),
                "selection_FDE_2s_m": macro(sel, "top1_FDE_mean"),
                "selection_FDE_2s_support": int(sel["FDE_full_horizon_samples"]),
                "temperature": float(calibration["parameters"]["temperature"]),
                "covariance_scale": float(calibration["parameters"]["covariance_scale"]),
                "calibration_sha256": calibration["calibration_sha256"],
                "heldout_samples": int(heldout["samples"]),
                "heldout_partial_samples": int(validity_test["partial_horizon_samples"]),
                "heldout_valid_future_steps": int(validity_test["valid_future_steps"]),
                "heldout_invalid_future_steps": int(validity_test["invalid_future_steps"]),
                "heldout_rollout_macro_nll": macro(test, "trajectory_mixture_NLL_per_step_mean"),
                "heldout_top1_ADE_m": macro(test, "top1_ADE_mean"),
                "heldout_FDE_2s_m": macro(test, "top1_FDE_mean"),
                "heldout_FDE_2s_support": int(test["FDE_full_horizon_samples"]),
                "training_complete": True,
                "mask_contract": heldout["future_validity_contract"],
            }
        )
    if len(rows) != 27:
        raise ValueError(f"Expected 27 model-seed rows, found {len(rows)}")
    return rows


def controlled_effect_rows(
    old: Mapping[str, Any],
    corrected: Mapping[str, Any],
    full: Mapping[str, Any],
) -> list[dict[str, Any]]:
    old_map = contrast_map(old)
    new_map = contrast_map(corrected)
    primary_ids = {
        str(row["contrast_id"])
        for row in corrected["three_axes"]["primary_contrasts"]
    }
    full_map = contrast_map(full["full_horizon_selection_recalibrated"]["three_axes"])
    crossed = crossed_map(corrected)
    rows = []
    for contrast_id in sorted(new_map):
        new = new_map[contrast_id]
        before = old_map.get(contrast_id, {})
        sensitivity = full_map.get(contrast_id, {})
        crossed_row = crossed.get(contrast_id, {})
        contrast_role = "primary" if contrast_id in primary_ids else "supporting_descriptive"
        rows.append(
            {
                "contrast_id": contrast_id,
                "contrast_role": contrast_role,
                "metric": new["metric"],
                "old_v3_effect_diagnostic_only": before.get("effect"),
                "corrected_v4_effect": new["effect"],
                "corrected_group_bootstrap_ci_low": new["cluster_interval_95"][0],
                "corrected_group_bootstrap_ci_high": new["cluster_interval_95"][1],
                "corrected_exact_sign_flip_p": new.get("raw_sign_flip_p"),
                "corrected_holm_p": new.get("holm_adjusted_p"),
                "reported_adjusted_p": (
                    new.get("holm_adjusted_p") if contrast_role == "primary" else None
                ),
                "independent_init_groups": new["independent_init_groups"],
                "crossed_seed_init_ci_low": (
                    crossed_row.get("crossed_bootstrap_interval_95", [None, None])[0]
                ),
                "crossed_seed_init_ci_high": (
                    crossed_row.get("crossed_bootstrap_interval_95", [None, None])[1]
                ),
                "full_horizon_recalibrated_effect": sensitivity.get("effect"),
                "full_horizon_ci_low": sensitivity.get("cluster_interval_95", [None, None])[0],
                "full_horizon_ci_high": sensitivity.get("cluster_interval_95", [None, None])[1],
                "evidence_role": (
                    "retrospective_primary_n5_resolution_limited"
                    if contrast_role == "primary"
                    else "retrospective_supporting_descriptive_no_confirmatory_p"
                ),
            }
        )
    return rows


def paper_update_rows() -> list[dict[str, Any]]:
    entries = (
        ("abstract_offline", "46--55", "Abstract offline results", "claims + model_seed_metrics", False),
        ("h1_statement", "118--121", "H1 statement", "CLAIM_CONSISTENCY_AUDIT", False),
        ("h2_statement", "123--129", "H2 transfer statement", "CARLA_DEPLOYMENT_DECISION", True),
        ("contributions", "134--142", "Contributions", "claims + deployment gate", True),
        ("calibration", "195--200", "Calibration", "mask audit + selection integrity", False),
        ("prediction_metrics", "256--271", "Prediction metrics", "valid-step metric contract", False),
        ("dataset", "312--324", "Dataset", "split/mask strata", False),
        ("training_formula", "339--349", "Training loss", "retain; clarify bug boundary", False),
        ("early_stopping", "399--401", "Early stopping", "V4 training audit", False),
        (
            "foundation",
            "661--682",
            "tab:foundation",
            "FOUNDATION_MASK_SCOPE_AUDIT; retain full-horizon-only values",
            False,
        ),
        ("selected_model", "617", "Selected P*", "corrected selection freeze", True),
        ("capacity", "685--694", "Capacity result", "controlled_effects", False),
        ("fig_offline", "696--701", "fig:offline_landscape", "corrected CIA figure", False),
        ("history", "703--714", "Information result", "controlled_effects", False),
        ("architecture", "716--725", "Architecture result", "controlled_effects", False),
        ("tab_effects", "727--743", "tab:offline_effects", "table_offline_effects_v4", False),
        ("closed_loop", "746--820", "fig:closed_factorial/tab:closed_cells", "deployment gate", True),
        ("supervisor", "823--859", "fig:supervisor_authority", "historical/corrected scope", True),
        ("conclusion", "874--903", "Conclusion", "all claims + deployment gate", True),
        ("appendix_metrics", "924--930", "Appendix metric formulae", "mask-aware ADE/FDE", False),
        ("appendix_offline", "968--995", "tab:appendix_offline", "model_seed_metrics", False),
        ("checkpoint", "997--1002", "Checkpoint statement", "training_curve_audit", False),
        ("appendix_audit", "1007--1029", "Appendix audit", "mask integrity + deployment", True),
    )
    return [
        {
            "update_id": key,
            "file": "Jiaqi-Xie-Dissertation/main.tex",
            "current_line_locator": lines,
            "text_or_label_anchor": anchor,
            "replacement_data_source": source,
            "requires_carla_identity_gate": requires_carla,
            "paper_source_was_modified": False,
        }
        for key, lines, anchor, source, requires_carla in entries
    ]


def write_latex_tables(
    output_dir: Path,
    model_rows: list[Mapping[str, Any]],
    effects: list[Mapping[str, Any]],
    cache_audit: Mapping[str, Any],
) -> None:
    by_cell: dict[str, list[Mapping[str, Any]]] = {}
    for row in model_rows:
        by_cell.setdefault(str(row["model_cell_id"]), []).append(row)
    lines = [
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"Model cell & Seed 11 & Seed 23 & Seed 37 & Mean & ADE (m) & FDE@2s (m) \\",
        r"\midrule",
    ]
    for cell, members in sorted(by_cell.items()):
        members = sorted(members, key=lambda row: int(row["seed"]))
        mean_nll = sum(float(row["heldout_rollout_macro_nll"]) for row in members) / 3.0
        mean_ade = sum(float(row["heldout_top1_ADE_m"]) for row in members) / 3.0
        mean_fde = sum(float(row["heldout_FDE_2s_m"]) for row in members) / 3.0
        lines.append(
            f"{latex_escape(cell)} & "
            + " & ".join(fmt(row["heldout_rollout_macro_nll"]) for row in members)
            + f" & {fmt(mean_nll)} & {fmt(mean_ade, 4)} & {fmt(mean_fde, 4)} " + r"\\"
        )
    lines.extend((r"\bottomrule", r"\end{tabular}"))
    (output_dir / "table_offline_matrix_v4.tex").write_text("\n".join(lines) + "\n")

    effect_lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Contrast & Effect & 95\% group CI & Adjusted $p$/scope & Full-horizon effect \\",
        r"\midrule",
    ]
    for row in effects:
        interval = (
            f"[{fmt(row['corrected_group_bootstrap_ci_low'])}, "
            f"{fmt(row['corrected_group_bootstrap_ci_high'])}]"
        )
        p_or_scope = (
            fmt(row["reported_adjusted_p"], 3)
            if row["contrast_role"] == "primary"
            else "descriptive"
        )
        effect_lines.append(
            f"{latex_escape(row['contrast_id'])} & {fmt(row['corrected_v4_effect'])} & "
            f"{interval} & {p_or_scope} & "
            f"{fmt(row['full_horizon_recalibrated_effect'])} " + r"\\"
        )
    effect_lines.extend((r"\bottomrule", r"\end{tabular}"))
    (output_dir / "table_offline_effects_v4.tex").write_text(
        "\n".join(effect_lines) + "\n"
    )

    mask_lines = [
        r"\begin{tabular}{lrrrrr}",
        r"\toprule",
        r"Split & Samples & Partial & Valid steps & Invalid steps & FDE@2s support \\",
        r"\midrule",
    ]
    for split in ("fit", "selection", "heldout"):
        validity = cache_audit["dataset_mask_strata"]["splits"][split]["future_validity"]
        mask_lines.append(
            f"{split} & {validity['samples']} & {validity['partial_horizon_samples']} & "
            f"{validity['valid_future_steps']} & {validity['invalid_future_steps']} & "
            f"{validity['full_horizon_samples']} " + r"\\"
        )
    mask_lines.extend((r"\bottomrule", r"\end{tabular}"))
    (output_dir / "table_mask_audit_v4.tex").write_text("\n".join(mask_lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--old-synthesis", required=True, type=Path)
    parser.add_argument("--foundation-scope", required=True, type=Path)
    parser.add_argument("--extension-protocol", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    freeze_path = args.root / "postprocess/selection_freeze.json"
    synthesis_path = args.root / "postprocess/offline_synthesis.json"
    audit_root = args.root / "audits"
    freeze = load(freeze_path)
    synthesis = load(synthesis_path)
    old = load(args.old_synthesis)
    cache_audit = load(audit_root / "CACHE_AND_MASK_AUDIT.json")
    full = load(audit_root / "FULL_HORIZON_SENSITIVITY.json")
    claims = load(audit_root / "CLAIM_CONSISTENCY_AUDIT.json")
    deployment = load(audit_root / "CARLA_DEPLOYMENT_DECISION.json")
    evidence = load(audit_root / "OFFLINE_EVIDENCE_RELEASE.json")
    formal_reports = load(audit_root / "FORMAL_REPORT_CONTRACT_AUDIT.json")
    foundation = load(args.foundation_scope)
    extension = load(args.extension_protocol)
    if not all(
        (
            hash_valid(freeze, "freeze_sha256"),
            hash_valid(synthesis, "synthesis_sha256"),
            hash_valid(old, "synthesis_sha256"),
            hash_valid(cache_audit, "audit_sha256"),
            hash_valid(full, "sensitivity_sha256"),
            hash_valid(claims, "audit_sha256"),
            hash_valid(deployment, "decision_sha256"),
            hash_valid(evidence, "release_sha256"),
            hash_valid(formal_reports, "audit_sha256"),
            hash_valid(foundation, "audit_sha256"),
            hash_valid(extension, "protocol_sha256"),
        )
    ):
        raise ValueError("Paper materialisation source gate failed")
    gates = evidence.get("gate_artifacts", {})
    expected_links = (
        (evidence.get("schema_version"), "capacity_history_future_mask_v4_offline_evidence_release"),
        (gates.get("selection_freeze_sha256"), freeze.get("freeze_sha256")),
        (gates.get("corrected_synthesis_sha256"), synthesis.get("synthesis_sha256")),
        (gates.get("cache_and_mask_audit_sha256"), cache_audit.get("audit_sha256")),
        (gates.get("full_horizon_sensitivity_sha256"), full.get("sensitivity_sha256")),
        (evidence.get("claim_consistency_audit_sha256"), claims.get("audit_sha256")),
        (evidence.get("carla_deployment_decision_sha256"), deployment.get("decision_sha256")),
        (
            gates.get("formal_report_contract_audit_sha256"),
            formal_reports.get("audit_sha256"),
        ),
        (claims.get("deployment_decision_sha256"), deployment.get("decision_sha256")),
        (
            gates.get("extension_protocol_sha256"),
            extension.get("protocol_sha256"),
        ),
    )
    if any(not left or left != right for left, right in expected_links):
        raise ValueError("Paper materialisation cross-release identity gate failed")

    model_rows = model_seed_rows(args.root, freeze, formal_reports)
    effects = controlled_effect_rows(old, synthesis, full)
    claim_rows = [
        {
            "claim_id": row["claim_id"],
            "conclusion_status": row["conclusion_status"],
            "corrected_offline_to_closed_loop_status": claims[
                "corrected_offline_to_closed_loop_status"
            ],
            "carla_deployment_decision": deployment["decision"],
            "paper_source_was_modified": False,
        }
        for row in claims["claims"]
    ]
    claim_rows.append(
        {
            "claim_id": "foundation_B0_B1_full_horizon_only",
            "conclusion_status": "same",
            "corrected_offline_to_closed_loop_status": claims[
                "corrected_offline_to_closed_loop_status"
            ],
            "carla_deployment_decision": deployment["decision"],
            "paper_source_was_modified": False,
        }
    )
    updates = paper_update_rows()
    write_csv(args.output_dir / "model_seed_metrics.csv", model_rows)
    write_csv(args.output_dir / "controlled_effects.csv", effects)
    write_csv(args.output_dir / "claim_decisions.csv", claim_rows)
    write_csv(args.output_dir / "paper_update_map.csv", updates)
    write_latex_tables(args.output_dir, model_rows, effects, cache_audit)

    claim_lines = "\n".join(
        f"- `{row['claim_id']}`: **{row['conclusion_status']}**"
        for row in claims["claims"]
    )
    markdown = f"""# Corrected future-mask V4 conclusion audit

## Release gates

- Offline evidence release: pass (27/27 corrected runs).
- Future mask: fail-closed in validation, checkpointing, early stopping, calibration and held-out evaluation.
- Selection: groups 36--40 only; held-out groups 41--45 were opened after the immutable freeze.
- Statistical scope: five independent held-out init groups; exact two-sided sign-flip inference is resolution-limited.
- Training budget: the pre-freeze convergence gate triggered a uniform 80-to-120 epoch amendment for all 27 runs before held-out access.

## Offline claim decisions

{claim_lines}

- `foundation_B0_B1_full_horizon_only`: **same**. The frozen foundation
  comparison used 326 full-horizon validation windows and 315 full-horizon
  test windows; zero partial windows entered its metrics.

Overall offline conclusion status: **{claims['overall_offline_conclusion_status']}**.

## P* and CARLA gate

- Old P*: `{deployment['old_p_star']['model_cell_id']}` / `{deployment['old_p_star']['representative_run_id']}`.
- Corrected P*: `{deployment['corrected_p_star']['model_cell_id']}` / `{deployment['corrected_p_star']['representative_run_id']}`.
- Exact deployment identity decision: **{deployment['decision']}**.
- Corrected offline-to-closed-loop claim allowed: **{deployment['corrected_offline_to_closed_loop_claim_allowed']}**.
- Required action: {deployment['required_next_action']}

Historical CARLA outcomes remain valid observations for the historical V3 deployed stack; they cannot be relabelled as corrected V4 transfer evidence unless the identity gate is exact or CARLA is rerun.

## Paper update boundary

No dissertation source or existing figure was modified. Use `paper_update_map.csv`, the three LaTeX table fragments and the Python-generated figures as replacement inputs.
"""
    (args.output_dir / "corrected_v4_conclusion_audit.md").write_text(
        markdown, encoding="utf-8"
    )
    produced = produced_output_files(args.output_dir)
    manifest = {
        "schema_version": "capacity_history_future_mask_v4_paper_outputs",
        "status": "pass",
        "corrected_runs": 27,
        "future_validity_contract": "future_valid_mask_fail_closed_v4",
        "paper_source_modified": False,
        "files": {name: sha256_file(args.output_dir / name) for name in produced},
        "source_artifacts": {
            "selection_freeze_sha256": freeze["freeze_sha256"],
            "synthesis_sha256": synthesis["synthesis_sha256"],
            "cache_audit_sha256": cache_audit["audit_sha256"],
            "full_horizon_sensitivity_sha256": full["sensitivity_sha256"],
            "claim_consistency_audit_sha256": claims["audit_sha256"],
            "carla_deployment_decision_sha256": deployment["decision_sha256"],
            "offline_evidence_release_sha256": evidence["release_sha256"],
            "formal_report_contract_audit_sha256": formal_reports["audit_sha256"],
            "foundation_mask_scope_audit_sha256": foundation["audit_sha256"],
            "extension_protocol_sha256": extension["protocol_sha256"],
        },
    }
    manifest["manifest_sha256"] = sha256_payload(manifest)
    atomic_json(args.output_dir / PAPER_OUTPUTS_MANIFEST, manifest)
    print(json.dumps({"status": "pass", "files": len(produced) + 1}, indent=2))


if __name__ == "__main__":
    main()
