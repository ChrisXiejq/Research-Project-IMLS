#!/usr/bin/env python3
"""Close supervisor feedback item 3 with a frozen, aggregation-safe audit.

This analysis deliberately performs no training and does not open CARLA.  It
re-reads the frozen B0/B1 test evaluations, reconstructs every comparison at a
named common aggregation level, and treats the five held-out ego
initialisations as the independent paired units.  It also rebuilds the simple
physical-baseline comparison without subtracting a sample-micro neural metric
from a rollout-macro baseline metric.

Only the Python standard library is required.  The generated completion marker
hash-binds every source and output so that this audit can be rerun in a clean
checkout.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import re
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = Path(
    "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit"
)

SOURCE_PATHS = {
    "b1_test_evaluation": Path(
        "docs/paper/generated/day8/final_test/B1/seed_37/test_all.json"
    ),
    "b0_test_evaluation": Path(
        "docs/paper/generated/day10/gaps/b0_offline/b0_test_all.json"
    ),
    "day8_test_summary": Path(
        "docs/paper/generated/day8/final_test/day8_frozen_test_summary.json"
    ),
    "day8_selection_freeze": Path(
        "docs/paper/generated/day8/final_test/DAY8_MODEL_SELECTION_FROZEN.json"
    ),
    "b0_bridge_summary": Path(
        "docs/paper/generated/day10/gaps/b0_offline/b0_frozen_offline_summary.json"
    ),
    "day7_split_audit": Path("docs/paper/generated/day7/day7_split_audit.json"),
    "split_balance_audit": Path(
        "docs/paper/generated/distinction_v1/06_split_balance/split_balance_audit.json"
    ),
    "training_budget_audit": Path(
        "docs/paper/generated/distinction_v1/03_training_budget/"
        "model_capacity_training_budget_audit.json"
    ),
    "b1_input_audit": Path(
        "docs/paper/generated/distinction_v1/02_input_ablations/"
        "b1_base_input_diagnostics.json"
    ),
    "physical_baseline_samples": Path(
        "docs/paper/generated/distinction_v1/01_physical_baselines/"
        "physical_baseline_sample_metrics.csv"
    ),
}

CLAIM_ASSET_ROOTS = (
    Path("docs/paper/generated/distinction_v1"),
    Path("docs/paper/generated/paper_assets_v1"),
    Path("docs/dissertation/latex"),
)
TEXT_SUFFIXES = {".csv", ".json", ".md", ".tex", ".txt", ".yaml", ".yml"}
EXPECTED_INIT_KEYS = tuple(f"ego_init_{value:02d}" for value in range(46, 51))
EXPECTED_TEST_JSONL_SHA256 = (
    "29291fe2a172047267c3a0c4c3d5693519f550881010a965fb60166a5013d770"
)
EXPECTED_TEST_JSONL_BYTES = 5_673_913
EXPECTED_ANCHORS_SHA256 = (
    "52ab777b9bf695ed56f069b96cbce337014a47f457ed19c638abfb1cde6aa982"
)
EXPECTED_ANCHORS_BYTES = 6_528
EXPECTED_EVALUATION_SCHEMA = "multipath_accuracy_calibration_v2"
EXPECTED_CALIBRATION_SCHEMA = "multipath_posthoc_calibration_v2"
EXPECTED_PER_INIT_SAMPLE_SIGNATURE = (
    "049eb15076543a54371d9bebd3452ecb02ea9874f54cf72e29a115120d2e2745"
)
EXPECTED_PER_ROLLOUT_SAMPLE_SIGNATURE = (
    "023009fc0e623aaf638a7dd1726ecde3fc1bdb9dd7707fb4c123a87780f96e52"
)
METRICS = (
    ("top1_ADE_mean", "top1_ADE_m", "lower"),
    ("top1_FDE_mean", "top1_FDE_m", "lower"),
    (
        "trajectory_mixture_NLL_per_step_mean",
        "trajectory_mixture_NLL_nats_per_step",
        "lower",
    ),
)

# The old result appeared in prose as a percentage-accuracy jump.  Requiring
# the percent sign on 100 avoids false positives from raw simulation columns
# while still catching variants such as "0.98 to 100%" and "0.98% -> 100%".
OLD_PERCENTAGE_ACCURACY_PATTERNS = (
    re.compile(
        r"(?i)(?:accuracy|improv(?:e|ed|ement|ing))?[^\n]{0,100}"
        r"\b0[.,]98\s*%?\s*(?:to|into|->|--?>|→|–|—)\s*100(?:[.,]0+)?\s*%"
    ),
    re.compile(
        r"(?i)\b0[.,]98\s*%[^\n]{0,100}\b100(?:[.,]0+)?\s*%"
        r"[^\n]{0,100}(?:accuracy|improv(?:e|ed|ement|ing))"
    ),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected JSON object: {path}")
    return payload


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")
    temporary.replace(path)


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(value)
    temporary.replace(path)


def atomic_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Refusing to write empty CSV: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        writer = csv.DictWriter(
            handle,
            fieldnames=list(rows[0]),
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def finite(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"Non-finite metric {label}: {value!r}")
    return result


def require_pass(payload: Mapping[str, Any], label: str) -> None:
    if payload.get("status") != "pass":
        raise ValueError(f"Source gate is not pass: {label}")


def aggregation_metrics(
    evaluation: Mapping[str, Any], aggregation: str
) -> dict[str, float]:
    if aggregation == "rollout_macro":
        source = evaluation["uncalibrated"]["rollout_aggregation"]["macro_mean"]
    elif aggregation == "held_out_init_group_macro":
        source = evaluation["uncalibrated"]["init_group_aggregation"]["macro_mean"]
    else:
        raise ValueError(f"Unsupported aggregation: {aggregation}")
    return {
        output_name: finite(source[source_name], f"{aggregation}:{source_name}")
        for source_name, output_name, _ in METRICS
    }


def exact_sign_flip_paired_p(effects: Sequence[float]) -> float:
    """Exact sign-flip sensitivity value under paired-effect symmetry."""

    values = [finite(value, "paired effect") for value in effects]
    if not values:
        raise ValueError("Exact paired test requires at least one effect")
    observed = abs(statistics.fmean(values))
    tolerance = 1.0e-12
    extreme = 0
    total = 0
    magnitudes = [abs(value) for value in values]
    for signs in itertools.product((-1.0, 1.0), repeat=len(values)):
        permuted = abs(
            statistics.fmean(sign * magnitude for sign, magnitude in zip(signs, magnitudes))
        )
        extreme += int(permuted + tolerance >= observed)
        total += 1
    return extreme / total


def _count_signature(values: Mapping[str, int]) -> str:
    payload = json.dumps(
        {str(key): int(value) for key, value in values.items()},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def frozen_test_population_contract(
    b0: Mapping[str, Any], b1: Mapping[str, Any]
) -> dict[str, Any]:
    """Hash- and key-bind the exact test population shared by B0 and B1."""

    def artifact(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
        value = payload.get(name)
        return value if isinstance(value, Mapping) else {}

    def init_counts(payload: Mapping[str, Any]) -> dict[str, int]:
        groups = _per_init_metrics(payload)
        return {str(key): int(value["samples"]) for key, value in groups.items()}

    def rollout_counts(payload: Mapping[str, Any]) -> dict[str, int]:
        per_rollout = payload["uncalibrated"]["rollout_aggregation"][
            "per_rollout"
        ]
        if not isinstance(per_rollout, Mapping):
            raise TypeError("uncalibrated per-rollout evidence must be a mapping")
        return {
            str(key): int(value["samples"])
            for key, value in per_rollout.items()
        }

    b0_jsonl, b1_jsonl = artifact(b0, "jsonl"), artifact(b1, "jsonl")
    b0_anchors, b1_anchors = (
        artifact(b0, "anchors_artifact"),
        artifact(b1, "anchors_artifact"),
    )
    b0_init, b1_init = init_counts(b0), init_counts(b1)
    b0_rollout, b1_rollout = rollout_counts(b0), rollout_counts(b1)
    b0_calibration, b1_calibration = (
        artifact(b0, "calibration"),
        artifact(b1, "calibration"),
    )
    checks = {
        "jsonl_sha256_exact_and_equal": (
            b0_jsonl.get("sha256")
            == b1_jsonl.get("sha256")
            == EXPECTED_TEST_JSONL_SHA256
        ),
        "jsonl_bytes_exact_and_equal": (
            int(b0_jsonl.get("bytes", -1))
            == int(b1_jsonl.get("bytes", -2))
            == EXPECTED_TEST_JSONL_BYTES
        ),
        "anchors_sha256_exact_and_equal": (
            b0_anchors.get("sha256")
            == b1_anchors.get("sha256")
            == EXPECTED_ANCHORS_SHA256
        ),
        "anchors_bytes_exact_and_equal": (
            int(b0_anchors.get("bytes", -1))
            == int(b1_anchors.get("bytes", -2))
            == EXPECTED_ANCHORS_BYTES
        ),
        "evaluation_contract_exact_and_equal": all(
            (
                b0.get("split") == b1.get("split") == "test",
                b0.get("subset") == b1.get("subset") == "all",
                int(b0.get("horizon", -1)) == int(b1.get("horizon", -2)) == 10,
                b0.get("evaluation_schema_version")
                == b1.get("evaluation_schema_version")
                == EXPECTED_EVALUATION_SCHEMA,
                b0.get("calibration_fit_uses_test") is False,
                b1.get("calibration_fit_uses_test") is False,
                b0_calibration.get("fit_split")
                == b1_calibration.get("fit_split")
                == "val",
                b0_calibration.get("calibration_schema_version")
                == b1_calibration.get("calibration_schema_version")
                == EXPECTED_CALIBRATION_SCHEMA,
                int(b0_calibration.get("horizon", -1))
                == int(b1_calibration.get("horizon", -2))
                == 10,
                b0.get("uses_interaction_context") is False,
                b1.get("uses_interaction_context") is False,
                int(b0.get("model_input_count", -1))
                == int(b1.get("model_input_count", -2))
                == 2,
            )
        ),
        "aggregate_counts_exact_and_equal": all(
            (
                int(b0.get("samples", -1)) == int(b1.get("samples", -2)) == 315,
                int(b0.get("independent_rollouts", -1))
                == int(b1.get("independent_rollouts", -2))
                == 20,
                int(b0.get("independent_init_groups", -1))
                == int(b1.get("independent_init_groups", -2))
                == 5,
            )
        ),
        "per_init_keys_and_counts_exact_and_equal": (
            b0_init == b1_init
            and tuple(sorted(b0_init)) == EXPECTED_INIT_KEYS
            and sum(b0_init.values()) == 315
            and _count_signature(b0_init) == EXPECTED_PER_INIT_SAMPLE_SIGNATURE
        ),
        "per_rollout_keys_and_counts_exact_and_equal": (
            b0_rollout == b1_rollout
            and len(b0_rollout) == 20
            and sum(b0_rollout.values()) == 315
            and _count_signature(b0_rollout)
            == EXPECTED_PER_ROLLOUT_SAMPLE_SIGNATURE
        ),
    }
    return {
        "schema_version": "frozen_test_population_contract_v1",
        "status": "pass" if all(checks.values()) else "fail",
        "checks": checks,
        "test_jsonl": {
            "sha256": EXPECTED_TEST_JSONL_SHA256,
            "bytes": EXPECTED_TEST_JSONL_BYTES,
        },
        "anchors": {
            "sha256": EXPECTED_ANCHORS_SHA256,
            "bytes": EXPECTED_ANCHORS_BYTES,
        },
        "evaluation_schema_version": EXPECTED_EVALUATION_SCHEMA,
        "calibration_schema_version": EXPECTED_CALIBRATION_SCHEMA,
        "horizon": 10,
        "subset": "all",
        "per_init_sample_signature": EXPECTED_PER_INIT_SAMPLE_SIGNATURE,
        "per_rollout_sample_signature": EXPECTED_PER_ROLLOUT_SAMPLE_SIGNATURE,
        "per_init_samples": b1_init,
        "per_rollout_samples": b1_rollout,
    }


def scan_old_percentage_accuracy(
    roots: Iterable[Path], *, relative_to: Path | None = None
) -> dict[str, Any]:
    def explicitly_withdrawn_context(text: str, start: int, end: int) -> bool:
        """Allow disclosure of the old number only inside its own retraction.

        The supervisor explicitly asked why the old number was implausible, so
        silently deleting it would make the paper less auditable.  We retain a
        fail-closed distinction between a positive result claim and a paragraph
        that names, withdraws and says the number is not evidence.
        """

        paragraph_start = text.rfind("\n\n", 0, start)
        paragraph_end = text.find("\n\n", end)
        if paragraph_start < 0:
            paragraph_start = max(0, start - 600)
        else:
            paragraph_start += 2
        if paragraph_end < 0:
            paragraph_end = min(len(text), end + 600)
        context = text[paragraph_start:paragraph_end]
        has_retraction = re.search(
            r"\b(?:withdraw(?:n|s|ing)?|retract(?:ed|s|ing)?|invalid|"
            r"discredited|superseded|discard(?:ed|s|ing)?)\b",
            context,
            re.I,
        )
        has_negative_evidence_status = re.search(
            r"\bnot\b.{0,140}\b(?:evidence|trajectory[- ]accuracy|endpoint)\b"
            r"|\b(?:not|no longer)\s+(?:valid|current)\s+evidence\b"
            r"|\bmust\s+not\s+be\s+used\b",
            context,
            re.I | re.S,
        )
        return bool(has_retraction and has_negative_evidence_status)

    def display(path: Path) -> str:
        resolved = path.resolve()
        if relative_to is not None:
            try:
                return resolved.relative_to(relative_to.resolve()).as_posix()
            except ValueError:
                pass
        return str(resolved)

    resolved_roots = sorted({path.resolve() for path in roots}, key=str)
    scanned_files = 0
    scanned_bytes = 0
    hits: list[dict[str, Any]] = []
    for root in resolved_roots:
        if not root.is_dir():
            raise FileNotFoundError(root)
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            raw = path.read_bytes()
            scanned_files += 1
            scanned_bytes += len(raw)
            text = raw.decode("utf-8", errors="replace")
            for pattern_index, pattern in enumerate(OLD_PERCENTAGE_ACCURACY_PATTERNS):
                for match in pattern.finditer(text):
                    if explicitly_withdrawn_context(text, match.start(), match.end()):
                        continue
                    line = text.count("\n", 0, match.start()) + 1
                    hits.append(
                        {
                            "path": display(path),
                            "line": line,
                            "pattern_index": pattern_index,
                            "matched_text": match.group(0)[:240],
                        }
                    )
    return {
        "status": "pass" if not hits else "fail",
        "rule": (
            "No positive prose claim may report the superseded 0.98/0.98%-to-100% "
            "mode-ranking hit-rate jump. It may be named only inside an explicit "
            "withdrawal that marks it as not evidence; current ML claims must use "
            "frozen NLL/ADE/FDE."
        ),
        "scanned_roots": [display(path) for path in resolved_roots],
        "scanned_files": scanned_files,
        "scanned_bytes": scanned_bytes,
        "hit_count": len(hits),
        "hits": hits,
    }


def _per_init_metrics(evaluation: Mapping[str, Any]) -> Mapping[str, Mapping[str, Any]]:
    return evaluation["uncalibrated"]["init_group_aggregation"]["per_init_group"]


def build_frozen_test_tables(
    b0: Mapping[str, Any], b1: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    summary_rows: list[dict[str, Any]] = []
    contrast_rows: list[dict[str, Any]] = []
    for aggregation in ("rollout_macro", "held_out_init_group_macro"):
        values = {
            "B0": aggregation_metrics(b0, aggregation),
            "B1": aggregation_metrics(b1, aggregation),
        }
        for variant in ("B0", "B1"):
            summary_rows.append(
                {
                    "variant": variant,
                    "aggregation_level": aggregation,
                    "full_horizon_windows": int(b1["samples"]),
                    "rollouts": int(b1["independent_rollouts"]),
                    "held_out_init_groups": int(b1["independent_init_groups"]),
                    **values[variant],
                }
            )
        contrast_rows.append(
            {
                "contrast": "B1_minus_B0",
                "aggregation_level": aggregation,
                "full_horizon_windows": int(b1["samples"]),
                "rollouts": int(b1["independent_rollouts"]),
                "held_out_init_groups": int(b1["independent_init_groups"]),
                **{
                    f"delta_{output_name}": values["B1"][output_name]
                    - values["B0"][output_name]
                    for _, output_name, _ in METRICS
                },
            }
        )

    b0_groups = _per_init_metrics(b0)
    b1_groups = _per_init_metrics(b1)
    if tuple(sorted(b0_groups)) != EXPECTED_INIT_KEYS or tuple(sorted(b1_groups)) != EXPECTED_INIT_KEYS:
        raise ValueError(
            "Frozen test must contain exactly paired init groups 46--50: "
            f"B0={sorted(b0_groups)}, B1={sorted(b1_groups)}"
        )
    paired_rows: list[dict[str, Any]] = []
    for key in EXPECTED_INIT_KEYS:
        b0_row = b0_groups[key]
        b1_row = b1_groups[key]
        if int(b0_row["samples"]) != int(b1_row["samples"]):
            raise ValueError(f"B0/B1 sample mismatch in {key}")
        record: dict[str, Any] = {
            "ego_init_id": int(key.rsplit("_", 1)[-1]),
            "paired_unit": "held_out_ego_initialisation",
            "within_unit_aggregation": "mean_over_overlapping_full_horizon_windows",
            "windows": int(b1_row["samples"]),
        }
        for source_name, output_name, _ in METRICS:
            b0_value = finite(b0_row[source_name], f"B0:{key}:{source_name}")
            b1_value = finite(b1_row[source_name], f"B1:{key}:{source_name}")
            record[f"B0_{output_name}"] = b0_value
            record[f"B1_{output_name}"] = b1_value
            record[f"B1_minus_B0_{output_name}"] = b1_value - b0_value
            record[f"B1_better_{output_name}"] = int(b1_value < b0_value)
        paired_rows.append(record)

    paired_summary: list[dict[str, Any]] = []
    for _, output_name, preferred in METRICS:
        effects = [float(row[f"B1_minus_B0_{output_name}"]) for row in paired_rows]
        paired_summary.append(
            {
                "metric": output_name,
                "preferred_direction": preferred,
                "independent_paired_init_groups": len(effects),
                "favourable_init_count": sum(effect < 0.0 for effect in effects),
                "mean_B1_minus_B0": statistics.fmean(effects),
                "median_B1_minus_B0": statistics.median(effects),
                "minimum_B1_minus_B0": min(effects),
                "maximum_B1_minus_B0": max(effects),
                "two_sided_exact_sign_flip_p": exact_sign_flip_paired_p(effects),
                "inference_note": (
                    "The five held-out ego initialisations are independent units; "
                    "overlapping prediction windows are not replications. The exact "
                    "two-sided sign-flip value is a sensitivity analysis under a "
                    "symmetric paired-cluster-effect assumption, not treatment-"
                    "randomisation inference."
                ),
            }
        )
    return summary_rows, contrast_rows, paired_rows, paired_summary


def render_rollout_macro_latex(
    summary_rows: Sequence[Mapping[str, Any]],
    contrast_rows: Sequence[Mapping[str, Any]],
) -> str:
    """Render a directly inputtable, aggregation-explicit B0/B1 table."""

    rows = {
        str(row["variant"]): row
        for row in summary_rows
        if row["aggregation_level"] == "rollout_macro"
    }
    contrast = next(
        row
        for row in contrast_rows
        if row["aggregation_level"] == "rollout_macro"
    )
    if set(rows) != {"B0", "B1"}:
        raise ValueError(f"Expected rollout-macro B0/B1 rows, found {sorted(rows)}")

    def metric_row(label: str, row: Mapping[str, Any]) -> str:
        return (
            f"{label} & {int(row['full_horizon_windows'])} & "
            f"{int(row['rollouts'])} & {int(row['held_out_init_groups'])} & "
            f"{float(row['trajectory_mixture_NLL_nats_per_step']):.3f} & "
            f"{float(row['top1_ADE_m']):.3f} & "
            f"{float(row['top1_FDE_m']):.3f} \\\\"
        )

    delta_row = (
        "B1$-$B0 & 315 & 20 & 5 & "
        f"{float(contrast['delta_trajectory_mixture_NLL_nats_per_step']):+.3f} & "
        f"{float(contrast['delta_top1_ADE_m']):+.3f} & "
        f"{float(contrast['delta_top1_FDE_m']):+.3f} \\\\"
    )
    return "\n".join(
        [
            r"\begin{center}",
            r"\refstepcounter{table}",
            r"\label{tab:finetune-b0-b1-rollout-macro}",
            r"\small",
            (
                r"Table~\thetable: Frozen B0/B1 test results at one common rollout-macro "
                r"aggregation. Every metric is first averaged within rollout and "
                r"then over 20 rollouts. The 315 overlapping windows are descriptive "
                r"observations, not independent replications; lower is better.\par\smallskip"
            ),
            r"\begin{tabular}{@{}lrrrrrr@{}}",
            r"\toprule",
            "Stack/contrast & Windows & Rollouts & Init groups & NLL & ADE (m) & FDE (m) \\\\",
            r"\midrule",
            metric_row("B0", rows["B0"]),
            metric_row("B1", rows["B1"]),
            r"\midrule",
            delta_row,
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{center}",
            "",
        ]
    )


def render_paired_init_latex(
    paired_rows: Sequence[Mapping[str, Any]],
    paired_summary: Sequence[Mapping[str, Any]],
) -> str:
    """Render paired init-group effects without treating windows as replicates."""

    summary = {str(row["metric"]): row for row in paired_summary}
    required = {
        "trajectory_mixture_NLL_nats_per_step",
        "top1_ADE_m",
        "top1_FDE_m",
    }
    if set(summary) != required:
        raise ValueError(f"Unexpected paired-summary metrics: {sorted(summary)}")

    rows: list[str] = []
    for row in paired_rows:
        all_favour = all(
            int(row[f"B1_better_{metric}"]) == 1 for metric in required
        )
        rows.append(
            f"{int(row['ego_init_id'])} & {int(row['windows'])} & "
            f"{float(row['B1_minus_B0_trajectory_mixture_NLL_nats_per_step']):+.3f} & "
            f"{float(row['B1_minus_B0_top1_ADE_m']):+.3f} & "
            f"{float(row['B1_minus_B0_top1_FDE_m']):+.3f} & "
            f"{'yes' if all_favour else 'no'} \\\\"
        )

    mean_row = (
        r"Init-macro mean & -- & "
        f"{float(summary['trajectory_mixture_NLL_nats_per_step']['mean_B1_minus_B0']):+.3f} & "
        f"{float(summary['top1_ADE_m']['mean_B1_minus_B0']):+.3f} & "
        f"{float(summary['top1_FDE_m']['mean_B1_minus_B0']):+.3f} & 5/5 \\\\"
    )
    p_nll = float(
        summary["trajectory_mixture_NLL_nats_per_step"][
            "two_sided_exact_sign_flip_p"
        ]
    )
    p_ade = float(summary["top1_ADE_m"]["two_sided_exact_sign_flip_p"])
    p_fde = float(summary["top1_FDE_m"]["two_sided_exact_sign_flip_p"])
    caption = (
        r"\caption{Paired frozen-test effects by held-out ego initialisation. "
        r"$\Delta=\mathrm{B1}-\mathrm{B0}$, so negative values favour B1. "
        r"The five initialisations, not their overlapping windows, are the "
        r"independent units. Exact two-sided sign-flip sensitivity values under "
        r"a symmetric paired-cluster-effect assumption (not treatment-"
        r"randomisation inference) are "
        f"{p_nll:.4f} for NLL, {p_ade:.4f} for ADE and {p_fde:.4f} for FDE.}}"
    )
    return "\n".join(
        [
            r"\begin{table}[t]",
            r"\centering\small",
            caption,
            r"\label{tab:finetune-b0-b1-paired-init}",
            r"\begin{tabular}{@{}lrrrrl@{}}",
            r"\toprule",
            "Init & Windows & $\\Delta$NLL & $\\Delta$ADE (m) & $\\Delta$FDE (m) & All lower? \\\\",
            r"\midrule",
            *rows,
            r"\midrule",
            mean_row,
            r"\bottomrule",
            r"\end{tabular}",
            r"\end{table}",
            "",
        ]
    )


def load_physical_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Physical-baseline source is empty: {path}")
    return rows


def build_physical_tables(
    source_rows: Sequence[Mapping[str, str]], b1: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[tuple[str, int], dict[str, list[float]]] = defaultdict(
        lambda: {"ADE": [], "FDE": []}
    )
    for row in source_rows:
        if row.get("split") != "test":
            continue
        baseline = str(row["baseline"])
        init_id = int(row["ego_init_id"])
        if init_id not in range(46, 51):
            raise ValueError(f"Unexpected physical-baseline test init: {init_id}")
        grouped[(baseline, init_id)]["ADE"].append(
            finite(row["ADE_m"], f"{baseline}:{init_id}:ADE")
        )
        grouped[(baseline, init_id)]["FDE"].append(
            finite(row["FDE_m"], f"{baseline}:{init_id}:FDE")
        )
    baselines = sorted({baseline for baseline, _ in grouped})
    if baselines != ["CA", "CV", "train_mean"]:
        raise ValueError(f"Unexpected physical baselines: {baselines}")

    b1_groups = _per_init_metrics(b1)
    paired_rows: list[dict[str, Any]] = []
    for baseline in baselines:
        for init_id in range(46, 51):
            values = grouped[(baseline, init_id)]
            if not values["ADE"] or not values["FDE"]:
                raise ValueError(f"Missing physical-baseline pair: {baseline}/init{init_id}")
            b1_group = b1_groups[f"ego_init_{init_id:02d}"]
            b1_ade = finite(b1_group["top1_ADE_mean"], "B1 ADE")
            b1_fde = finite(b1_group["top1_FDE_mean"], "B1 FDE")
            baseline_ade = statistics.fmean(values["ADE"])
            baseline_fde = statistics.fmean(values["FDE"])
            paired_rows.append(
                {
                    "baseline": baseline,
                    "ego_init_id": init_id,
                    "paired_unit": "held_out_ego_initialisation",
                    "within_unit_aggregation": "mean_over_full_horizon_windows",
                    "B1_top1_ADE_m": b1_ade,
                    "baseline_ADE_m": baseline_ade,
                    "B1_minus_baseline_ADE_m": b1_ade - baseline_ade,
                    "B1_ADE_better": int(b1_ade < baseline_ade),
                    "B1_top1_FDE_m": b1_fde,
                    "baseline_FDE_m": baseline_fde,
                    "B1_minus_baseline_FDE_m": b1_fde - baseline_fde,
                    "B1_FDE_better": int(b1_fde < baseline_fde),
                }
            )

    summary_rows: list[dict[str, Any]] = []
    for baseline in baselines:
        subset = [row for row in paired_rows if row["baseline"] == baseline]
        summary_rows.append(
            {
                "baseline": baseline,
                "aggregation_level": "held_out_init_group_macro",
                "independent_paired_init_groups": len(subset),
                "B1_top1_ADE_m": statistics.fmean(
                    float(row["B1_top1_ADE_m"]) for row in subset
                ),
                "baseline_ADE_m": statistics.fmean(
                    float(row["baseline_ADE_m"]) for row in subset
                ),
                "mean_B1_minus_baseline_ADE_m": statistics.fmean(
                    float(row["B1_minus_baseline_ADE_m"]) for row in subset
                ),
                "B1_ADE_better_init_count": sum(
                    int(row["B1_ADE_better"]) for row in subset
                ),
                "B1_top1_FDE_m": statistics.fmean(
                    float(row["B1_top1_FDE_m"]) for row in subset
                ),
                "baseline_FDE_m": statistics.fmean(
                    float(row["baseline_FDE_m"]) for row in subset
                ),
                "mean_B1_minus_baseline_FDE_m": statistics.fmean(
                    float(row["B1_minus_baseline_FDE_m"]) for row in subset
                ),
                "B1_FDE_better_init_count": sum(
                    int(row["B1_FDE_better"]) for row in subset
                ),
                "nll_comparison": (
                    "not_reported: physical-baseline diagonal-Gaussian NLL and "
                    "MultiPath mixture NLL are not the same estimand"
                ),
            }
        )
    return paired_rows, summary_rows


def validation_checks(
    *,
    b1_evaluation_path: Path,
    b0: Mapping[str, Any],
    b1: Mapping[str, Any],
    test_summary: Mapping[str, Any],
    selection: Mapping[str, Any],
    b0_bridge: Mapping[str, Any],
    split: Mapping[str, Any],
    balance: Mapping[str, Any],
    percentage_scan: Mapping[str, Any],
    population_contract: Mapping[str, Any],
    paired_rows: Sequence[Mapping[str, Any]],
    physical_summary: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    representatives = selection.get("representatives_for_single_test_pass", {})
    b1_frozen = representatives.get("B1", {})
    b1_summary_run = next(
        (run for run in test_summary.get("runs", []) if run.get("variant") == "B1"),
        None,
    )
    checks = [
        (
            "source_gates_pass",
            all(
                payload.get("status") == "pass"
                for payload in (
                    b0,
                    b1,
                    test_summary,
                    selection,
                    b0_bridge,
                    split,
                    balance,
                )
            ),
        ),
        (
            "same_frozen_test_population",
            population_contract.get("status") == "pass"
            and all((population_contract.get("checks") or {}).values()),
        ),
        (
            "selection_frozen_before_test",
            (
                selection.get("closed_loop_selected_variant") == "B1"
                and int(selection.get("closed_loop_selected_seed", -1)) == 37
                and selection.get("closed_loop_selection_locked_before_test") is True
                and selection.get("test_accessed_at_freeze") is False
                and test_summary.get("test_used_for_selection") is False
                and test_summary.get("retraining_or_retuning_after_test_permitted") is False
                and b0_bridge.get("test_used_for_selection") is False
            ),
        ),
        (
            "frozen_b1_hash_matches_test",
            (
                b1_frozen.get("model", {}).get("sha256_tree")
                == b1.get("model_artifact", {}).get("sha256_tree")
                and b1_summary_run is not None
                and b1_summary_run.get("artifact_sha256", {}).get("test_all")
                == sha256_file(b1_evaluation_path)
            ),
        ),
        (
            "rollout_disjoint_split_and_train_only_normalisation",
            (
                split.get("leakage_checks", {}).get("init_groups_disjoint") is True
                and split.get("leakage_checks", {}).get("four_cells_colocated_per_init")
                is True
                and split.get("leakage_checks", {}).get("normalization_train_only")
                is True
                and balance.get("checks", {}).get("duplicate_sample_keys") == 0
            ),
        ),
        (
            "five_paired_init_rows",
            [int(row["ego_init_id"]) for row in paired_rows] == list(range(46, 51)),
        ),
        (
            "all_three_metrics_favour_b1_in_each_init",
            all(
                int(row[f"B1_better_{metric}"]) == 1
                for row in paired_rows
                for metric in (
                    "trajectory_mixture_NLL_nats_per_step",
                    "top1_ADE_m",
                    "top1_FDE_m",
                )
            ),
        ),
        (
            "physical_baselines_same_aggregation",
            (
                len(physical_summary) == 3
                and all(
                    row.get("aggregation_level") == "held_out_init_group_macro"
                    and int(row.get("independent_paired_init_groups", 0)) == 5
                    for row in physical_summary
                )
            ),
        ),
        (
            "superseded_percentage_accuracy_absent",
            percentage_scan.get("status") == "pass"
            and int(percentage_scan.get("hit_count", -1)) == 0,
        ),
    ]
    return [
        {"check": name, "status": "pass" if passed else "fail"}
        for name, passed in checks
    ]


def relative_path(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve()))
    except ValueError:
        return str(path.resolve())


def build(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve()
    output = output.resolve()
    sources = {name: repo / path for name, path in SOURCE_PATHS.items()}
    for path in sources.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    b1 = load_json(sources["b1_test_evaluation"])
    b0 = load_json(sources["b0_test_evaluation"])
    test_summary = load_json(sources["day8_test_summary"])
    selection = load_json(sources["day8_selection_freeze"])
    b0_bridge = load_json(sources["b0_bridge_summary"])
    split = load_json(sources["day7_split_audit"])
    balance = load_json(sources["split_balance_audit"])
    budget = load_json(sources["training_budget_audit"])
    inputs = load_json(sources["b1_input_audit"])
    for name, payload in (
        ("B1 evaluation", b1),
        ("B0 evaluation", b0),
        ("test summary", test_summary),
        ("selection freeze", selection),
        ("B0 bridge", b0_bridge),
        ("split audit", split),
        ("balance audit", balance),
        ("budget audit", budget),
        ("input audit", inputs),
    ):
        require_pass(payload, name)

    summary_rows, contrast_rows, paired_rows, paired_summary = build_frozen_test_tables(
        b0, b1
    )
    physical_pairs, physical_summary = build_physical_tables(
        load_physical_rows(sources["physical_baseline_samples"]), b1
    )
    scan_roots = [repo / relative for relative in CLAIM_ASSET_ROOTS]
    percentage_scan = scan_old_percentage_accuracy(scan_roots, relative_to=repo)
    population_contract = frozen_test_population_contract(b0, b1)

    checks = validation_checks(
        b1_evaluation_path=sources["b1_test_evaluation"],
        b0=b0,
        b1=b1,
        test_summary=test_summary,
        selection=selection,
        b0_bridge=b0_bridge,
        split=split,
        balance=balance,
        percentage_scan=percentage_scan,
        population_contract=population_contract,
        paired_rows=paired_rows,
        physical_summary=physical_summary,
    )
    failures = [item for item in checks if item["status"] != "pass"]
    if failures:
        raise ValueError(f"Supervisor fine-tuning audit failed: {failures}")

    response = b0_bridge["subsets"]["response_active"]
    response_samples = int(response["B1"]["samples"])
    response_active = {
        "full_horizon_windows": response_samples,
        "fraction_of_all_full_horizon_windows": response_samples / int(b1["samples"]),
        "rollouts": int(response["B1"]["independent_rollouts"]),
        "held_out_init_groups": int(response["B1"]["independent_init_groups"]),
        "B0": {
            "top1_ADE_m": response["B0"]["top1_ADE_mean"],
            "top1_FDE_m": response["B0"]["top1_FDE_mean"],
            "uncalibrated_rollout_macro_NLL": response["B0"][
                "uncalibrated_rollout_macro_NLL"
            ],
            "calibrated_rollout_macro_NLL": response["B0"][
                "calibrated_rollout_macro_NLL"
            ],
        },
        "B1": {
            "top1_ADE_m": response["B1"]["top1_ADE_mean"],
            "top1_FDE_m": response["B1"]["top1_FDE_mean"],
            "uncalibrated_rollout_macro_NLL": response["B1"][
                "uncalibrated_rollout_macro_NLL"
            ],
            "calibrated_rollout_macro_NLL": response["B1"][
                "calibrated_rollout_macro_NLL"
            ],
        },
        "interpretation": (
            "The aggregate B1 point-error gain persists, but validation-frozen global "
            "calibration is worse in this small response-active tail."
        ),
    }

    variants = {row["variant"]: row for row in budget["variants"]}
    raster_shuffle = next(
        row for row in inputs["shuffle_aggregate"] if row["input"] == "raster"
    )
    past_shuffle = next(
        row for row in inputs["shuffle_aggregate"] if row["input"] == "past"
    )
    limitations = [
        "Inference is bounded to the frozen Town05 give-way distribution; there is no cross-map or real-road claim.",
        "The five held-out ego initialisations, not the 315 overlapping full-horizon windows, are the independent paired units.",
        (
            f"Only {response_samples}/315 full-horizon test windows "
            f"({100.0 * response_samples / 315.0:.2f}%) are response-active, so the "
            "aggregate result is dominated by non-active interaction periods."
        ),
        (
            f"B1 exposes {int(variants['B1']['trainable_parameters']):,} trainable "
            "parameters; the tested adapter configurations expose substantially fewer, "
            "so architecture-only causality is not identified."
        ),
        (
            f"{int(budget['fairness_checks']['runs_best_at_budget_boundary'])}/15 "
            "training runs selected the final allowed epoch; all three B1 seeds reached "
            "that boundary."
        ),
        (
            "B1 is raster-dominant: raster shuffle changes aggregate ADE by "
            f"{raster_shuffle['mean__delta_vs_original__all_top1_ADE_m']:.6f} m on "
            "average, whereas past-state shuffle changes it by only "
            f"{past_shuffle['mean__delta_vs_original__all_top1_ADE_m']:.6f} m."
        ),
        (
            "The response-active calibration finding is based on 15 windows from six "
            "rollouts and three init groups and is therefore a tail diagnostic, not a "
            "stable population estimate."
        ),
        (
            "Physical-baseline NLL is intentionally not contrasted with MultiPath NLL "
            "because their probabilistic models define different estimands."
        ),
    ]

    report = {
        "schema_version": "supervisor_finetune_feedback_audit_v2",
        "status": "pass",
        "supervisor_comment": (
            "The earlier 0.98%-to-100% top-probability/oracle-best-mode hit-rate "
            "claim required an implementation, split, evaluation and metric audit."
        ),
        "verdict": (
            "closed_for_the_frozen_in_distribution_claim_with_explicit_generalisation_"
            "and_tail_boundaries"
        ),
        "metric_policy": {
            "primary_comparison": "uncalibrated rollout-macro NLL/ADE/FDE",
            "independent_unit": "held-out ego initialisation",
            "paired_init_ids": list(range(46, 51)),
            "overlapping_windows_are_independent": False,
            "superseded_percentage_accuracy_is_current_evidence": False,
        },
        "frozen_test_population_contract": population_contract,
        "checks": checks,
        "frozen_test": {
            "summary_rows": summary_rows,
            "contrast_rows": contrast_rows,
            "paired_summary": paired_summary,
        },
        "response_active_tail": response_active,
        "physical_baseline_policy": (
            "ADE/FDE are paired and averaged at the held-out init-group level; no "
            "sample-micro/rollout-macro subtraction and no cross-model NLL subtraction."
        ),
        "superseded_accuracy_scan": percentage_scan,
        "limitations": limitations,
    }

    output.mkdir(parents=True, exist_ok=True)
    artifact_names = {
        "frozen_test_same_aggregation.csv": summary_rows,
        "frozen_test_same_aggregation_contrasts.csv": contrast_rows,
        "frozen_test_paired_by_init.csv": paired_rows,
        "frozen_test_paired_summary.csv": paired_summary,
        "physical_baselines_paired_by_init.csv": physical_pairs,
        "physical_baselines_same_aggregation.csv": physical_summary,
    }
    for name, rows in artifact_names.items():
        atomic_csv(output / name, rows)
    latex_artifacts = {
        "finetune_b0_b1_rollout_macro.tex": render_rollout_macro_latex(
            summary_rows, contrast_rows
        ),
        "finetune_b0_b1_paired_init_effects.tex": render_paired_init_latex(
            paired_rows, paired_summary
        ),
    }
    for name, value in latex_artifacts.items():
        atomic_text(output / name, value)
    atomic_json(output / "percentage_accuracy_scan.json", percentage_scan)
    atomic_json(output / "frozen_test_population_contract.json", population_contract)
    atomic_json(output / "finetune_audit.json", report)

    rollout_b0 = next(
        row
        for row in summary_rows
        if row["variant"] == "B0" and row["aggregation_level"] == "rollout_macro"
    )
    rollout_b1 = next(
        row
        for row in summary_rows
        if row["variant"] == "B1" and row["aggregation_level"] == "rollout_macro"
    )
    markdown = f"""# Supervisor feedback item 3: fine-tuning audit

