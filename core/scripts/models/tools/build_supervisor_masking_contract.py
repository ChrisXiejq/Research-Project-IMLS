#!/usr/bin/env python3
"""Build the immutable baseline and scientific contract for the masking reframe.

The builder is deliberately descriptive.  It never mutates the completed
``supervisor_bottleneck_v1`` release, and it never pools experimental
populations.  Its outputs provide the machine-readable inputs for the later
evidence audit and manuscript rewrite.
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
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit, urlunsplit


RELEASE_ROOT = "docs/paper/generated/supervisor_masking_v2"
PRIOR_MANIFEST = (
    "docs/paper/generated/supervisor_bottleneck_v1/"
    "SUBMISSION_RELEASE_MANIFEST.json"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def _source(root: Path, relative: str, locator: str = "/") -> dict[str, str]:
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": relative, "sha256": _sha256(path), "locator": locator}


def _run_git(root: Path, *args: str, check: bool = True, binary: bool = False):
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    if check and result.returncode != 0:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode()
        raise RuntimeError(f"git {' '.join(args)} failed in {root}: {stderr.strip()}")
    if binary:
        return result.stdout
    return result.stdout.strip()


def _sanitize_remote(url: str) -> str:
    """Strip embedded HTTP credentials while preserving ordinary SSH remotes."""

    if "://" not in url:
        return url
    split = urlsplit(url)
    if "@" not in split.netloc:
        return url
    host = split.netloc.rsplit("@", 1)[1]
    return urlunsplit((split.scheme, host, split.path, split.query, split.fragment))


def _worktree_inventory(root: Path) -> list[dict[str, Any]]:
    raw = _run_git(
        root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        binary=True,
    )
    tokens = raw.decode("utf-8", errors="surrogateescape").split("\0")
    records: list[dict[str, Any]] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        if not token:
            continue
        status = token[:2]
        path = token[3:]
        old_path = None
        if "R" in status or "C" in status:
            old_path = path
            if index >= len(tokens):
                raise ValueError(f"Malformed Git porcelain record: {token!r}")
            path = tokens[index]
            index += 1
        absolute = root / path
        records.append(
            {
                "status": status,
                "path": path,
                "old_path": old_path,
                "bytes": absolute.stat().st_size if absolute.is_file() else None,
                "sha256": _sha256(absolute) if absolute.is_file() else None,
            }
        )
    return records


def _repository_record(name: str, root: Path) -> dict[str, Any]:
    if not (root / ".git").exists():
        raise FileNotFoundError(f"Expected Git repository: {root}")
    upstream = _run_git(root, "rev-parse", "--abbrev-ref", "@{upstream}", check=False)
    ahead = behind = None
    if upstream:
        left, right = _run_git(
            root, "rev-list", "--left-right", "--count", f"HEAD...{upstream}"
        ).split()
        ahead, behind = int(left), int(right)
    remotes = {
        remote: _sanitize_remote(_run_git(root, "remote", "get-url", remote))
        for remote in _run_git(root, "remote").splitlines()
        if remote
    }
    dirty = _worktree_inventory(root)
    return {
        "name": name,
        "root_name": root.name,
        "head": _run_git(root, "rev-parse", "HEAD"),
        "head_tree": _run_git(root, "rev-parse", "HEAD^{tree}"),
        "branch": _run_git(root, "branch", "--show-current"),
        "upstream": upstream or None,
        "ahead": ahead,
        "behind": behind,
        "remotes": remotes,
        "worktree_dirty_count": len(dirty),
        "worktree_inventory": dirty,
    }


def _git_object_sha256(root: Path, revision: str, relative: str) -> str:
    content = _run_git(root, "show", f"{revision}:{relative}", binary=True)
    return hashlib.sha256(content).hexdigest()


def _prior_release_record(
    experiment_root: Path, dissertation_root: Path
) -> dict[str, Any]:
    manifest_path = experiment_root / PRIOR_MANIFEST
    manifest = _read_json(manifest_path)
    if manifest.get("status") != "pass":
        raise ValueError("Prior submission release manifest is not pass")

    # The experiment release commit is the commit that first materialised the
    # submission manifest.  The dissertation commit is frozen inside it.
    experiment_commit = _run_git(
        experiment_root, "log", "-1", "--format=%H", "--", PRIOR_MANIFEST
    )
    dissertation_commit = manifest["release_base_commits"]["dissertation"]
    repositories = {
        "experiment": (experiment_root, experiment_commit),
        "dissertation": (dissertation_root, dissertation_commit),
    }
    checks: list[dict[str, Any]] = []
    for role, (root, revision) in repositories.items():
        for artifact in manifest[f"{role}_artifacts"]:
            observed = _git_object_sha256(root, revision, artifact["path"])
            expected = artifact["sha256"]
            checks.append(
                {
                    "repository": role,
                    "commit": revision,
                    "path": artifact["path"],
                    "expected_sha256": expected,
                    "observed_sha256": observed,
                    "matches": observed == expected,
                }
            )
    if not checks or not all(item["matches"] for item in checks):
        failures = [item for item in checks if not item["matches"]]
        raise ValueError(f"Prior release object verification failed: {failures}")
    return {
        "manifest": _source(experiment_root, PRIOR_MANIFEST),
        "frozen_commits": {
            "experiment": experiment_commit,
            "dissertation": dissertation_commit,
        },
        "artifact_checks": checks,
        "all_artifacts_match": True,
        "mutation_boundary": (
            "supervisor_bottleneck_v1 is read only; hashes are verified from frozen "
            "Git objects rather than from a later manuscript worktree."
        ),
    }


def build_baseline_snapshot(
    experiment_root: Path, dissertation_root: Path
) -> dict[str, Any]:
    payload = {
        "schema_version": "supervisor_masking_immutable_baseline_v2",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repositories": [
            _repository_record("experiment", experiment_root),
            _repository_record("dissertation", dissertation_root),
        ],
        "prior_release": _prior_release_record(experiment_root, dissertation_root),
        "checks": {
            "two_repository_heads_recorded": True,
            "remotes_sanitized": True,
            "divergence_recorded": True,
            "worktree_inventory_recorded": True,
            "prior_release_git_objects_match_manifest": True,
        },
    }
    payload["status"] = "pass" if all(payload["checks"].values()) else "fail"
    return payload


def _terminology(root: Path) -> list[dict[str, str]]:
    rows = [
        {
            "term_id": "multipath_predictor",
            "canonical_term": "MultiPath",
            "definition": "A fixed-anchor multimodal trajectory predictor that emits mode probabilities and per-mode future Gaussian states.",
            "symbol": "p(Y|X)=sum_k pi_k p_k(Y|X)",
            "measurement_layer": "upstream_prediction",
            "code_or_evidence_locator": "core/scripts/models/training/deploy_multipath_model.py",
            "do_not_conflate_with": "a deterministic single-trajectory regressor",
        },
        {
            "term_id": "multimodal_smpc",
            "canonical_term": "multimodal SMPC",
            "definition": "A receding-horizon stochastic controller that consumes multimodal target predictions and applies chance-constraint tightening.",
            "symbol": "u_nom=pi_SMPC(x,Y_hat,delta)",
            "measurement_layer": "candidate_control",
            "code_or_evidence_locator": "core/scripts/carla/utils/mpc_utils.py",
            "do_not_conflate_with": "the post-solver rule-based supervisor",
        },
        {
            "term_id": "fixed_risk_allocation",
            "canonical_term": "fixed risk allocation",
            "definition": "A declared time-invariant risk/tightening policy used by the stochastic collision constraints.",
            "symbol": "delta_t=delta_fixed",
            "measurement_layer": "risk_constraint",
            "code_or_evidence_locator": "core/scripts/carla/policies/smpc_agent.py",
            "do_not_conflate_with": "constant physical clearance",
        },
        {
            "term_id": "adaptive_risk_allocation",
            "canonical_term": "adaptive risk allocation",
            "definition": "An interaction-state-dependent allocation that changes per-mode target probability or tightening within a rollout.",
            "symbol": "delta_t=rho(x_t,Y_hat_t)",
            "measurement_layer": "risk_constraint",
            "code_or_evidence_locator": "core/scripts/carla/policies/smpc_agent.py",
            "do_not_conflate_with": "the supervisor brake rule",
        },
        {
            "term_id": "controller_candidate_command",
            "canonical_term": "candidate command",
            "definition": "The nominal first SMPC command before post-solver supervisor arbitration.",
            "symbol": "u_nom",
            "measurement_layer": "candidate_control",
            "code_or_evidence_locator": "core/scripts/carla/policies/supervisor_action_filter.py",
            "do_not_conflate_with": "the rule-proposed supervisor candidate",
        },
        {
            "term_id": "supervisor_candidate_command",
            "canonical_term": "supervisor candidate command",
            "definition": "A rule-proposed replacement command computed whether or not behavioural authority permits application.",
            "symbol": "u_sup",
            "measurement_layer": "supervisor_intervention",
            "code_or_evidence_locator": "core/scripts/carla/policies/supervisor_action_filter.py",
            "do_not_conflate_with": "the nominal solver command or executed command",
        },
        {
            "term_id": "executed_command",
            "canonical_term": "executed command",
            "definition": "The command on the factual vehicle-control path after authority arbitration.",
            "symbol": "u_exec",
            "measurement_layer": "executed_control",
            "code_or_evidence_locator": "core/scripts/carla/policies/supervisor_action_filter.py",
            "do_not_conflate_with": "an unactuated shadow command",
        },
        {
            "term_id": "supervisor_authority",
            "canonical_term": "supervisor authority",
            "definition": "The complete seven-channel behavioural bundle controlling reference shaping, linearisation/cost changes, bypass, post-solver replacement and recovery state.",
            "symbol": "A in {on,off}",
            "measurement_layer": "cross_layer_intervention",
            "code_or_evidence_locator": "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results/sf4_supervisor_behavioural_authority_run_contract.json",
            "do_not_conflate_with": "one isolated safety-filter rule",
        },
        {
            "term_id": "attenuation",
            "canonical_term": "attenuation",
            "definition": "A quantified reduction in an aligned policy contrast between two adjacent measurement layers.",
            "symbol": "rho=d_after/(d_before+epsilon)",
            "measurement_layer": "aligned_cross_layer_estimand",
            "code_or_evidence_locator": "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/attenuation_claim_audit.json",
            "do_not_conflate_with": "causal supervisor masking without an identifying contrast",
        },
        {
            "term_id": "compression",
            "canonical_term": "compression",
            "definition": "A descriptive contraction of policy separation downstream; by itself it does not identify which component caused the contraction.",
            "symbol": "d_downstream<d_upstream",
            "measurement_layer": "descriptive_cross_layer",
            "code_or_evidence_locator": "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/attenuation_claim_audit.json",
            "do_not_conflate_with": "causally identified masking",
        },
        {
            "term_id": "not_transferred",
            "canonical_term": "not transferred",
            "definition": "An upstream difference whose declared downstream outcome contrast is not detected at the available precision and population.",
            "symbol": "Delta_upstream!=0; Delta_outcome not detected",
            "measurement_layer": "cross_population_verdict",
            "code_or_evidence_locator": "docs/paper/generated/supervisor_bottleneck_v1/scientific_contract/claim_evidence_boundary.json",
            "do_not_conflate_with": "proof of equivalence or uselessness",
        },
        {
            "term_id": "masking",
            "canonical_term": "masking",
            "definition": "A causal supervisor effect that reduces an upstream-policy distinction, licensed only by aligned same-state mappings or a non-saturated policy-by-authority interaction.",
            "symbol": "Delta_policy x authority",
            "measurement_layer": "identified_intervention_effect",
            "code_or_evidence_locator": "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/attenuation_claim_audit.json",
            "do_not_conflate_with": "similar final trajectories under shared supervision",
        },
    ]
    for row in rows:
        if not (root / row["code_or_evidence_locator"]).is_file():
            raise FileNotFoundError(root / row["code_or_evidence_locator"])
    if len({row["term_id"] for row in rows}) != len(rows):
        raise ValueError("Terminology identifiers must be unique")
    return rows


def _identification_ladder() -> list[dict[str, Any]]:
    return [
        {
            "level": 1,
            "verdict": "retained_upstream_difference",
            "required_evidence": ["provenance-aligned upstream policy contrast"],
            "licensed_claim": "The upstream policies remain distinguishable at the measured layer.",
            "does_not_license": "Any claim about candidate commands, executed controls or masking.",
        },
        {
            "level": 2,
            "verdict": "attenuated_candidate_difference",
            "required_evidence": [
                "same-state upstream evaluations",
                "aligned candidate commands",
                "non-degenerate pre-layer contrast",
            ],
            "licensed_claim": "The upstream distinction contracts by the SMPC candidate-command layer.",
            "does_not_license": "Attribution of that contraction to supervisor authority.",
        },
        {
            "level": 3,
            "verdict": "compressed_executed_difference",
            "required_evidence": [
                "aligned candidate and executed commands",
                "declared command-distance metric",
            ],
            "licensed_claim": "Executed command separation is smaller than candidate separation.",
            "does_not_license": "Long-horizon counterfactual trajectory masking.",
        },
        {
            "level": 4,
            "verdict": "no_detected_physical_transfer",
            "required_evidence": [
                "declared upstream difference",
                "matched physical outcome contrast with uncertainty",
            ],
            "licensed_claim": "No uniform physical advantage was detected in the tested population.",
            "does_not_license": "Equivalence, uselessness, or a unique masking mechanism.",
        },
        {
            "level": 5,
            "verdict": "consistent_with_masking",
            "required_evidence": [
                "upstream difference",
                "downstream compression or non-transfer",
                "documented active supervisor intervention",
                "explicit unresolved rival mechanisms",
            ],
            "licensed_claim": "The observed chain is consistent with supervisor masking.",
            "does_not_license": "A causal or selective masking conclusion.",
        },
        {
            "level": 6,
            "verdict": "causally_identified_masking",
            "required_evidence_any_of": [
                [
                    "aligned same-state candidate-to-executed mappings",
                    "enabled and monitor-only complete supervisor mappings",
                    "paired attenuation uncertainty",
                ],
                [
                    "joint upstream-policy-by-authority factorial",
                    "comparable non-saturated units",
                    "policy-by-authority interaction uncertainty",
                ],
            ],
            "licensed_claim": "Supervisor authority causally attenuates the immediate command distinction under the declared state distribution.",
            "does_not_license": "Universal safety, isolated-rule attribution, or counterfactual trajectory effects beyond the estimand.",
        },
    ]


def _hypotheses(root: Path) -> dict[str, Any]:
    sf4 = (
        "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/"
        "results/analysis/sf4_inference.json"
    )
    cia = "docs/paper/generated/capacity_history_v3/final/table_three_axis_contrasts.csv"
    v3 = "docs/paper/generated/capacity_history_v3/final/table_model_by_risk_contrasts.csv"
    r3 = (
        "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/"
        "synthesis/table_r3_h4_dominance.csv"
    )
    return {
        "H1": {
            "name": "Nominal physical yielding under complete supervisor authority",
            "treatment": "complete seven-channel supervisor authority on versus monitor-only off",
            "independent_unit": "SF4 ego_init_id cluster",
            "upstream_outcome": "not_applicable_authority_is_the_downstream_treatment",
            "candidate_control_outcome": "supervisor request, bypass/fallback path and candidate-minus-nominal command magnitude",
            "executed_outcome": "completion, yield-rule compliance, collisions, minimum footprint separation and executed-command replacement",
            "falsification_rule": "Refute the tested-sample effectiveness claim if authority-on rollouts do not consistently yield and complete, or exhibit adverse collisions/yield-order failures incompatible with the claim.",
            "population_boundary": "Town05 right-hand-traffic ego-left-turn versus opposing-straight target; 10 paired SF4 initialisation groups and the complete channel bundle only.",
            "claimable_conclusion": "Complete authority achieved nominal yielding and completion in all tested authority-on SF4 rollouts if canonical reconciliation passes.",
            "current_verdict_vocabulary": ["supported_in_tested_sample", "mixed", "refuted"],
            "prohibited_overclaims": [
                "formal safety guarantee",
                "general or real-road safety",
                "attribution to one individual rule",
            ],
            "sources": [_source(root, sf4, "/")],
        },
        "H2": {
            "name": "Predictor advantage transfer through the supervised stack",
            "treatment": "matched predictor contrasts, including B1 versus validation-frozen P* where deployed",
            "independent_unit": "offline ego initialisation group for CIA; V3 paired ego_init_id for deployed transfer",
            "upstream_outcome": "rollout-macro mixture NLL, top-1 ADE/FDE and in-loop prediction error",
            "candidate_control_outcome": "aligned nominal SMPC command separation when available",
            "executed_outcome": "supervisor intervention, executed command and completion/separation outcomes",
            "falsification_rule": "Refute supervisor-induced masking if predictor distinctions transfer without additional authority-linked attenuation; treat absent aligned or non-saturated authority contrasts as unidentified rather than confirmation.",
            "population_boundary": "CIA and V3 are separate populations; only actually deployed matched policies license physical-transfer statements.",
            "claimable_conclusion": "Capacity, Information and Architecture change bounded prediction, while current evidence tests whether rather than presumes supervisor-specific masking.",
            "current_verdict_vocabulary": [
                "retained_upstream_difference",
                "attenuated_candidate_difference",
                "compressed_executed_difference",
                "no_detected_physical_transfer",
                "consistent_with_masking",
                "causally_identified_masking",
            ],
            "subquestions": {
                "Capacity": "small, medium and large Transformer tiers at fixed full history",
                "Information": "0.0, 0.4 and 1.0 second histories within matched families",
                "Architecture": "matched MLP versus Transformer direct gap and history-gain interaction",
            },
            "prohibited_overclaims": [
                "all predictor improvements are masked",
                "attention is generally ineffective",
                "non-significance proves equality",
            ],
            "sources": [
                _source(root, cia, "/"),
                _source(root, v3, "/P_star_minus_B1 contrasts"),
            ],
        },
        "H3": {
            "name": "Risk-allocation distinction transfer through the supervised stack",
            "treatment": "adaptive allocation versus every declared fixed-risk frontier comparator",
            "independent_unit": "R3 ego_init_cluster; V3/SF4 ego_init_id, reported separately",
            "upstream_outcome": "per-mode allocation, target probability, tightening and constraint activity where logged",
            "candidate_control_outcome": "aligned nominal SMPC command separation and solver/fallback status",
            "executed_outcome": "supervisor intervention, executed command, completion and minimum footprint separation",
            "falsification_rule": "Refute supervisor-induced masking if risk-policy candidate distinctions pass through authority unchanged; if constraint or nominal-command differences are already absent, attribute no unique supervisor mechanism.",
            "population_boundary": "R3 full fixed frontier, V3 selected-model cells, SF4 authority cells and licensed legacy timing evidence remain unpooled.",
            "claimable_conclusion": "Adaptive risk is evaluated across the full fixed frontier and any physical similarity is decomposed before masking language is used.",
            "current_verdict_vocabulary": [
                "retained_constraint_difference",
                "controller_compression",
                "compressed_executed_difference",
                "no_detected_physical_transfer",
                "consistent_with_masking",
                "causally_identified_masking",
            ],
            "prohibited_overclaims": [
                "adaptive risk is universally superior",
                "the supervisor alone causes all risk-policy similarity",
                "non-significance proves equality",
            ],
            "sources": [
                _source(root, r3, "/"),
                _source(root, v3, "/model_by_risk contrasts"),
                _source(root, sf4, "/risk-by-authority interaction"),
            ],
        },
    }


def _claim_matrix(root: Path) -> list[dict[str, Any]]:
    def sources(*items: tuple[str, str]) -> list[dict[str, str]]:
        return [_source(root, path, locator) for path, locator in items]

    sf4_root = "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results"
    return [
        {
            "claim_id": "H1_PHYSICAL_EFFECTIVENESS",
            "hypothesis": "H1",
            "intended_sentence": "Complete supervisor authority achieved nominal yielding and completion in all tested authority-on SF4 rollouts, whereas the monitor-only arm was failure-saturated.",
            "identification_level": "tested-sample_authority_effect",
            "population_ids": ["SF4_authority"],
            "source_locators": sources(
                (f"{sf4_root}/analysis/sf4_inference.json", "/outcomes"),
                (f"{sf4_root}/analysis/sf4_rollout_outcomes.csv", "authority-on/off rows"),
            ),
            "evidence_gap": None,
            "boundary": "Observed nominal outcome in one geometry; not a formal or general safety guarantee.",
        },
        {
            "claim_id": "H1_INTERVENTION_MECHANISM",
            "hypothesis": "H1",
            "intended_sentence": "The authority effect is accompanied by requests, actual command replacement and distinct bypass/solver paths rather than inferred from trajectories alone.",
            "identification_level": "mechanism_accounting",
            "population_ids": ["SF4_authority"],
            "source_locators": sources(
                (
                    "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/TELEMETRY_AUDIT_COMPLETE.json",
                    "/",
                ),
                (
                    "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/solver_path_reconciliation.json",
                    "/",
                ),
            ),
            "evidence_gap": None,
            "boundary": "Seven channels were toggled together; channel-specific effects are not identified.",
        },
        {
            "claim_id": "H2_CAPACITY",
            "hypothesis": "H2.Capacity",
            "intended_sentence": "Increasing Transformer capacity does not produce a coherent monotonic held-out prediction gain under the frozen V3 protocol.",
            "identification_level": "retained_upstream_difference",
            "population_ids": ["V3_CIA_offline"],
            "source_locators": sources(
                (
                    "docs/paper/generated/capacity_history_v3/final/table_three_axis_contrasts.csv",
                    "H1_capacity rows",
                ),
            ),
            "evidence_gap": None,
            "boundary": "No capacity tier was separately crossed with supervisor authority.",
        },
        {
            "claim_id": "H2_INFORMATION",
            "hypothesis": "H2.Information",
            "intended_sentence": "Short interaction history provides a small, rapidly saturating upstream prediction gain in both matched encoder families.",
            "identification_level": "retained_upstream_difference",
            "population_ids": ["V3_CIA_offline"],
            "source_locators": sources(
                (
                    "docs/paper/generated/capacity_history_v3/final/table_three_axis_contrasts.csv",
                    "H2_information rows",
                ),
                (
                    "docs/paper/generated/capacity_history_v3/final/table_offline_model_cells.csv",
                    "history_horizon_s cells",
                ),
            ),
            "evidence_gap": None,
            "boundary": "Input value does not establish attention-specific understanding.",
        },
        {
            "claim_id": "H2_ARCHITECTURE",
            "hypothesis": "H2.Architecture",
            "intended_sentence": "The direct MLP--Transformer gap is distinct from the history-gain interaction, which does not support attention-specific extraction.",
            "identification_level": "retained_upstream_difference",
            "population_ids": ["V3_CIA_offline"],
            "source_locators": sources(
                (
                    "docs/paper/generated/capacity_history_v3/final/table_three_axis_contrasts.csv",
                    "architecture_direct and H3_attention rows",
                ),
            ),
            "evidence_gap": None,
            "boundary": "Bounded to tested architectures, capacity matching and optimisation budget.",
        },
        {
            "claim_id": "H2_PHYSICAL_TRANSFER",
            "hypothesis": "H2",
            "intended_sentence": "The selected predictor remains distinguishable in-loop but does not show a uniform co-primary physical advantage under the shared supervised stack.",
            "identification_level": "no_detected_physical_transfer",
            "population_ids": ["V3_selected_model_closed_loop"],
            "source_locators": sources(
                (
                    "docs/paper/generated/capacity_history_v3/final/table_model_by_risk_contrasts.csv",
                    "P_star_minus_B1 rows",
                ),
                (
                    "docs/paper/generated/capacity_history_v3/final/table_closed_loop_cells.csv",
                    "deployed predictor cells",
                ),
            ),
            "evidence_gap": None,
            "boundary": "Shared-supervisor physical non-transfer does not identify supervisor-specific masking.",
        },
        {
            "claim_id": "H2_SUPERVISOR_MASKING",
            "hypothesis": "H2",
            "intended_sentence": "Whether the supervisor causally attenuates predictor-policy command separation remains subject to the identification gate.",
            "identification_level": "not_transferred_or_not_identified",
            "population_ids": ["V3_selected_model_closed_loop", "SF4_authority"],
            "source_locators": [],
            "evidence_gap": {
                "missing_estimand": "aligned same-state B1/P* candidate-to-executed command contrast under enabled and monitor-only complete supervisor mappings",
                "reason": "V3 shares authority-on operation and SF4 varies authority only for B1; the SF4 off arm is floor-saturated.",
            },
            "boundary": "Use consistent_with_masking at most until the gate licenses a stronger term.",
        },
        {
            "claim_id": "H3_RISK_FRONTIER",
            "hypothesis": "H3",
            "intended_sentence": "Adaptive risk is context-dependent and does not uniformly dominate the full fixed-risk frontier.",
            "identification_level": "retained_upstream_or_policy_difference",
            "population_ids": ["R3_predictor_risk"],
            "source_locators": sources(
                (
                    "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/synthesis/table_r3_h4_dominance.csv",
                    "all declared fixed comparators",
                ),
            ),
            "evidence_gap": None,
            "boundary": "All fixed comparators and target contexts must remain visible.",
        },
        {
            "claim_id": "H3_CROSS_LAYER_TRANSFER",
            "hypothesis": "H3",
            "intended_sentence": "The risk-to-action audit must locate any contraction at the constraint-to-SMPC layer before assigning additional attenuation to rule-level authority.",
            "identification_level": "pending_constraint_to_candidate_audit",
            "population_ids": ["R3_predictor_risk", "legacy_timing_shift"],
            "source_locators": [],
            "evidence_gap": {
                "missing_estimand": "provenance-bound risk/tightening-to-nominal-command contrast across declared fixed/adaptive policies",
                "reason": "The compact local release contains outcome and solver summaries but the server telemetry inventory is still pending.",
            },
            "boundary": "Historical timing and R3 results are juxtaposed, never pooled.",
        },
        {
            "claim_id": "H3_SUPERVISOR_MASKING",
            "hypothesis": "H3",
            "intended_sentence": "Whether the supervisor adds causal attenuation beyond SMPC controller compression remains subject to the identification gate.",
            "identification_level": "consistent_with_masking",
            "population_ids": ["R3_predictor_risk", "SF4_authority"],
            "source_locators": [],
            "evidence_gap": {
                "missing_estimand": "same-state fixed/adaptive candidate-to-executed contrast or a non-saturated risk-by-authority interaction",
                "reason": "SF4 authority-off outcomes are floor-saturated and factual rollouts do not align alternative risk commands at identical states.",
            },
            "boundary": "Do not assign all physical similarity uniquely to the supervisor.",
        },
    ]


def _population_registry(root: Path) -> list[dict[str, Any]]:
    f1_manifest = (
        "docs/paper/generated/supervisor_feedback_v1/03_finetune_audit/"
        "FINETUNE_AUDIT_MANIFEST.json"
    )
    v3_train = "docs/paper/generated/capacity_history_v3/results/postprocess/training_audit.json"
    v3_complete = "docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_COMPLETE.json"
    v3_manifest = "docs/paper/generated/capacity_history_v3/results/closed_loop/CLOSED_LOOP_MANIFEST.json"
    r3_root = (
        "docs/paper/generated/distinction_v1/08_corrected_closed_loop/r3_final/"
        "server_runs/r3_corrected_formal_v3"
    )
    sf4_root = "docs/paper/generated/distinction_sf4_supervisor_authority_ablation/results"
    timing_complete = "docs/paper/generated/day12/timing_synthesis/DAY12_TIMING_SYNTHESIS_COMPLETE.json"
    threshold_registry = (
        "docs/paper/generated/supervisor_bottleneck_v1/telemetry_audit/"
        "timing_threshold_evidence_registry.json"
    )
    legacy = (
        "docs/paper/generated/supervisor_bottleneck_v1/legacy_implicit_filter_snapshot/"
        "LEGACY_IMPLICIT_FILTER_SNAPSHOT.json"
    )

    v3_closed_manifest = _read_json(root / v3_manifest)
    r3_contract = _read_json(root / f"{r3_root}/r3_run_contract.json")
    sf4_contract = _read_json(
        root / f"{sf4_root}/sf4_supervisor_behavioural_authority_run_contract.json"
    )
    threshold = _read_json(root / threshold_registry)
    threshold_record = next(
        row for row in threshold["records"] if row["evidence_id"] == "rule_parameter_threshold_sweep"
    )
    records = [
        {
            "population_id": "foundation_prediction",
            "role": "supporting MultiPath task-adaptation evidence",
            "availability": "complete",
            "population": "Town05 give-way held-out prediction groups 46--50",
            "independent_unit": "ego initialisation group",
            "independent_groups": [46, 47, 48, 49, 50],
            "denominator": {"independent_groups": 5, "rollouts": 20, "overlapping_windows": 315},
            "completion_marker": _source(root, f1_manifest, "/status=pass"),
            "pooling_permission": "standalone_only",
        },
        {
            "population_id": "V3_CIA_offline",
            "role": "Capacity--Information--Architecture offline decomposition",
            "availability": "complete",
            "population": "Town05 prediction groups 1--45 with frozen split roles",
            "independent_unit": "ego initialisation group; training seed is repeated model fitting, not a new trajectory population",
            "independent_groups": {
                "fit": list(range(1, 36)),
                "selection_calibration": list(range(36, 41)),
                "retrospective_heldout": list(range(41, 46)),
            },
            "denominator": {"model_cells": 9, "seeds_per_cell": 3, "valid_runs": 27},
            "completion_marker": _source(root, v3_train, "/status=pass; valid_runs=27"),
            "pooling_permission": "standalone_only",
        },
        {
            "population_id": "V3_selected_model_closed_loop",
            "role": "selected predictor physical-transfer experiment",
            "availability": "complete",
            "population": "Town05 V3 ego initialisations 81--90",
            "independent_unit": "ego_init_id",
            "independent_groups": v3_closed_manifest["ego_init_ids"],
            "denominator": {"independent_groups": 10, "cells": 8, "rollouts": 80},
            "completion_marker": _source(root, v3_complete, "/status=pass; observed_rollouts=80"),
            "pooling_permission": "standalone_only",
        },
        {
            "population_id": "R3_predictor_risk",
            "role": "full fixed-risk frontier and adaptive-risk context experiment",
            "availability": "complete",
            "population": "Town05 corrected R3 ego initialisations 101--105",
            "independent_unit": r3_contract.get("analysis_unit", "ego_init_cluster"),
            "independent_groups": r3_contract["ego_init_ids"],
            "denominator": {"independent_groups": 5, "cells": len(r3_contract["cells"]), "rollouts": 80},
            "completion_marker": _source(root, f"{r3_root}/R3_COMPLETE.json", "/status=pass; observed_rollouts=80"),
            "pooling_permission": "standalone_only",
        },
        {
            "population_id": "SF4_authority",
            "role": "complete supervisor-authority mechanism ablation",
            "availability": "complete",
            "population": "Town05 SF4 ego initialisations 106--115",
            "independent_unit": sf4_contract["independent_unit"],
            "independent_groups": sf4_contract["ego_init_ids"],
            "denominator": {"independent_groups": 10, "cells": len(sf4_contract["cells"]), "rollouts": 80},
            "completion_marker": _source(root, f"{sf4_root}/SF4_COMPLETE.json", "/status=pass; observed_rollouts=80"),
            "pooling_permission": "standalone_only",
        },
        {
            "population_id": "legacy_timing_shift",
            "role": "secondary target-arrival timing sensitivity",
            "availability": "complete",
            "population": "Town05 ego initialisations 46--50 across nominal and +/-3 m target offsets",
            "independent_unit": "ego_init_id within paired predictor/risk/style/offset condition",
            "independent_groups": [46, 47, 48, 49, 50],
            "denominator": {"independent_groups": 5, "cells": 24, "rollouts": 120},
            "completion_marker": _source(root, timing_complete, "/status=pass; rollouts=120"),
            "pooling_permission": "must_not_pool_with_foundation_V3_R3_or_SF4",
        },
        {
            "population_id": "supervisor_threshold_sweep",
            "role": "requested rule-parameter threshold sensitivity",
            "availability": threshold_record["availability"],
            "population": None,
            "independent_unit": None,
            "independent_groups": None,
            "denominator": {"status": "not_available", "rollouts": None},
            "completion_marker": None,
            "evidence_gap": threshold_record["boundary"],
            "source_registry": _source(root, threshold_registry, "/records/rule_parameter_threshold_sweep"),
            "pooling_permission": "not_applicable",
        },
        {
            "population_id": "legacy_implicit_filter_smoke",
            "role": "excluded exploratory controller engineering provenance",
            "availability": "complete_but_excluded",
            "population": "one legacy implicit-SMPC smoke rollout",
            "independent_unit": "single engineering rollout; no population inference",
            "independent_groups": ["smoke_hardtube_progressref_h4_10hz_20260825_0242"],
            "denominator": {"engineering_rollouts": 1},
            "completion_marker": _source(root, legacy, "/local_snapshot_status=complete"),
            "pooling_permission": "excluded_from_headline_evidence",
        },
    ]
    for record in records:
        signature = {
            "population_id": record["population_id"],
            "population": record["population"],
            "independent_unit": record["independent_unit"],
            "independent_groups": record["independent_groups"],
            "denominator": record["denominator"],
        }
        record["population_signature"] = _stable_sha(signature)
    if len({row["population_id"] for row in records}) != len(records):
        raise ValueError("Population identifiers are not unique")
    if len({row["population_signature"] for row in records}) != len(records):
        raise ValueError("Population signatures are not unique")
    return records


def _safe_claim_language(contract: dict[str, Any]) -> None:
    texts = [contract["paper_argument"]]
    for item in contract["hypotheses"].values():
        texts.append(item["claimable_conclusion"])
    joined = " ".join(texts).lower()
    prohibited = (
        "guarantees safety",
        "guarantees physical safety",
        "proves safety",
        "universally safe",
        "real-road safety is ensured",
        "all predictor improvements are masked",
        "all risk-allocation improvements are masked",
        "causally masked by the supervisor",
    )
    matches = [phrase for phrase in prohibited if phrase in joined]
    if matches:
        raise ValueError(f"Unsafe or unidentified headline language: {matches}")


def validate_contract(
    contract: dict[str, Any],
    terms: list[dict[str, str]],
    ladder: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    populations: list[dict[str, Any]],
) -> dict[str, bool]:
    required_hypothesis_fields = {
        "treatment",
        "independent_unit",
        "upstream_outcome",
        "candidate_control_outcome",
        "executed_outcome",
        "falsification_rule",
        "population_boundary",
        "claimable_conclusion",
        "current_verdict_vocabulary",
        "prohibited_overclaims",
        "sources",
    }
    _safe_claim_language(contract)
    checks = {
        "exactly_H1_H2_H3": set(contract["hypotheses"]) == {"H1", "H2", "H3"},
        "hypothesis_fields_complete": all(
            required_hypothesis_fields.issubset(item)
            for item in contract["hypotheses"].values()
        ),
        "required_terminology_present": {
            "MultiPath",
            "multimodal SMPC",
            "fixed risk allocation",
            "adaptive risk allocation",
            "candidate command",
            "executed command",
            "supervisor authority",
            "attenuation",
            "compression",
            "masking",
        }.issubset({row["canonical_term"] for row in terms}),
        "terms_map_one_concept": len({row["term_id"] for row in terms}) == len(terms)
        and all(row["code_or_evidence_locator"] for row in terms),
        "identification_ladder_ordered": [row["level"] for row in ladder]
        == list(range(1, len(ladder) + 1)),
        "causal_masking_requires_identification": ladder[-1]["verdict"]
        == "causally_identified_masking"
        and bool(ladder[-1].get("required_evidence_any_of")),
        "every_claim_located_or_gap": all(
            bool(row["source_locators"]) ^ bool(row["evidence_gap"]) for row in claims
        ),
        "H2_three_subdirections_present": {
            "H2_CAPACITY",
            "H2_INFORMATION",
            "H2_ARCHITECTURE",
        }.issubset({row["claim_id"] for row in claims}),
        "population_ids_unique": len({row["population_id"] for row in populations})
        == len(populations),
        "population_signatures_unique": len(
            {row["population_signature"] for row in populations}
        )
        == len(populations),
        "denominators_explicit": all("denominator" in row for row in populations),
        "completion_state_explicit": all(
            "completion_marker" in row for row in populations
        ),
        "threshold_absence_not_mislabelled": any(
            row["population_id"] == "supervisor_threshold_sweep"
            and row["availability"] == "not_present_in_canonical_generated_evidence"
            and row["completion_marker"] is None
            for row in populations
        ),
        "legacy_smoke_excluded": any(
            row["population_id"] == "legacy_implicit_filter_smoke"
            and row["pooling_permission"] == "excluded_from_headline_evidence"
            for row in populations
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ValueError(f"Supervisor masking contract validation failed: {failures}")
    return checks


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_csv(
    path: Path, rows: Iterable[dict[str, Any]], fields: list[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: json.dumps(row.get(field), sort_keys=True)
                    if isinstance(row.get(field), (dict, list))
                    else row.get(field)
                    for field in fields
                }
            )


def build_contract(
    root: Path, dissertation_root: Path, output_dir: Path
) -> dict[str, Any]:
    root = root.resolve()
    dissertation_root = dissertation_root.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    baseline = build_baseline_snapshot(root, dissertation_root)
    terms = _terminology(root)
    ladder = _identification_ladder()
    hypotheses = _hypotheses(root)
    claims = _claim_matrix(root)
    populations = _population_registry(root)
    contract = {
        "schema_version": "supervisor_masking_scientific_contract_v2",
        "status": "pass",
        "paper_argument": (
            "In the tested Town05 right-hand-traffic left-turn give-way task, complete "
            "rule-based supervisor authority achieved nominal physical yielding, while "
            "predictor and risk-allocation distinctions did not uniformly transfer to "
            "executed behaviour; causal masking is reserved for aligned or non-saturated "
            "intervention contrasts that identify the supervisor mechanism."
        ),
        "scenario": {
            "map": "Town05",
            "traffic_side": "right-hand traffic",
            "ego_manoeuvre": "left turn across opposing traffic",
            "target_manoeuvre": "straight priority movement",
            "behavioural_sequence": [
                "continue before target conflict",
                "decelerate and yield outside the conflict region",
                "resume after target clearance and complete the route",
            ],
        },
        "hypotheses": hypotheses,
        "identification_ladder_verdicts": [row["verdict"] for row in ladder],
        "population_ids": [row["population_id"] for row in populations],
        "global_boundaries": [
            "Nominal outcomes in the tested sample are not a formal or real-road safety guarantee.",
            "Seven supervisor channels are toggled together, so individual-rule effects are not isolated.",
            "SF4 authority-off failure saturation prevents a clean no-masking or selective-masking conclusion.",
            "Foundation, V3, R3, SF4, timing-shift, threshold-gap and legacy-smoke records are never pooled.",
            "Similar trajectories do not by themselves identify masking rather than controller insensitivity, inactive constraints, fallback, target response or limited power.",
        ],
    }
    checks = validate_contract(contract, terms, ladder, claims, populations)

    products: dict[str, dict[str, Any]] = {
        "immutable_baseline.json": baseline,
        "terminology_ledger.json": {
            "schema_version": "supervisor_masking_terminology_ledger_v2",
            "status": "pass",
            "terms": terms,
        },
        "identification_ladder.json": {
            "schema_version": "supervisor_masking_identification_ladder_v2",
            "status": "pass",
            "levels": ladder,
        },
        "hypothesis_registry.json": {
            "schema_version": "supervisor_masking_hypothesis_registry_v2",
            "status": "pass",
            "paper_argument": contract["paper_argument"],
            "hypotheses": hypotheses,
        },
        "claim_evidence_matrix.json": {
            "schema_version": "supervisor_masking_claim_evidence_matrix_v2",
            "status": "pass",
            "claims": claims,
        },
        "population_registry.json": {
            "schema_version": "supervisor_masking_population_registry_v2",
            "status": "pass",
            "no_cross_population_pooling": True,
            "populations": populations,
        },
        "scientific_contract.json": contract,
    }
    paths: list[Path] = []
    for name, payload in products.items():
        path = output_dir / name
        _write_json(path, payload)
        paths.append(path)

    terms_csv = output_dir / "terminology_ledger.csv"
    _write_csv(
        terms_csv,
        (
            {"schema_version": "supervisor_masking_terminology_ledger_v2", **row}
            for row in terms
        ),
        [
            "schema_version",
            "term_id",
            "canonical_term",
            "definition",
            "symbol",
            "measurement_layer",
            "code_or_evidence_locator",
            "do_not_conflate_with",
        ],
    )
    paths.append(terms_csv)

    claims_csv = output_dir / "claim_evidence_matrix.csv"
    _write_csv(
        claims_csv,
        (
            {"schema_version": "supervisor_masking_claim_evidence_matrix_v2", **row}
            for row in claims
        ),
        [
            "schema_version",
            "claim_id",
            "hypothesis",
            "intended_sentence",
            "identification_level",
            "population_ids",
            "source_locators",
            "evidence_gap",
            "boundary",
        ],
    )
    paths.append(claims_csv)

    populations_csv = output_dir / "population_registry.csv"
    _write_csv(
        populations_csv,
        (
            {"schema_version": "supervisor_masking_population_registry_v2", **row}
            for row in populations
        ),
        [
            "schema_version",
            "population_id",
            "role",
            "availability",
            "population",
            "independent_unit",
            "independent_groups",
            "denominator",
            "completion_marker",
            "pooling_permission",
            "population_signature",
        ],
    )
    paths.append(populations_csv)

    complete = {
        "schema_version": "supervisor_masking_contract_complete_v2",
        "status": "pass",
        "checks": checks,
        "baseline_status": baseline["status"],
        "hypotheses": sorted(hypotheses),
        "terminology_entries": len(terms),
        "identification_levels": len(ladder),
        "claims": len(claims),
        "populations": len(populations),
        "products": {path.name: _sha256(path) for path in paths},
        "prior_release_immutable": True,
        "no_cross_population_pooling": True,
    }
    _write_json(output_dir / "SUPERVISOR_MASKING_CONTRACT_COMPLETE.json", complete)
    return complete


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    root = Path(__file__).resolve().parents[4]
    parser.add_argument("--root", type=Path, default=root)
    parser.add_argument(
        "--dissertation-root", type=Path, default=root.parent / "Jiaqi-Xie-Dissertation"
    )
    parser.add_argument("--output-dir", type=Path, default=root / RELEASE_ROOT / "contract")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = build_contract(args.root, args.dissertation_root, args.output_dir)
    print(
        json.dumps(
            {
                "status": result["status"],
                "hypotheses": result["hypotheses"],
                "claims": result["claims"],
                "populations": result["populations"],
                "output_dir": str(args.output_dir),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
