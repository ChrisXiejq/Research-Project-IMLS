#!/usr/bin/env python3
"""Build the final, hash-bound supervisor-feedback Results insertion.

This builder is intentionally final-only.  It refuses to produce a passing
paper-integration marker until SF1--SF4 scientific closure passes, creates one
canonical LaTeX insertion from the paper-facing analysis tables, compiles the
current dissertation, and binds the exact manuscript, evidence, PDF and log
bytes.  Evidence-ID comments remain locators; they are never a substitute for
an input table in the compiled manuscript.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

try:
    from .build_m1_evidence_package import (
        SUPERVISOR_CONTENT_EVIDENCE_IDS,
        audit_supervisor_feedback_closure,
    )
except ImportError:  # pragma: no cover - direct script execution
    from build_m1_evidence_package import (  # type: ignore
        SUPERVISOR_CONTENT_EVIDENCE_IDS,
        audit_supervisor_feedback_closure,
    )


SCHEMA_VERSION = "supervisor_feedback_paper_integration_v6"
SF3_RESULTS_EVIDENCE_ID = "SF3_CORRECTED_FINETUNE_METRICS"
WRAPPER_RELATIVE = Path(
    "docs/paper/generated/supervisor_feedback_v1/paper_integration/"
    "supervisor_feedback_final_results.tex"
)
MARKER_RELATIVE = WRAPPER_RELATIVE.parent / "SUPERVISOR_FEEDBACK_PAPER_INTEGRATION_COMPLETE.json"
DISCUSSION_WRAPPER_RELATIVE = WRAPPER_RELATIVE.parent / "supervisor_feedback_final_discussion.tex"
CONCLUSION_WRAPPER_RELATIVE = WRAPPER_RELATIVE.parent / "supervisor_feedback_final_conclusion.tex"
DEADLINE_TEX_RELATIVE = WRAPPER_RELATIVE.parent / "sf2_deadline_exceedance.tex"
RESULTS_RELATIVE = Path("docs/dissertation/latex/sections/06_results.tex")
DISCUSSION_RELATIVE = Path("docs/dissertation/latex/sections/07_discussion.tex")
CONCLUSION_RELATIVE = Path("docs/dissertation/latex/sections/08_conclusion.tex")
MAIN_RELATIVE = Path("docs/dissertation/latex/main.tex")
WRAPPER_LATEX_INPUT = (
    "../../paper/generated/supervisor_feedback_v1/paper_integration/"
    "supervisor_feedback_final_results.tex"
)
DISCUSSION_WRAPPER_LATEX_INPUT = (
    "../../paper/generated/supervisor_feedback_v1/paper_integration/"
    "supervisor_feedback_final_discussion.tex"
)
CONCLUSION_WRAPPER_LATEX_INPUT = (
    "../../paper/generated/supervisor_feedback_v1/paper_integration/"
    "supervisor_feedback_final_conclusion.tex"
)
PROVISIONAL_DISCUSSION_WRAPPER_TEXT = """% Provisional tracked insertion. The final-only evidence builder atomically
% replaces this file after every scientific and provenance gate passes.
\\subsection{Supervisor-authority interpretation pending scientific closure}