**Status:** pass. The old report's 0.98%-to-100% number was the fraction of
prediction windows for which the top-probability mode matched the oracle-best
(minimum-error) mode. It was not a thresholded trajectory-accuracy endpoint.
That headline interpretation is withdrawn and is not evidence for trajectory
quality. It is replaced by a validation-frozen, rollout-disjoint NLL/ADE/FDE
evaluation.

## Frozen test at one aggregation level

At rollout-macro aggregation, B0 has NLL
{rollout_b0['trajectory_mixture_NLL_nats_per_step']:.6f}, ADE
{rollout_b0['top1_ADE_m']:.6f} m and FDE {rollout_b0['top1_FDE_m']:.6f} m.
B1 has NLL {rollout_b1['trajectory_mixture_NLL_nats_per_step']:.6f}, ADE
{rollout_b1['top1_ADE_m']:.6f} m and FDE {rollout_b1['top1_FDE_m']:.6f} m.
All three metrics favour B1 in each of 5/5 held-out init groups.
The smallest attainable two-sided exact sign-flip value with five groups is
0.0625. It is a sensitivity analysis under a symmetric paired-cluster-effect
assumption, not treatment-randomisation inference; overlapping windows are not
counted as independent evidence.

## Why the result is not “100% accuracy”

The old mode-ranking hit rate was fragile to the narrow split, concentration
of the oracle-best mode and overlapping-window aggregation. The corrected
endpoints are continuous displacement and probabilistic forecasting metrics,
not accuracy percentages. Their large aggregate gain is bounded to one Town05
distribution. Only {response_samples}/315 full-horizon test windows are
response-active, and the globally fitted B1 calibration worsens NLL in that
small tail despite improving aggregate NLL.

## Physical baselines

The rebuilt physical-baseline tables compare ADE/FDE at the common held-out
init-group aggregation. MultiPath mixture NLL is not subtracted from the
physical baselines' diagonal-Gaussian NLL because they are different
estimands.

## Frozen limitations

""" + "".join(f"- {item}\n" for item in limitations)
    atomic_text(output / "SUPERVISOR_COMMENT_3_AUDIT.md", markdown)

    generated = [
        *artifact_names,
        *latex_artifacts,
        "percentage_accuracy_scan.json",
        "frozen_test_population_contract.json",
        "finetune_audit.json",
        "SUPERVISOR_COMMENT_3_AUDIT.md",
    ]
    artifact_hashes = {name: sha256_file(output / name) for name in sorted(generated)}
    source_hashes = {
        relative_path(repo, path): sha256_file(path)
        for path in sorted(sources.values(), key=str)
    }
    script_path = Path(__file__).resolve()
    source_hashes[relative_path(repo, script_path)] = sha256_file(script_path)
    manifest = {
        "schema_version": "supervisor_finetune_feedback_manifest_v2",
        "status": "pass",
        "result_generation": "supervisor_feedback_v1",
        "analysis_requires_carla": False,
        "analysis_requires_training": False,
        "source_sha256": source_hashes,
        "artifacts": artifact_hashes,
        "checks_passed": len(checks),
        "checks_failed": 0,
        "independent_paired_init_groups": 5,
        "frozen_test_population_contract_status": population_contract["status"],
        "frozen_test_population_contract_sha256": sha256_file(
            output / "frozen_test_population_contract.json"
        ),
        "test_jsonl_sha256": population_contract["test_jsonl"]["sha256"],
        "anchors_sha256": population_contract["anchors"]["sha256"],
        "limitations": limitations,
    }
    manifest_path = output / "FINETUNE_AUDIT_MANIFEST.json"
    atomic_json(manifest_path, manifest)
    completion = {
        "schema_version": "supervisor_comment_3_complete_v2",
        "status": "pass",
        "stage": "supervisor_feedback_item_3_finetune_audit",
        "manifest": manifest_path.name,
        "manifest_sha256": sha256_file(manifest_path),
        "artifacts": artifact_hashes,
        "source_sha256": source_hashes,
        "check_count": len(checks),
        "failure_count": 0,
        "old_percentage_accuracy_hit_count": percentage_scan["hit_count"],
        "independent_paired_init_groups": 5,
        "overlapping_windows_treated_as_independent": False,
        "frozen_test_population_contract_status": population_contract["status"],
        "frozen_test_population_contract_sha256": sha256_file(
            output / "frozen_test_population_contract.json"
        ),
        "test_jsonl_sha256": population_contract["test_jsonl"]["sha256"],
        "anchors_sha256": population_contract["anchors"]["sha256"],
    }
    atomic_json(output / "SUPERVISOR_COMMENT_3_COMPLETE.json", completion)
    return completion


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    output = (args.output or repo / DEFAULT_OUTPUT).resolve()
    completion = build(repo, output)
    print(json.dumps(completion, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