The bounded interpretation of supervisor authority is intentionally unavailable
in this non-submission draft. This placeholder contains no outcome estimate,
count, percentage, probability value, effect direction, ranking or superiority
claim. The release audit remains fail-closed until the prospectively specified
authority matrix, source hashes and paper-integration build have all passed.
"""
PROVISIONAL_CONCLUSION_SENTINEL = "% Provisional tracked Conclusion insertion."
PROVISIONAL_CONCLUSION_WRAPPER_TEXT = f"""{PROVISIONAL_CONCLUSION_SENTINEL} The final-only evidence builder atomically
% replaces this file only after every scientific and provenance gate passes.
\\paragraph{{Supervisor-authority conclusion pending scientific closure.}}
The outcome-specific supervisor-authority conclusion is intentionally unavailable
in this non-submission draft. This placeholder contains no outcome estimate,
effect direction, interval interpretation, ranking, superiority statement or
claim that the authority study has reached scientific closure.
"""
SF3_RESULTS_LATEX_INPUT = (
    "../../paper/generated/supervisor_feedback_v1/03_finetune_audit/"
    "finetune_b0_b1_rollout_macro.tex"
)
LEGACY_DIRECT_SF2_INPUT_PREFIX = (
    "../../paper/generated/supervisor_feedback_v1/02_cost_feasibility/"
)
LEGACY_SF4_PRODUCTION_TOKENS = (
    "distinction_sf4_supervisor_ablation",
    "sf4_supervisor_action_ablation_v1",
    "run_sf4_supervisor_action_ablation",
    "analyze_sf4_supervisor_action_ablation",
)
MISLEADING_SOLVER_PHRASE_PATTERN = re.compile(
    r"attempted[- ]solve\s+latency\s*/\s*feasibility", re.IGNORECASE
)

# These are scientific source products, not arbitrary presentation files.
# The SF4 names are part of the frozen final paper contract for the prospective
# corrected reduced-intervention supervisor application-authority ablation.
CANONICAL_EVIDENCE_ASSETS: dict[str, Path] = {
    "SF1_BEHAVIOUR_APPROACH_STOP": Path(
        "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
        "behaviour_approach_stop.tex"
    ),
    "SF1_BEHAVIOUR_RELEASE_LATENCY": Path(
        "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
        "behaviour_release.tex"
    ),
    "SF1_BEHAVIOUR_PAIRED_RISK_CONTRASTS": Path(
        "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
        "behaviour_policy_paired_contrasts.tex"
    ),
    "SF2_ATTEMPTED_SOLVE_COST_QUANTILES": Path(
        "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
        "supervisor_feedback_02_policy_cost.tex"
    ),
    "SF2_ATTEMPTED_SOLVE_ACCEPTANCE": Path(
        "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
        "supervisor_feedback_02_solver_nonoptimal.tex"
    ),
    "SF2_PAIRED_COST_ACCEPTANCE_CONTRASTS": Path(
        "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
        "supervisor_feedback_02_paired_cost_acceptance.tex"
    ),
    "SF2_RAW_SOLVER_FAILURE_TAXONOMY": Path(
        "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
        "supervisor_feedback_02_failure_taxonomy.tex"
    ),
    "SF2_FAILURE_AFFECTED_ROLLOUT_OUTCOMES": Path(
        "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
        "supervisor_feedback_02_failure_downstream.tex"
    ),
    "SF2_DEADLINE_EXCEEDANCE": DEADLINE_TEX_RELATIVE,
    "SF4_PRIMARY_DID_COMPLETION": Path(
        "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
        "sf4_supervisor_behavioural_authority_v1/analysis/sf4_primary_and_direct_effects.tex"
    ),
    "SF4_BEHAVIOURAL_AUTHORITY_EFFECTS": Path(
        "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
        "sf4_supervisor_behavioural_authority_v1/analysis/"
        "sf4_behavioural_authority_effects.tex"
    ),
    "SF4_MANIPULATION_AUTHORITY": Path(
        "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
        "sf4_supervisor_behavioural_authority_v1/analysis/"
        "sf4_authority_manipulation_and_first_stage.tex"
    ),
    "SF4_COMPUTATIONAL_WALL_TIME": Path(
        "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
        "sf4_supervisor_behavioural_authority_v1/analysis/"
        "sf4_computational_wall_time.tex"
    ),
    "SF4_CONTROLLER_ACCEPTANCE_AND_SOLVER_STATUS": Path(
        "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
        "sf4_supervisor_behavioural_authority_v1/analysis/"
        "sf4_controller_acceptance_and_solver_status.tex"
    ),
    SF3_RESULTS_EVIDENCE_ID: Path(
        "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
        "finetune_b0_b1_rollout_macro.tex"
    ),
}

CANONICAL_EVIDENCE_DATA_SOURCES: dict[str, tuple[Path, ...]] = {
    "SF1_BEHAVIOUR_APPROACH_STOP": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_policy_cluster_macro.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_threshold_sensitivity.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_policy_paired_contrasts.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_rollouts.csv"
        ),
    ),
    "SF1_BEHAVIOUR_RELEASE_LATENCY": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_policy_cluster_macro.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_threshold_sensitivity.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_policy_paired_contrasts.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_rollouts.csv"
        ),
    ),
    "SF1_BEHAVIOUR_PAIRED_RISK_CONTRASTS": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_policy_paired_contrasts.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/01_behaviour/"
            "behaviour_analysis_contract.json"
        ),
    ),
    "SF2_ATTEMPTED_SOLVE_COST_QUANTILES": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "policy_cost_summary.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_policy_solver_summary.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_taxonomy_status.json"
        ),
    ),
    "SF2_ATTEMPTED_SOLVE_ACCEPTANCE": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_policy_solver_summary.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "corrected_attempted_acceptance_contrasts.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_taxonomy_status.json"
        ),
    ),
    "SF2_PAIRED_COST_ACCEPTANCE_CONTRASTS": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "corrected_attempted_cost_contrasts.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "corrected_attempted_acceptance_contrasts.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_taxonomy_status.json"
        ),
    ),
    "SF2_RAW_SOLVER_FAILURE_TAXONOMY": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_step_classification.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "solver_failure_taxonomy.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_taxonomy_status.json"
        ),
    ),
    "SF2_FAILURE_AFFECTED_ROLLOUT_OUTCOMES": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "solver_failure_events.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "solver_failure_affected_rollout_outcomes.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_taxonomy_status.json"
        ),
    ),
    "SF2_DEADLINE_EXCEEDANCE": (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "deadline_exceedance.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/r3_offline/02_cost_feasibility/"
            "raw_taxonomy_status.json"
        ),
    ),
    "SF4_PRIMARY_DID_COMPLETION": (
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/sf4_per_init_did.csv"
        ),
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/sf4_inference.json"
        ),
    ),
    "SF4_BEHAVIOURAL_AUTHORITY_EFFECTS": (
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/sf4_per_init_did.csv"
        ),
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/"
            "sf4_per_init_direct_effects.csv"
        ),
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/sf4_inference.json"
        ),
    ),
    "SF4_MANIPULATION_AUTHORITY": (
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/sf4_manipulation_checks.json"
        ),
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/sf4_rollout_outcomes.csv"
        ),
    ),
    "SF4_COMPUTATIONAL_WALL_TIME": (
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/"
            "sf4_server_wall_time_diagnostics.json"
        ),
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/sf4_inference.json"
        ),
    ),
    "SF4_CONTROLLER_ACCEPTANCE_AND_SOLVER_STATUS": (
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/"
            "sf4_controller_acceptance_and_solver_status.json"
        ),
        Path(
            "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/server_runs/"
            "sf4_supervisor_behavioural_authority_v1/analysis/sf4_rollout_outcomes.csv"
        ),
    ),
    SF3_RESULTS_EVIDENCE_ID: (
        Path(
            "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
            "frozen_test_same_aggregation.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
            "frozen_test_same_aggregation_contrasts.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
            "frozen_test_paired_by_init.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
            "frozen_test_paired_summary.csv"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
            "percentage_accuracy_scan.json"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
            "frozen_test_population_contract.json"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
            "FINETUNE_AUDIT_MANIFEST.json"
        ),
        Path(
            "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
            "SUPERVISOR_COMMENT_3_COMPLETE.json"
        ),
    ),
}

ALL_CONTENT_EVIDENCE_IDS = (*SUPERVISOR_CONTENT_EVIDENCE_IDS, SF3_RESULTS_EVIDENCE_ID)

# The discredited progress-report sentence must not silently re-enter the
# dissertation.  A methods-only retraction may quote it if the local context
# explicitly says that it is withdrawn/retracted and not evidence.
OBSOLETE_PERCENTAGE_ACCURACY_PATTERN = re.compile(
    r"(?:0\s*\.\s*98\s*\\?%.{0,240}?100\s*\\?%"
    r"|100\s*\\?%.{0,240}?0\s*\.\s*98\s*\\?%"
    r"|(?:accuracy|improvement|increase).{0,180}?0\s*\.\s*98.{0,180}?100"
    r"|0\s*\.\s*98.{0,180}?100.{0,180}?(?:accuracy|improvement|increase))",
    flags=re.IGNORECASE | re.DOTALL,
)


def strip_latex_comments(text: str) -> str:
    r"""Remove unescaped LaTeX comments without truncating ``\%`` values."""

    return "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in text.splitlines())


def obsolete_percentage_accuracy_claim_hits(paths: Sequence[Path]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        if not path.is_file():
            continue
        text = strip_latex_comments(path.read_text(encoding="utf-8"))
        for match in OBSOLETE_PERCENTAGE_ACCURACY_PATTERN.finditer(text):
            context = text[max(0, match.start() - 320) : match.end() + 320]
            explicit_retraction = (
                re.search(
                    r"\b(?:withdraw(?:n|s|ing)?|retract(?:ed|s|ing)?|invalid|"
                    r"discredited|superseded)\b",
                    context,
                    re.I,
                )
                and re.search(
                    r"\b(?:not|neither)\b.{0,120}\b(?:evidence|endpoint|accuracy)\b"
                    r"|\bwithdraw(?:n|s|ing)?\b.{0,120}\bevidence\b",
                    context,
                    re.I | re.S,
                )
            )
            if not explicit_retraction:
                hits.append(path.as_posix())
                break
    return sorted(hits)


def sf3_retraction_explanation_complete(text: str) -> bool:
    """Require the old percentage result to be named and correctly retracted."""

    visible = strip_latex_comments(text)
    checks = (
        re.search(r"0\s*\.\s*98\s*\\?%", visible, re.I),
        re.search(r"100\s*\\?%", visible, re.I),
        re.search(
            r"top[- ]probability.{0,100}oracle[- ]best.{0,60}mode",
            visible,
            re.I | re.S,
        ),
        re.search(
            r"not\s+(?:a\s+)?(?:thresholded\s+)?trajectory[- ]accuracy(?:\s+endpoint)?",
            visible,
            re.I,
        ),
        re.search(
            r"\bwithdraw(?:n|s|ing)?\b.{0,180}\bnot\s+evidence\b"
            r"|\bnot\s+evidence\b.{0,180}\bwithdraw(?:n|s|ing)?\b",
            visible,
            re.I | re.S,
        ),
        re.search(r"\bnarrow\b.{0,80}\bsplit\b|\bsplit\b.{0,80}\bnarrow\b", visible, re.I),
        re.search(
            r"oracle[- ]best\s+mode.{0,80}\bconcentrat",
            visible,
            re.I | re.S,
        ),
        re.search(
            r"overlapping[- ]window.{0,100}\baggregat",
            visible,
            re.I | re.S,
        ),
        all(re.search(rf"\b{metric}\b", visible, re.I) for metric in ("NLL", "ADE", "FDE")),
        re.search(r"rollout[- ]macro", visible, re.I),
        re.search(r"independent\s+paired\s+units", visible, re.I),
    )
    unsupported_bug_claim = re.search(
        r"\bimplementation\s+(?:bug|error|fault)\b|\bbug\s+in\s+the\s+implementation\b",
        visible,
        re.I,
    )
    return all(bool(item) for item in checks) and unsupported_bug_claim is None


def legacy_sf4_production_reference_hits(text: str) -> list[str]:
    lowered = strip_latex_comments(text).lower()
    return [token for token in LEGACY_SF4_PRODUCTION_TOKENS if token in lowered]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(contents, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, payload: object) -> None:
    atomic_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def ensure_provisional_discussion_wrapper(repo: Path) -> Path:
    """Create the fail-closed draft wrapper without overwriting final evidence.

    The tracked placeholder keeps the active Discussion ``\\input`` compilable
    before SF4 closure.  Existing content is never changed here; only the final
    builder may atomically replace it after all closure gates pass.
    """

    path = repo.resolve() / DISCUSSION_WRAPPER_RELATIVE
    if path.exists():
        if not path.is_file():
            raise RuntimeError(f"Discussion wrapper path is not a file: {path}")
        return path
    visible = strip_latex_comments(PROVISIONAL_DISCUSSION_WRAPPER_TEXT)
    if re.search(r"\d", visible):
        raise AssertionError("Provisional Discussion wrapper contains an outcome number")
    atomic_text(path, PROVISIONAL_DISCUSSION_WRAPPER_TEXT)
    return path


def ensure_provisional_conclusion_wrapper(repo: Path) -> Path:
    """Create the fail-closed Conclusion wrapper without overwriting final evidence."""

    path = repo.resolve() / CONCLUSION_WRAPPER_RELATIVE
    if path.exists():
        if not path.is_file():
            raise RuntimeError(f"Conclusion wrapper path is not a file: {path}")
        return path
    visible = strip_latex_comments(PROVISIONAL_CONCLUSION_WRAPPER_TEXT)
    if re.search(r"\d", visible):
        raise AssertionError("Provisional Conclusion wrapper contains an outcome number")
    atomic_text(path, PROVISIONAL_CONCLUSION_WRAPPER_TEXT)
    return path


def latex_escape(value: object) -> str:
    text = str(value if value not in (None, "") else "--")
    for original, replacement in (
        ("\\", r"\textbackslash{}"),
        ("_", r"\_"),
        ("%", r"\%"),
        ("&", r"\&"),
        ("#", r"\#"),
    ):
        text = text.replace(original, replacement)
    return text


def build_deadline_table(csv_path: Path) -> str:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"No exact raw deadline rows in {csv_path}")
    required_fields = {
        "risk_policy",
        "deadline_name",
        "deadline_s",
        "evaluation_status",
        "finite_attempted_solve_steps",
        "nonfinite_attempted_solve_steps_excluded",
        "deadline_exceedance_steps",
        "deadline_exceedance_fraction_of_finite_attempts",
    }
    if not required_fields.issubset(rows[0]):
        raise ValueError(
            f"Final attempted-solve deadline table lacks fields "
            f"{sorted(required_fields - set(rows[0]))}: {csv_path}"
        )
    lines = [
        r"\begin{table}[t]",
        r"  \centering\small",
        r"  \caption{Exact attempted-solve deadline audit from hash-validated R3 raw logs. Rule-yield bypass rows are excluded; non-finite attempted latencies are counted separately and not imputed. Exceedance rates use finite attempts only.}",
        r"  \label{tab:sf2-raw-deadline-exceedance}",
        r"  \resizebox{\linewidth}{!}{%",
        r"  \begin{tabular}{@{}llrrrrr@{}}",
        r"    \toprule",
        r"    Policy & Deadline & Limit (ms) & Attempts & Non-finite & Exceed & Rate (\%) \\",
        r"    \midrule",
    ]
    for row in rows:
        if row.get("evaluation_status") != "evaluated":
            raise ValueError(f"Deadline row is not evaluated: {row}")
        try:
            finite = int(row["finite_attempted_solve_steps"])
            nonfinite = int(row["nonfinite_attempted_solve_steps_excluded"])
            exceedances = int(row["deadline_exceedance_steps"])
            deadline_ms = 1000.0 * float(row["deadline_s"])
            rate = (
                100.0 * float(row["deadline_exceedance_fraction_of_finite_attempts"])
                if finite
                else None
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Malformed attempted-solve deadline row: {row}") from exc
        if min(finite, nonfinite, exceedances) < 0 or exceedances > finite:
            raise ValueError(f"Impossible attempted-solve deadline counts: {row}")
        lines.append(
            "    "
            + latex_escape(row.get("risk_policy"))
            + " & "
            + latex_escape(row.get("deadline_name"))
            + " & "
            + f"{deadline_ms:.1f}"
            + " & "
            + str(finite + nonfinite)
            + " & "
            + str(nonfinite)
            + " & "
            + str(exceedances)
            + " & "
            + (f"{rate:.2f}" if rate is not None else "--")
            + r" \\"
        )
    lines.extend(
        (r"    \bottomrule", r"  \end{tabular}%", r"  }", r"\end{table}")
    )
    return "\n".join(lines) + "\n"


def latex_input_for(repo: Path, path: Path) -> str:
    latex_root = repo / "docs/dissertation/latex"
    return os.path.relpath(path, latex_root).replace(os.sep, "/")


def _read_csv_rows(
    path: Path, *, allow_empty: bool = False
) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows and not allow_empty:
        raise ValueError(f"Narrative source has no rows: {path}")
    return rows


def _finite_csv_values(rows: Sequence[Mapping[str, str]], field: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        raw = row.get(field)
        if raw in (None, ""):
            continue
        value = float(raw)
        if not (float("-inf") < value < float("inf")):
            raise ValueError(f"Non-finite narrative value {field}={raw!r}")
        values.append(value)
    return values


def _optional_finite_number(value: Any) -> float | None:
    if value in (None, "", "NA", "--"):
        return None
    number = float(value)
    if not (float("-inf") < number < float("inf")):
        raise ValueError(f"Non-finite narrative value: {value!r}")
    return number


def _format_optional(value: float | None, *, digits: int, signed: bool = False) -> str:
    if value is None:
        return "NA"
    sign = "+" if signed else ""
    return f"{value:{sign}.{digits}f}"


def build_result_narrative(repo: Path) -> dict[str, Any]:
    """Recompute all final prose facts from the exact paper-facing products."""

    feedback = repo / "docs/paper/generated/supervisor_feedback_v1/r3_offline"
    sf1_dir = feedback / "01_behaviour"
    sf2_dir = feedback / "02_cost_feasibility"
    sf4_dir = (
        repo
        / "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/"
        "server_runs/sf4_supervisor_behavioural_authority_v1/analysis"
    )
    source_paths = (
        sf1_dir / "behaviour_policy_cluster_macro.csv",
        sf1_dir / "behaviour_threshold_sensitivity.csv",
        sf2_dir / "raw_policy_solver_summary.csv",
        sf2_dir / "solver_failure_affected_rollout_outcomes.csv",
        sf2_dir / "raw_taxonomy_status.json",
        sf2_dir / "SUPERVISOR_FEEDBACK_02_COMPLETE.json",
        sf4_dir / "sf4_inference.json",
        sf4_dir / "sf4_manipulation_checks.json",
        sf4_dir / "sf4_server_wall_time_diagnostics.json",
        sf4_dir / "sf4_controller_acceptance_and_solver_status.json",
        sf1_dir / "behaviour_policy_paired_contrasts.csv",
        sf1_dir / "behaviour_rollouts.csv",
        sf2_dir / "corrected_attempted_cost_contrasts.csv",
        sf2_dir / "corrected_attempted_acceptance_contrasts.csv",
    )
    for path in source_paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(path)

    sf1_rows = _read_csv_rows(source_paths[0])
    sf1_by_policy = {row["risk_policy"]: row for row in sf1_rows}
    if set(sf1_by_policy) != {
        "adaptive",
        "fixed_aggressive",
        "fixed_medium",
        "fixed_conservative",
    }:
        raise ValueError("SF1 policy-macro narrative source is incomplete")
    sensitivity = _read_csv_rows(source_paths[1])
    definitions = {
        (
            float(row["stop_speed_mps"]),
            float(row["resume_speed_mps"]),
            int(row["consecutive_steps"]),
        )
        for row in sensitivity
    }
    if len(sensitivity) != 108 or len(definitions) != 27:
        raise ValueError("SF1 threshold sensitivity must contain 27 x 4 rows")
    adaptive_sensitivity = [
        row for row in sensitivity if row["risk_policy"] == "adaptive"
    ]
    stop_sensitivity = _finite_csv_values(
        adaptive_sensitivity,
        "first_stop_distance_to_conflict_m__cluster_macro_mean",
    )
    sf1_contrasts = _read_csv_rows(source_paths[10])
    contrast_by_key = {
        (row["contrast"], row["metric"]): row for row in sf1_contrasts
    }
    fixed_comparators = (
        "fixed_aggressive",
        "fixed_medium",
        "fixed_conservative",
    )
    mechanism_metrics = (
        "first_stop_distance_to_conflict_m",
        "first_stop_distance_to_designed_stop_m",
        "cautious_approach_progress_m",
        "pre_clearance_stopped_duration_s",
        "nominal_clear_to_release_latency_s",
        "buffered_clear_to_resume_latency_s",
        "release_to_resume_latency_s",
    )
    expected_contrast_keys = {
        (f"adaptive_minus_{fixed}", metric)
        for fixed in fixed_comparators
        for metric in mechanism_metrics
    }
    if (
        len(sf1_contrasts) != 21
        or len(contrast_by_key) != 21
        or set(contrast_by_key) != expected_contrast_keys
    ):
        raise ValueError("SF1 paired mechanism contrasts are incomplete")
    paired_facts: dict[str, dict[str, dict[str, Any]]] = {}
    for fixed in fixed_comparators:
        paired_facts[fixed] = {}
        for metric in mechanism_metrics:
            row = contrast_by_key[(f"adaptive_minus_{fixed}", metric)]
            observed = int(row["independent_init_groups"])
            expected = int(row["expected_init_groups"])
            per_init = json.loads(row["per_init_effects_json"])
            defined_effects = [
                _optional_finite_number(value) for value in per_init.values()
            ]
            defined_effects = [
                value for value in defined_effects if value is not None
            ]
            mean_effect = _optional_finite_number(row.get("cluster_mean_effect"))
            sensitivity_value = _optional_finite_number(
                row.get("two_sided_exact_sign_flip_p_descriptive")
            )
            if not all(
                (
                    expected == 5,
                    0 <= observed <= expected,
                    set(per_init) == {"101", "102", "103", "104", "105"},
                    len(defined_effects) == observed,
                    row.get("analysis_role")
                    == "post_hoc_paired_mechanism_contrast",
                    mean_effect is None and sensitivity_value is None
                    if observed == 0
                    else mean_effect is not None
                    and sensitivity_value is not None
                    and 0.0 <= sensitivity_value <= 1.0,
                )
            ):
                raise ValueError(
                    f"SF1 paired mechanism missingness contract failed: {fixed}/{metric}"
                )
            paired_facts[fixed][metric] = {
                "observed_init_groups": observed,
                "expected_init_groups": expected,
                "cluster_mean_effect": mean_effect,
                "sign_flip_sensitivity": sensitivity_value,
            }
    sf1_rollouts = _read_csv_rows(source_paths[11])
    stop_window_counts: dict[str, int] = {}
    for row in sf1_rollouts:
        status = row["stop_window_status"]
        stop_window_counts[status] = stop_window_counts.get(status, 0) + 1
    if len(sf1_rollouts) != 80 or set(stop_window_counts) - {
        "evaluated",
        "censored_missing_release",
        "not_applicable_missing_yield_entry",
    }:
        raise ValueError("SF1 stop-window missingness accounting is invalid")

    def sf1_metric(policy: str, metric: str) -> dict[str, Any]:
        row = sf1_by_policy[policy]
        value = _optional_finite_number(row.get(f"{metric}__cluster_macro_mean"))
        observed_raw = row.get(f"{metric}__clusters_observed")
        if observed_raw in (None, ""):
            raise ValueError(f"SF1 policy-macro coverage is missing: {policy}/{metric}")
        observed = int(observed_raw)
        expected = int(row["independent_init_groups"])
        if not (expected == 5 and 0 <= observed <= expected):
            raise ValueError(f"SF1 policy-macro coverage is invalid: {policy}/{metric}")
        if (value is None) != (observed == 0):
            raise ValueError(f"SF1 policy-macro value/coverage mismatch: {policy}/{metric}")
        return {"value": value, "observed_init_groups": observed, "expected_init_groups": expected}

    policy_metric_names = {
        "approach_progress_m": "cautious_approach_progress_m",
        "stop_to_conflict_m": "first_stop_distance_to_conflict_m",
        "designed_stop_clearance_m": "designed_stop_clearance_m",
        "stop_line_error_m": "first_stop_distance_to_designed_stop_m",
        "pre_clearance_stopped_duration_s": "pre_clearance_stopped_duration_s",
        "nominal_clear_to_release_s": "nominal_clear_to_release_latency_s",
        "release_to_resume_s": "release_to_resume_latency_s",
        "buffered_clear_to_resume_s": "buffered_clear_to_resume_latency_s",
    }

    sf1_facts = {
        "rollouts": sum(int(row["rollouts"]) for row in sf1_rows),
        "independent_init_groups_per_policy": 5,
        "threshold_definitions": len(definitions),
        "threshold_rows": len(sensitivity),
        "policy_macro": {
            policy: {
                label: sf1_metric(policy, metric)
                for label, metric in policy_metric_names.items()
            }
            for policy in sf1_by_policy
        },
        "adaptive_stop_sensitivity_defined_definitions": len(stop_sensitivity),
        "adaptive_stop_sensitivity_min_m": (
            min(stop_sensitivity) if stop_sensitivity else None
        ),
        "adaptive_stop_sensitivity_max_m": (
            max(stop_sensitivity) if stop_sensitivity else None
        ),
        "paired_contrasts": paired_facts,
        "stop_window_counts": stop_window_counts,
    }

    def policy_phrase(policy: str, metric: str, *, unit: str) -> str:
        fact = sf1_facts["policy_macro"][policy][metric]
        return (
            f"{_format_optional(fact['value'], digits=3)}~{unit} "
            f"({fact['observed_init_groups']}/{fact['expected_init_groups']})"
        )

    def contrast_phrase(fixed: str, metric: str, *, unit: str) -> str:
        fact = paired_facts[fixed][metric]
        label = fixed.replace("fixed_", "fixed-").replace("_", "-")
        return (
            f"{label} {_format_optional(fact['cluster_mean_effect'], digits=3, signed=True)}"
            f"~{unit} ({fact['observed_init_groups']}/{fact['expected_init_groups']}; "
            f"sign-flip {_format_optional(fact['sign_flip_sensitivity'], digits=4)})"
        )

    if stop_sensitivity:
        sensitivity_phrase = (
            f"{min(stop_sensitivity):.3f}--{max(stop_sensitivity):.3f}~m "
            f"across {len(stop_sensitivity)}/27 definitions with a defined "
            "cluster-macro estimate"
        )
    else:
        sensitivity_phrase = "NA across 0/27 definitions with a defined cluster-macro estimate"
    sf1_text = (
        r"\paragraph{Cautious approach, stopping and release.} "
        f"The 80-rollout corrected-R3 mechanism audit (five independent ego-init "
        f"groups per policy) reports every mechanism estimate with observed/expected "
        f"init coverage. Adaptive approach progress, stop--conflict distance, configured "
        f"designed stop clearance and signed stop-line error were "
        f"{policy_phrase('adaptive', 'approach_progress_m', unit='m')}, "
        f"{policy_phrase('adaptive', 'stop_to_conflict_m', unit='m')}, "
        f"{policy_phrase('adaptive', 'designed_stop_clearance_m', unit='m')} and "
        f"{policy_phrase('adaptive', 'stop_line_error_m', unit='m')}. These are frozen-"
        f"route coordinates, not bumper clearances: stop--conflict is "
        f"$s_{{conflict}}-s_{{ego}}$ from the actor/reference point (positive upstream, "
        f"negative after conflict); designed clearance is $s_{{conflict}}-s_{{stop}}$; "
        f"and signed stop-line error is $s_{{stop}}-s_{{ego}}$ (positive means stopped "
        f"upstream/short of the configured stop point, negative means passed it). Adaptive "
        f"stop--path-release duration, nominal-clear--release, release--resume and "
        f"buffered-clear--resume latencies were "
        f"{policy_phrase('adaptive', 'pre_clearance_stopped_duration_s', unit='s')}, "
        f"{policy_phrase('adaptive', 'nominal_clear_to_release_s', unit='s')}, "
        f"{policy_phrase('adaptive', 'release_to_resume_s', unit='s')} and "
        f"{policy_phrase('adaptive', 'buffered_clear_to_resume_s', unit='s')}. The post-hoc "
        f"definition sensitivity covers 27 stop/resume/hysteresis definitions "
        f"(108 policy summaries); adaptive stop distance was {sensitivity_phrase}. The "
        f"paired table exposes all 21 adaptive-minus-fixed mechanism cells. For "
        f"stop--conflict distance the effects were "
        f"{contrast_phrase('fixed_aggressive', 'first_stop_distance_to_conflict_m', unit='m')}, "
        f"{contrast_phrase('fixed_medium', 'first_stop_distance_to_conflict_m', unit='m')} and "
        f"{contrast_phrase('fixed_conservative', 'first_stop_distance_to_conflict_m', unit='m')}; "
        f"for nominal-clear--release they were "
        f"{contrast_phrase('fixed_aggressive', 'nominal_clear_to_release_latency_s', unit='s')}, "
        f"{contrast_phrase('fixed_medium', 'nominal_clear_to_release_latency_s', unit='s')} and "
        f"{contrast_phrase('fixed_conservative', 'nominal_clear_to_release_latency_s', unit='s')}. "
        f"Stop windows were evaluated for {stop_window_counts.get('evaluated', 0)} "
        f"rollouts, censored at missing release for "
        f"{stop_window_counts.get('censored_missing_release', 0)}, and not applicable "
        f"without yield entry for "
        f"{stop_window_counts.get('not_applicable_missing_yield_entry', 0)}; a later "
        "terminal stop is never substituted. NA denotes scientific censoring, never an "
        "integrity failure or a reason to rerun. These values quantify conservative "
        "behaviour but do not turn a post-hoc mechanism audit into a causal comparison."
    )

    sf2_policy_rows = _read_csv_rows(source_paths[2])
    sf2_by_policy = {row["risk_policy"]: row for row in sf2_policy_rows}
    if set(sf2_by_policy) != set(sf1_by_policy):
        raise ValueError("SF2 policy summary is incomplete")
    affected_rows = _read_csv_rows(source_paths[3], allow_empty=True)
    raw_status = json.loads(source_paths[4].read_text(encoding="utf-8"))
    sf2_receipt = json.loads(source_paths[5].read_text(encoding="utf-8"))
    if (
        raw_status.get("status") != "pass"
        or sf2_receipt.get("status") != "pass"
        or sf2_receipt.get("corrected_attempted_acceptance_status") != "pass"
        or sf2_receipt.get("failure_downstream_outcome_join_status") != "pass"
    ):
        raise ValueError("SF2 final receipt is not acceptance/downstream ready")
    attempts = sum(int(row["attempted_solve_steps"]) for row in sf2_policy_rows)
    accepted = sum(int(row["attempted_accepted_steps"]) for row in sf2_policy_rows)
    fallback = sum(
        int(row["attempted_fallback_or_nonaccepted_steps"])
        for row in sf2_policy_rows
    )
    bypass = sum(int(row["rule_bypass_no_solve_steps"]) for row in sf2_policy_rows)
    affected_events = sum(
        int(row["attempted_fallback_or_nonaccepted_steps"])
        for row in affected_rows
    )
    minimum_separation = (
        min(float(row["minimum_footprint_separation_m"]) for row in affected_rows)
        if affected_rows
        else None
    )
    sf2_cost_contrasts = _read_csv_rows(source_paths[12])
    sf2_acceptance_contrasts = _read_csv_rows(source_paths[13])

    def sf2_paired_facts(
        rows: Sequence[Mapping[str, str]], *, endpoint: str
    ) -> dict[str, dict[str, Any]]:
        by_contrast = {row["contrast"]: row for row in rows}
        expected = {f"adaptive_minus_{fixed}" for fixed in fixed_comparators}
        if len(rows) != 3 or set(by_contrast) != expected:
            raise ValueError(f"SF2 {endpoint} contrasts do not cover all fixed policies")
        output: dict[str, dict[str, Any]] = {}
        for fixed in fixed_comparators:
            row = by_contrast[f"adaptive_minus_{fixed}"]
            n = int(row["independent_init_clusters"])
            effects = json.loads(row["cluster_effects_json"])
            mean = _optional_finite_number(row.get("cluster_mean_effect"))
            low = _optional_finite_number(row.get("cluster_minimum_effect"))
            high = _optional_finite_number(row.get("cluster_maximum_effect"))
            p_value = _optional_finite_number(
                row.get("two_sided_exact_sign_flip_p_descriptive")
            )
            signs = [
                int(row[field])
                for field in ("cluster_negative", "cluster_zero", "cluster_positive")
            ]
            if not all(
                (
                    n == 5,
                    set(effects) == {"101", "102", "103", "104", "105"},
                    all(_optional_finite_number(value) is not None for value in effects.values()),
                    mean is not None,
                    low is not None,
                    high is not None,
                    low <= mean <= high,
                    sum(signs) == n,
                    p_value is not None and 0.0 <= p_value <= 1.0,
                    row.get("inference_scope")
                    == "descriptive post-hoc supervisor-feedback audit",
                )
            ):
                raise ValueError(f"SF2 {endpoint} paired contrast is invalid: {fixed}")
            output[fixed] = {
                "independent_init_clusters": n,
                "cluster_mean_effect": mean,
                "cluster_minimum_effect": low,
                "cluster_maximum_effect": high,
                "cluster_signs_negative_zero_positive": signs,
                "sign_flip_sensitivity": p_value,
            }
        return output

    paired_cost = sf2_paired_facts(sf2_cost_contrasts, endpoint="cost")
    paired_acceptance = sf2_paired_facts(
        sf2_acceptance_contrasts, endpoint="acceptance"
    )
    sf2_facts = {
        "canonical_debug_logs": int(raw_status["canonical_debug_files"]),
        "attempted_solve_steps": attempts,
        "controller_accepted_steps": accepted,
        "fallback_or_nonaccepted_steps": fallback,
        "bypass_no_solve_steps": bypass,
        "adaptive_attempted_p95_ms": 1000.0
        * float(sf2_by_policy["adaptive"]["attempted_latency_p95_s"]),
        "fixed_medium_attempted_p95_ms": 1000.0
        * float(sf2_by_policy["fixed_medium"]["attempted_latency_p95_s"]),
        "affected_rollouts": len(affected_rows),
        "affected_events": affected_events,
        "completion_failures": sum(int(row["completion_failure"]) for row in affected_rows),
        "yield_failures": sum(int(row["yield_failure"]) for row in affected_rows),
        "footprint_collisions": sum(int(row["footprint_collision"]) for row in affected_rows),
        "native_collision_rollouts": sum(int(row["native_collision_any"]) for row in affected_rows),
        "minimum_footprint_separation_m": minimum_separation,
        "paired_adaptive_minus_fixed_cost_p95_s": paired_cost,
        "paired_adaptive_minus_fixed_fallback_fraction": paired_acceptance,
    }
    if attempts != accepted + fallback or affected_events != fallback:
        raise ValueError("SF2 narrative accounting does not close")

    def sf2_contrast_phrase(fixed: str) -> str:
        label = fixed.replace("fixed_", "fixed-").replace("_", "-")
        cost = paired_cost[fixed]
        acceptance = paired_acceptance[fixed]
        return (
            f"{label}: {1000.0 * cost['cluster_mean_effect']:+.2f}~ms "
            f"[{1000.0 * cost['cluster_minimum_effect']:+.2f}, "
            f"{1000.0 * cost['cluster_maximum_effect']:+.2f}], sensitivity "
            f"{cost['sign_flip_sensitivity']:.4f}; "
            f"{100.0 * acceptance['cluster_mean_effect']:+.2f} percentage points "
            f"[{100.0 * acceptance['cluster_minimum_effect']:+.2f}, "
            f"{100.0 * acceptance['cluster_maximum_effect']:+.2f}], sensitivity "
            f"{acceptance['sign_flip_sensitivity']:.4f} "
            f"(n={cost['independent_init_clusters']} init clusters)"
        )
    sf2_text = (
        r"\paragraph{Solver execution, cost and downstream outcomes.} "
        f"The corrected SF2 receipt passed for {sf2_facts['canonical_debug_logs']} "
        f"hash-validated logs. Of {attempts} factual SMPC attempts, {accepted} were "
        f"controller-accepted and {fallback} followed the fallback/nonaccepted path; "
        f"{bypass} rule-bypass/no-solve decisions are reported outside that denominator. "
        f"Adaptive and fixed-medium finite recorded CasADi solve-stage P95 values were "
        f"{sf2_facts['adaptive_attempted_p95_ms']:.2f} and "
        f"{sf2_facts['fixed_medium_attempted_p95_ms']:.2f}~ms. This timer is "
        "optimizer-internal: it excludes prediction, controller preprocessing, "
        "supervisor logic and the CARLA loop, so it is neither end-to-end latency nor "
        "a real-time/deployment guarantee. The historical accepted flag includes "
        "controller-selected CasADi SUBOPTIMAL commands and is not a certificate of "
        f"mathematical optimality or feasibility. Cluster-paired adaptive-minus-fixed "
        f"effects for recorded solve-stage P95 and fallback/nonacceptance, respectively, "
        f"were {sf2_contrast_phrase('fixed_aggressive')}; "
        f"{sf2_contrast_phrase('fixed_medium')}; and "
        f"{sf2_contrast_phrase('fixed_conservative')}. These exact sign-flip values are "
        f"post-hoc small-n sensitivities, not treatment-randomisation inference. Each "
        f"of the {fallback} fallback/"
        f"nonaccepted events joins exactly one canonical rollout; those events occurred "
        f"across {len(affected_rows)} affected rollouts. Their downstream "
        f"outcomes contain {sf2_facts['completion_failures']} completion failures, "
        f"{sf2_facts['yield_failures']} yield failures, "
        f"{sf2_facts['footprint_collisions']} footprint collisions and "
        f"{sf2_facts['native_collision_rollouts']} native-collision rollouts"
        + (
            f", with minimum footprint separation {minimum_separation:.3f}~m. "
            if minimum_separation is not None
            else "; minimum separation is not applicable because no rollout was affected. "
        )
        + "This last association "
        "is descriptive and does not identify controller nonacceptance as the cause."
    )

    sf4_inference = json.loads(source_paths[6].read_text(encoding="utf-8"))
    sf4_manipulation = json.loads(source_paths[7].read_text(encoding="utf-8"))
    sf4_wall = json.loads(source_paths[8].read_text(encoding="utf-8"))
    sf4_controller = json.loads(source_paths[9].read_text(encoding="utf-8"))
    primary = sf4_inference["outcomes"]["failure_penalized_completion_time_s"]
    direct = sf4_inference["direct_paired_effects"][
        "failure_penalized_completion_time_s"
    ]
    first_stage = sf4_manipulation["observed_first_stage_activity"]
    implementation = sf4_manipulation["implementation_manipulation_gate"]
    wall_by_authority = sf4_wall["by_authority_rollout_means"]
    controller_full = sf4_controller["full_matrix"]
    if (
        implementation.get("status") != "pass"
        or first_stage.get("status") not in {"active", "inactive_scientific_outcome"}
        or sf4_controller.get("status") != "pass"
    ):
        raise ValueError("SF4 narrative sources are not final")

    def optional_finite(value: Any) -> float | None:
        if value in (None, ""):
            return None
        number = float(value)
        return number if float("-inf") < number < float("inf") else None

    wall_metrics = {
        f"{label}_p{quantile}": {
            mode: optional_finite(
                wall_by_authority[mode].get(
                    f"{prefix}_wall_time_p{quantile}_ms__rollout_mean"
                )
            )
            for mode in ("on", "off")
        }
        for prefix, label in (("ego_policy", "ego_policy"), ("prediction", "prediction"))
        for quantile in (50, 95, 99)
    }

    def wall_pair(label: str) -> str:
        values = wall_metrics[label]
        return "/".join(
            "NA" if values[mode] is None else f"{values[mode]:.2f}"
            for mode in ("on", "off")
        )

    sf4_behavioural_metrics = (
        (
            "minimum_margin_adjusted_bbox_separation_m",
            "minimum 0.25-m/actor margin-adjusted bbox separation",
            "m",
        ),
        (
            "cautious_approach_progress_m",
            "cautious approach progress after yield entry",
            "m",
        ),
        (
            "first_stop_distance_to_conflict_m",
            "first sustained-stop distance to conflict",
            "m",
        ),
        (
            "first_stop_distance_to_designed_stop_m",
            "signed stop-line error",
            "m",
        ),
        ("stopped_duration_s", "stopped duration", "s"),
        (
            "nominal_conflict_clear_to_actual_path_release_s",
            "nominal-clear--actual-path-release latency",
            "s",
        ),
        (
            "actual_path_release_to_sustained_resume_s",
            "actual-path-release--sustained-resume latency",
            "s",
        ),
        (
            "buffered_conflict_clear_to_sustained_resume_s",
            "buffered-clear--sustained-resume latency",
            "s",
        ),
    )

    def sf4_effect(entry: Mapping[str, Any], *, label: str) -> dict[str, Any]:
        defined = int(entry["defined_init_clusters"])
        total = int(entry["total_init_clusters"])
        if total != 10 or not 0 <= defined <= total:
            raise ValueError(f"SF4 behavioural coverage is invalid: {label}")
        mean = _optional_finite_number(entry.get("mean_effect"))
        ci_raw = entry.get("cluster_bootstrap_95ci")
        p_value = _optional_finite_number(
            entry.get("exact_two_sided_sign_flip_sensitivity_value")
        )
        if defined == total:
            if (
                mean is None
                or not isinstance(ci_raw, list)
                or len(ci_raw) != 2
                or p_value is None
            ):
                raise ValueError(f"SF4 complete behavioural effect is incomplete: {label}")
            ci_values = [_optional_finite_number(value) for value in ci_raw]
            if any(value is None for value in ci_values) or not 0.0 <= p_value <= 1.0:
                raise ValueError(f"SF4 complete behavioural effect is non-finite: {label}")
        else:
            if mean is not None or ci_raw not in (None, []) or p_value is not None:
                raise ValueError(f"SF4 censored behavioural effect must remain NA: {label}")
            ci_values = None
        return {
            "defined_init_clusters": defined,
            "total_init_clusters": total,
            "mean_effect": mean,
            "cluster_bootstrap_95ci": ci_values,
            "sign_flip_sensitivity": p_value,
            "censored": defined < total,
        }

    behavioural_facts: dict[str, dict[str, dict[str, Any]]] = {}
    for metric, _, _ in sf4_behavioural_metrics:
        outcome_entry = sf4_inference["outcomes"][metric]
        direct_entries = sf4_inference["direct_paired_effects"][metric]
        behavioural_facts[metric] = {
            "did": sf4_effect(outcome_entry, label=f"{metric}/DID"),
            "authority_effect_adaptive": sf4_effect(
                direct_entries["authority_effect_adaptive"],
                label=f"{metric}/authority_effect_adaptive",
            ),
            "authority_effect_fixed_medium": sf4_effect(
                direct_entries["authority_effect_fixed_medium"],
                label=f"{metric}/authority_effect_fixed_medium",
            ),
            "risk_effect_authority_on": sf4_effect(
                direct_entries["risk_effect_authority_on"],
                label=f"{metric}/risk_effect_authority_on",
            ),
            "risk_effect_authority_off": sf4_effect(
                direct_entries["risk_effect_authority_off"],
                label=f"{metric}/risk_effect_authority_off",
            ),
        }

    def sf4_effect_phrase(entry: Mapping[str, Any], *, unit: str) -> str:
        coverage = f"{entry['defined_init_clusters']}/{entry['total_init_clusters']}"
        if entry["mean_effect"] is None:
            return f"NA ({coverage}; censored)"
        ci_values = entry["cluster_bootstrap_95ci"]
        return (
            f"{entry['mean_effect']:+.3f}~{unit} ({coverage}; 95\\% CI "
            f"[{ci_values[0]:+.3f}, {ci_values[1]:+.3f}]; sign-flip "
            f"{entry['sign_flip_sensitivity']:.4f})"
        )

    behavioural_sentences = []
    for metric, label, unit in sf4_behavioural_metrics:
        entries = behavioural_facts[metric]
        behavioural_sentences.append(
            f"{label}: DID {sf4_effect_phrase(entries['did'], unit=unit)}, "
            f"authority on-minus-off within adaptive "
            f"{sf4_effect_phrase(entries['authority_effect_adaptive'], unit=unit)}, "
            f"and within fixed-medium "
            f"{sf4_effect_phrase(entries['authority_effect_fixed_medium'], unit=unit)}"
        )

    ci = [float(value) for value in primary["cluster_bootstrap_95ci"]]
    sf4_facts = {
        "primary_did_s": float(primary["mean_effect"]),
        "primary_ci95_s": ci,
        "primary_sign_flip_sensitivity": float(
            primary["exact_two_sided_sign_flip_sensitivity_value"]
        ),
        "risk_effect_authority_on_s": float(
            direct["risk_effect_authority_on"]["mean_effect"]
        ),
        "risk_effect_authority_off_s": float(
            direct["risk_effect_authority_off"]["mean_effect"]
        ),
        "first_stage_status": first_stage["status"],
        "authority_on_requested_fraction": float(
            first_stage["by_authority"]["on"]["any_channel_requested_fraction"]
        ),
        "authority_off_requested_fraction": float(
            first_stage["by_authority"]["off"]["any_channel_requested_fraction"]
        ),
        "wall_time_status": sf4_wall["status"],
        "wall_time_rollout_means_ms": wall_metrics,
        "behavioural_authority_effects": behavioural_facts,
        "factual_solver_attempts": int(controller_full["factual_solver_attempts"]),
        "controller_accepted_attempts": int(
            controller_full["controller_accepted_attempts"]
        ),
        "fallback_or_nonaccepted_attempts": int(
            controller_full["fallback_or_nonaccepted_attempts"]
        ),
    }
    activity_boundary = (
        "Measured supervisor channels were activated, so the assignment contrast has "
        "an observed first stage."
        if first_stage["status"] == "active"
        else first_stage["claim_limit_if_inactive"]
    )
    first_stage_tex = r"\texttt{" + latex_escape(first_stage["status"]) + "}"
    sf4_text = (
        r"\paragraph{Prospective corrected-supervisor authority ablation.} "
        f"Across the 80 preregistered rollouts and ten paired init clusters, the primary "
        f"DID $(adaptive-fixed\\mbox{{-}}medium)_{{on}}-(adaptive-fixed\\mbox{{-}}medium)_{{off}}$ "
        f"on failure-penalised completion time was {sf4_facts['primary_did_s']:+.3f}~s "
        f"(cluster-bootstrap 95\\% CI [{ci[0]:+.3f}, {ci[1]:+.3f}]; exact "
        f"two-sided sign-flip sensitivity value "
        f"{sf4_facts['primary_sign_flip_sensitivity']:.4f}). The direct adaptive-minus-"
        f"fixed-medium effects were {sf4_facts['risk_effect_authority_on_s']:+.3f}~s "
        f"with authority on and {sf4_facts['risk_effect_authority_off_s']:+.3f}~s with "
        f"authority off. The implementation gate passed; first-stage status was "
        f"{first_stage_tex}, with any-channel request "
        f"fractions {sf4_facts['authority_on_requested_fraction']:.3f} (on) and "
        f"{sf4_facts['authority_off_requested_fraction']:.3f} (off). {activity_boundary} "
        f"The signed behavioural-authority results were: "
        + "; ".join(behavioural_sentences)
        + ". Positive means a larger named endpoint, not automatically a benefit; "
        "missing event-clock effects remain NA/censored and never trigger replacement "
        "rollouts. "
        f"Server-side authority-on/off ego-policy rollout means were P50 "
        f"{wall_pair('ego_policy_p50')}~ms, P95 {wall_pair('ego_policy_p95')}~ms and P99 "
        f"{wall_pair('ego_policy_p99')}~ms; authority-on/off shared-prediction values were "
        f"P50 {wall_pair('prediction_p50')}~ms, P95 {wall_pair('prediction_p95')}~ms and P99 "
        f"{wall_pair('prediction_p99')}~ms. "
        "These machine-specific run-step diagnostics are separately timed: their sum is "
        "not a measured end-to-end loop latency, and neither is a deployment or real-time "
        "guarantee. Missing/non-finite secondary timing remains NA and is never imputed. "
        "Factual controller acceptance and raw solver statuses "
        "remain separately reported, and zero first-stage activity would be retained as "
        "a scientific outcome rather than used to trigger more simulation."
    )

    def masking_pattern(on: float | None, off: float | None) -> str:
        if on is None or off is None:
            return "censored_or_undefined"
        difference = on - off
        tolerance = 1.0e-9 * max(1.0, abs(on), abs(off))
        if abs(difference) <= tolerance:
            return "near_null_interaction_point_pattern"
        if on * off < 0.0:
            return "direction_reversing_point_pattern"
        if abs(on) < abs(off):
            return "masking_like_attenuation_point_pattern"
        return "amplifying_like_point_pattern"

    interpretation_patterns: dict[str, str] = {}
    if first_stage["status"] == "active":
        completion_pattern = masking_pattern(
            sf4_facts["risk_effect_authority_on_s"],
            sf4_facts["risk_effect_authority_off_s"],
        )
        interpretation_patterns["failure_penalized_completion_time_s"] = completion_pattern
        for metric, label, _ in sf4_behavioural_metrics:
            entries = behavioural_facts[metric]
            interpretation_patterns[label] = masking_pattern(
                entries["risk_effect_authority_on"]["mean_effect"],
                entries["risk_effect_authority_off"]["mean_effect"],
            )
        pattern_text = "; ".join(
            f"{label}: {pattern.replace('_', '-')}"
            for label, pattern in interpretation_patterns.items()
        )
        discussion_text = (
            r"\paragraph{What the supervisor ablation identifies.} "
            "The measured behavioural channels were active, so the authority-on/off "
            "assignment provides an observed first stage for this frozen Town05 give-way "
            "distribution. Comparing the adaptive-minus-fixed-medium effect with authority "
            "on versus off gives the following descriptive point patterns: "
            + pattern_text
            + ". Here masking-like means only that the absolute adaptive--fixed-medium "
            "contrast was smaller with authority on; amplifying-like means it was larger; "
            "direction-reversing and near-null labels are likewise algebraic summaries. "
            "They do not assign benefit or harm, override the cluster intervals or censored "
            "event clocks, establish the supervisor as the sole cause, or generalise beyond "
            "the frozen predictor/estimator/risk/SMPC stack. The prospective authority "
            "intervention estimates a bounded interaction contrast; whether that contrast "
            "supports a non-zero interaction is determined by its cluster interval and the "
            "observed first stage. Predictor, estimator, "
            "risk allocation, collision monitoring and SMPC constraints remain shared."
        )
        conclusion_pattern_labels = {
            "masking_like_attenuation_point_pattern": "attenuation",
            "amplifying_like_point_pattern": "amplification",
            "direction_reversing_point_pattern": "direction reversal",
            "near_null_interaction_point_pattern": "near-null",
        }
        if completion_pattern not in conclusion_pattern_labels:
            raise ValueError(
                "Active primary completion point-pattern is undefined or censored"
            )
        conclusion_pattern = conclusion_pattern_labels[completion_pattern]
        pattern_article = "an" if conclusion_pattern[0] in "aeiou" else "a"
        ci_spans_zero = ci[0] <= 0.0 <= ci[1]
        ci_relation = "spans zero" if ci_spans_zero else "does not span zero"
        conclusion_text = (
            r"\paragraph{Bounded supervisor-authority conclusion.} "
            "In the frozen Town05/B1 adaptive-versus-fixed-medium ablation, the primary "
            f"failure-penalised completion DID was {sf4_facts['primary_did_s']:+.3f}~s "
            f"(cluster-bootstrap 95\\% CI [{ci[0]:+.3f}, {ci[1]:+.3f}]); the interval "
            f"{ci_relation}, and comparing the authority-on versus authority-off direct "
            f"contrasts produced {pattern_article} {conclusion_pattern} point-pattern. "
            "That algebraic pattern and its interval uncertainty do not establish benefit "
            "or harm and do not make the supervisor the sole cause. The claim is confined "
            "to this Town05/B1 adaptive-versus-fixed-medium comparison and bounded by the "
            "shared B1 predictor, estimator-to-risk interface, risk-allocation "
            "implementation and SMPC constraints."
        )
    else:
        interpretation_patterns["identification_status"] = (
            "not_identified_inactive_first_stage"
        )
        discussion_text = (
            r"\paragraph{What the supervisor ablation identifies.} "
            "Authority assignment passed its implementation gate, but no measured "
            "behavioural channel was activated on this distribution. The experiment "
            "therefore does not identify masking, amplification or a null supervisor "
            "interaction conditional on an active intervention. This inactive first stage "
            "is a scientific outcome, not an integrity failure or a reason to replace "
            "rollouts; it cannot establish the supervisor as the sole cause. Predictor, "
            "estimator, risk allocation, collision monitoring and SMPC constraints remain "
            "shared, so conclusions stay limited to implementation validity and the "
            "observed no-activation boundary."
        )
        completion_pattern = "not_identified_inactive_first_stage"
        ci_spans_zero = None
        conclusion_text = (
            r"\paragraph{Bounded supervisor-authority conclusion.} "
            "In the frozen Town05/B1 adaptive-versus-fixed-medium ablation, authority "
            "assignment passed its implementation gate, but the first stage was inactive "
            "because no measured supervisor behavioural channel activated. Consequently, "
            "masking, amplification, direction reversal and a null supervisor interaction "
            "are not identified; the inactive first stage is a scientific outcome rather "
            "than an integrity failure. This result does not make the supervisor the sole "
            "cause and is bounded by the shared B1 predictor, estimator-to-risk interface, "
            "risk-allocation implementation and SMPC constraints."
        )
    return {
        "schema_version": "supervisor_feedback_result_narrative_v1",
        "sf1": {"text": sf1_text, "facts": sf1_facts},
        "sf2": {"text": sf2_text, "facts": sf2_facts},
        "sf4": {"text": sf4_text, "facts": sf4_facts},
        "discussion": {
            "text": discussion_text,
            "facts": {
                "first_stage_status": first_stage["status"],
                "point_patterns": interpretation_patterns,
                "sole_cause_claim": False,
                "benefit_or_harm_assigned_from_sign_alone": False,
            },
        },
        "conclusion": {
            "text": conclusion_text,
            "facts": {
                "first_stage_status": first_stage["status"],
                "primary_completion_point_pattern": completion_pattern,
                "primary_completion_did_s": sf4_facts["primary_did_s"],
                "primary_completion_ci95_s": ci,
                "primary_completion_ci_spans_zero": ci_spans_zero,
                "sole_cause_claim": False,
                "scope": "Town05/B1/adaptive-versus-fixed-medium",
                "sentence_count": 3,
            },
        },
        "source_sha256": {
            path.relative_to(repo).as_posix(): sha256(path) for path in source_paths
        },
    }


def build_wrapper(
    repo: Path,
    asset_paths: Mapping[str, Path],
    narrative: Mapping[str, Any],
) -> str:
    lines = [
        "% Generated final supervisor-feedback Results insertion; do not hand edit.",
        "% Evidence IDs below are locators. The following \\input commands carry the evidence.",
        r"\paragraph{Supervisor, solver and authority checks.}",
        str(narrative["sf1"]["text"]),
    ]
    groups = (
        (
            (
                "SF1_BEHAVIOUR_APPROACH_STOP",
                "SF1_BEHAVIOUR_RELEASE_LATENCY",
                "SF1_BEHAVIOUR_PAIRED_RISK_CONTRASTS",
            ),
            "sf2",
        ),
        (
            (
                "SF2_ATTEMPTED_SOLVE_COST_QUANTILES",
                "SF2_ATTEMPTED_SOLVE_ACCEPTANCE",
                "SF2_PAIRED_COST_ACCEPTANCE_CONTRASTS",
                "SF2_RAW_SOLVER_FAILURE_TAXONOMY",
                "SF2_FAILURE_AFFECTED_ROLLOUT_OUTCOMES",
                "SF2_DEADLINE_EXCEEDANCE",
            ),
            "sf4",
        ),
        (
            (
                "SF4_PRIMARY_DID_COMPLETION",
                "SF4_BEHAVIOURAL_AUTHORITY_EFFECTS",
                "SF4_MANIPULATION_AUTHORITY",
                "SF4_COMPUTATIONAL_WALL_TIME",
                "SF4_CONTROLLER_ACCEPTANCE_AND_SOLVER_STATUS",
            ),
            None,
        ),
    )
    observed_ids: list[str] = []
    for evidence_ids, next_narrative in groups:
        for evidence_id in evidence_ids:
            observed_ids.append(evidence_id)
            path = asset_paths[evidence_id]
            lines.append(f"% EVIDENCE: {evidence_id}")
            lines.append(r"\input{" + latex_input_for(repo, path) + "}")
        if next_narrative is not None:
            lines.append(str(narrative[next_narrative]["text"]))
    if tuple(observed_ids) != tuple(SUPERVISOR_CONTENT_EVIDENCE_IDS):
        raise AssertionError("Wrapper grouping drifted from the evidence-ID contract")
    return "\n".join(lines) + "\n"


def build_discussion_wrapper(narrative: Mapping[str, Any]) -> str:
    return "\n".join(
        (
            "% Generated final supervisor-feedback Discussion insertion; do not hand edit.",
            str(narrative["discussion"]["text"]),
        )
    ) + "\n"


def build_conclusion_wrapper(narrative: Mapping[str, Any]) -> str:
    return "\n".join(
        (
            "% Generated final supervisor-feedback Conclusion insertion; do not hand edit.",
            str(narrative["conclusion"]["text"]),
        )
    ) + "\n"


def _default_latex_runner(
    *, latex_root: Path, output_dir: Path, main: Path
) -> tuple[Path, Path, Sequence[str], int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    command = (
        "latexmk",
        "-pdf",
        "-interaction=nonstopmode",
        "-halt-on-error",
        f"-outdir={output_dir}",
        main.name,
    )
    completed = subprocess.run(
        command,
        cwd=latex_root,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log_path = output_dir / "supervisor_feedback_final_latexmk.log"
    atomic_text(log_path, completed.stdout)
    pdf_path = output_dir / f"{main.stem}.pdf"
    return pdf_path, log_path, command, completed.returncode


def build(
    repo: Path,
    *,
    closure_payload: dict[str, Any] | None = None,
    latex_runner: Callable[..., tuple[Path, Path, Sequence[str], int]] | None = None,
) -> dict[str, Any]:
    repo = repo.resolve()
    closure = closure_payload or audit_supervisor_feedback_closure(repo)
    if closure.get("status") != "pass" or closure.get("final_release_eligible") is not True:
        raise RuntimeError("SF1--SF4 scientific closure is not final; refusing paper integration")

    results = repo / RESULTS_RELATIVE
    discussion = repo / DISCUSSION_RELATIVE
    conclusion = repo / CONCLUSION_RELATIVE
    main = repo / MAIN_RELATIVE
    for path in (results, discussion, conclusion, main):
        if not path.is_file():
            raise FileNotFoundError(path)
    visible_results = strip_latex_comments(results.read_text(encoding="utf-8"))
    if not re.search(
        r"\\input\s*\{\s*" + re.escape(WRAPPER_LATEX_INPUT) + r"\s*\}",
        visible_results,
    ):
        raise RuntimeError(
            f"{RESULTS_RELATIVE} must explicitly input {WRAPPER_LATEX_INPUT}"
        )
    if LEGACY_DIRECT_SF2_INPUT_PREFIX in visible_results:
        raise RuntimeError(
            "Results still directly inputs preliminary SF2 tables; final SF2 content "
            "must enter only through the canonical hash-bound wrapper"
        )
    if not re.search(
        r"\\input\s*\{\s*" + re.escape(SF3_RESULTS_LATEX_INPUT) + r"\s*\}",
        visible_results,
    ):
        raise RuntimeError(
            f"{RESULTS_RELATIVE} must retain the corrected SF3 table input "
            f"{SF3_RESULTS_LATEX_INPUT}"
        )
    obsolete_hits = obsolete_percentage_accuracy_claim_hits(
        sorted((repo / "docs/dissertation/latex").rglob("*.tex"))
    )
    if obsolete_hits:
        raise RuntimeError(
            "Obsolete 0.98-to-100 percentage-accuracy claim is present in final "
            f"manuscript sources: {obsolete_hits}"
        )
    if not sf3_retraction_explanation_complete(visible_results):
        raise RuntimeError(
            "Results must explicitly and correctly retract the old 0.98%-to-100% "
            "top-probability/oracle-best-mode statistic and identify the replacement "
            "NLL/ADE/FDE evidence contract"
        )
    visible_discussion = strip_latex_comments(
        discussion.read_text(encoding="utf-8")
    )
    visible_conclusion = strip_latex_comments(
        conclusion.read_text(encoding="utf-8")
    )
    if not re.search(
        r"\\input\s*\{\s*"
        + re.escape(DISCUSSION_WRAPPER_LATEX_INPUT)
        + r"\s*\}",
        visible_discussion,
    ):
        raise RuntimeError(
            f"{DISCUSSION_RELATIVE} must explicitly input "
            f"{DISCUSSION_WRAPPER_LATEX_INPUT}"
        )
    if not re.search(
        r"\\input\s*\{\s*"
        + re.escape(CONCLUSION_WRAPPER_LATEX_INPUT)
        + r"\s*\}",
        visible_conclusion,
    ):
        raise RuntimeError(
            f"{CONCLUSION_RELATIVE} must explicitly input "
            f"{CONCLUSION_WRAPPER_LATEX_INPUT}"
        )
    legacy_sf4_hits = legacy_sf4_production_reference_hits(
        visible_results + "\n" + visible_discussion + "\n" + visible_conclusion
    )
    if legacy_sf4_hits:
        raise RuntimeError(
            "Final manuscript references obsolete SF4 action-ablation production "
            f"paths or receipts: {legacy_sf4_hits}"
        )
    if MISLEADING_SOLVER_PHRASE_PATTERN.search(
        visible_results + "\n" + visible_discussion + "\n" + visible_conclusion
    ):
        raise RuntimeError(
            "Final manuscript uses the misleading phrase 'attempted-solve "
            "latency/feasibility'"
        )

    feedback = repo / "docs/paper/generated/supervisor_feedback_v1/r3_offline"
    deadline_csv = feedback / "02_cost_feasibility/deadline_exceedance.csv"
    if not deadline_csv.is_file():
        raise FileNotFoundError(deadline_csv)
    deadline_path = repo / DEADLINE_TEX_RELATIVE
    atomic_text(deadline_path, build_deadline_table(deadline_csv))

    asset_paths = {key: repo / relative for key, relative in CANONICAL_EVIDENCE_ASSETS.items()}
    for evidence_id, path in asset_paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"{evidence_id}: {path}")
        text = path.read_text(encoding="utf-8")
        if not re.search(r"\\begin\{table\*?\}", text) or len(text.strip()) < 100:
            raise RuntimeError(f"Paper-facing evidence is not a substantive table: {path}")
    data_source_paths = {
        evidence_id: tuple(repo / relative for relative in relatives)
        for evidence_id, relatives in CANONICAL_EVIDENCE_DATA_SOURCES.items()
    }
    for evidence_id, paths in data_source_paths.items():
        for path in paths:
            if not path.is_file() or path.stat().st_size == 0:
                raise FileNotFoundError(f"{evidence_id} scientific source: {path}")

    narrative = build_result_narrative(repo)
    wrapper = repo / WRAPPER_RELATIVE
    discussion_wrapper = repo / DISCUSSION_WRAPPER_RELATIVE
    conclusion_wrapper = repo / CONCLUSION_WRAPPER_RELATIVE
    atomic_text(wrapper, build_wrapper(repo, asset_paths, narrative))
    atomic_text(discussion_wrapper, build_discussion_wrapper(narrative))
    atomic_text(conclusion_wrapper, build_conclusion_wrapper(narrative))

    prebuild_inputs = {
        str(MAIN_RELATIVE): sha256(main),
        str(RESULTS_RELATIVE): sha256(results),
        str(DISCUSSION_RELATIVE): sha256(discussion),
        str(CONCLUSION_RELATIVE): sha256(conclusion),
        str(WRAPPER_RELATIVE): sha256(wrapper),
        str(DISCUSSION_WRAPPER_RELATIVE): sha256(discussion_wrapper),
        str(CONCLUSION_WRAPPER_RELATIVE): sha256(conclusion_wrapper),
        **{
            str(CANONICAL_EVIDENCE_ASSETS[evidence_id]): sha256(path)
            for evidence_id, path in asset_paths.items()
        },
    }

    output_dir = wrapper.parent / "latex_build"
    runner = latex_runner or _default_latex_runner
    pdf_path, log_path, command, returncode = runner(
        latex_root=main.parent, output_dir=output_dir, main=main
    )
    if returncode != 0 or not pdf_path.is_file() or pdf_path.stat().st_size == 0:
        raise RuntimeError(
            f"Final LaTeX build failed (returncode={returncode}); see {log_path}"
        )
    if not log_path.is_file():
        raise RuntimeError("Final LaTeX build did not produce a log")

    paper_inputs = {
        str(MAIN_RELATIVE): sha256(main),
        str(RESULTS_RELATIVE): sha256(results),
        str(DISCUSSION_RELATIVE): sha256(discussion),
        str(CONCLUSION_RELATIVE): sha256(conclusion),
        str(WRAPPER_RELATIVE): sha256(wrapper),
        str(DISCUSSION_WRAPPER_RELATIVE): sha256(discussion_wrapper),
        str(CONCLUSION_WRAPPER_RELATIVE): sha256(conclusion_wrapper),
        **{
            str(CANONICAL_EVIDENCE_ASSETS[evidence_id]): sha256(path)
            for evidence_id, path in asset_paths.items()
        },
    }
    if paper_inputs != prebuild_inputs:
        raise RuntimeError("A compiled manuscript/evidence source changed during latexmk")
    artifacts: dict[str, dict[str, Any]] = {}
    for relative, expected in paper_inputs.items():
        path = repo / relative
        artifacts[relative] = {
            "bytes": path.stat().st_size,
            "sha256": expected,
            "role": "compiled_manuscript_source",
        }
    for paths in data_source_paths.values():
        for path in paths:
            relative = path.relative_to(repo).as_posix()
            artifacts[relative] = {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "role": "canonical_scientific_data_source",
            }
    for relative, expected in narrative["source_sha256"].items():
        path = repo / relative
        if sha256(path) != expected:
            raise RuntimeError(f"Narrative source drifted during build: {relative}")
        if relative in artifacts:
            artifacts[relative]["result_narrative_source"] = True
        else:
            artifacts[relative] = {
                "bytes": path.stat().st_size,
                "sha256": expected,
                "role": "result_narrative_scientific_source",
                "result_narrative_source": True,
            }
    for path, role in ((pdf_path, "compiled_pdf"), (log_path, "latex_build_log")):
        relative = path.relative_to(repo).as_posix()
        artifacts[relative] = {
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "role": role,
        }

    receipt_names = (
        "SUPERVISOR_FEEDBACK_BEHAVIOUR_COMPLETE.json",
        "SUPERVISOR_FEEDBACK_02_COMPLETE.json",
        "SUPERVISOR_COMMENT_3_COMPLETE.json",
        "SF4_COMPLETE.json",
        "SF4_ANALYSIS_COMPLETE.json",
        "SF4_FULL_RAW_SNAPSHOT_COMPLETE.json",
    )
    closure_files = closure.get("verified_files_sha256") or {}
    source_receipts: dict[str, str] = {}
    for filename in receipt_names:
        matches = {
            relative: expected
            for relative, expected in closure_files.items()
            if relative.endswith("/" + filename) or relative == filename
        }
        if len(matches) != 1:
            raise RuntimeError(f"Closure did not provide exactly one {filename} hash")
        source_receipts.update(matches)

    generator_relative = "core/scripts/models/build_supervisor_feedback_paper_integration.py"
    generator = repo / generator_relative
    if not generator.is_file():
        raise FileNotFoundError(generator)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "pass",
        "final_release_eligible": True,
        "generated_by": generator_relative,
        "generated_by_sha256": sha256(generator),
        "evidence_ids": list(ALL_CONTENT_EVIDENCE_IDS),
        "wrapper_evidence_ids": list(SUPERVISOR_CONTENT_EVIDENCE_IDS),
        "results_evidence_ids": [SF3_RESULTS_EVIDENCE_ID],
        "canonical_wrapper": str(WRAPPER_RELATIVE),
        "canonical_wrapper_sha256": sha256(wrapper),
        "canonical_discussion_wrapper": str(DISCUSSION_WRAPPER_RELATIVE),
        "canonical_discussion_wrapper_sha256": sha256(discussion_wrapper),
        "canonical_conclusion_wrapper": str(CONCLUSION_WRAPPER_RELATIVE),
        "canonical_conclusion_wrapper_sha256": sha256(conclusion_wrapper),
        "canonical_evidence_assets": {
            evidence_id: str(CANONICAL_EVIDENCE_ASSETS[evidence_id])
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS
        },
        "canonical_evidence_data_sources": {
            evidence_id: [str(path) for path in CANONICAL_EVIDENCE_DATA_SOURCES[evidence_id]]
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS
        },
        "evidence_assets": {
            **{
                evidence_id: [
                    str(WRAPPER_RELATIVE),
                    str(CANONICAL_EVIDENCE_ASSETS[evidence_id]),
                ]
                for evidence_id in SUPERVISOR_CONTENT_EVIDENCE_IDS
            },
            SF3_RESULTS_EVIDENCE_ID: [
                str(RESULTS_RELATIVE),
                str(CANONICAL_EVIDENCE_ASSETS[SF3_RESULTS_EVIDENCE_ID]),
            ],
        },
        "evidence_data_sources": {
            evidence_id: [
                path.relative_to(repo).as_posix()
                for path in data_source_paths[evidence_id]
            ]
            for evidence_id in ALL_CONTENT_EVIDENCE_IDS
        },
        "manuscript_sources": {
            str(MAIN_RELATIVE): sha256(main),
            str(RESULTS_RELATIVE): sha256(results),
            str(DISCUSSION_RELATIVE): sha256(discussion),
            str(CONCLUSION_RELATIVE): sha256(conclusion),
        },
        "source_receipts": source_receipts,
        "result_narrative": narrative,
        "artifacts": artifacts,
        "latex_build": {
            "status": "pass",
            "returncode": returncode,
            "command": list(command),
            "source_sha256": paper_inputs,
            "pdf": pdf_path.relative_to(repo).as_posix(),
            "pdf_sha256": sha256(pdf_path),
            "log": log_path.relative_to(repo).as_posix(),
            "log_sha256": sha256(log_path),
        },
        "claim_boundary": (
            "Evidence IDs are locators only; final content eligibility comes from reachable "
            "hash-bound LaTeX inputs and a successful build of the current manuscript."
        ),
    }
    atomic_json(repo / MARKER_RELATIVE, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[3])
    parser.add_argument(
        "--ensure-provisional-discussion",
        action="store_true",
        help=(
            "create the fail-closed Discussion placeholder if it is missing, "
            "without running or weakening final closure"
        ),
    )
    parser.add_argument(
        "--ensure-provisional-conclusion",
        action="store_true",
        help=(
            "create the fail-closed Conclusion placeholder if it is missing, "
            "without running or weakening final closure"
        ),
    )
    parser.add_argument(
        "--ensure-provisional-wrappers",
        action="store_true",
        help="create both fail-closed Discussion and Conclusion placeholders if missing",
    )
    args = parser.parse_args()
    if args.ensure_provisional_wrappers:
        paths = (
            ensure_provisional_discussion_wrapper(args.repo_root),
            ensure_provisional_conclusion_wrapper(args.repo_root),
        )
        print(
            json.dumps(
                {"status": "present", "wrappers": [str(path) for path in paths]},
                indent=2,
            )
        )
        return 0
    if args.ensure_provisional_discussion:
        path = ensure_provisional_discussion_wrapper(args.repo_root)
        print(json.dumps({"status": "present", "wrapper": str(path)}, indent=2))
        return 0
    if args.ensure_provisional_conclusion:
        path = ensure_provisional_conclusion_wrapper(args.repo_root)
        print(json.dumps({"status": "present", "wrapper": str(path)}, indent=2))
        return 0
    result = build(args.repo_root)
    print(json.dumps({"status": result["status"], "marker": str(MARKER_RELATIVE)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
