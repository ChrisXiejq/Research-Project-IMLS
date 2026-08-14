"""Pure helpers for the complete supervisor behavioural-authority boundary.

The SF4 treatment is owned by the SMPC agent and covers every behavioural
channel: reference shaping, reference linearization, heading cost, post-solver
command, release/recovery and next-step control state.  This module supplies
the locally testable authority-mode validator, factual/shadow isolation audit,
and the post-solver arbitration helper used for one channel of that treatment.
It deliberately contains no CARLA or model code.
"""

from __future__ import annotations

import math
import hashlib
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple


ACTION_FILTER_APPLY = "apply"
ACTION_FILTER_MONITOR_ONLY = "monitor_only"
VALID_ACTION_FILTER_MODES = frozenset(
    {ACTION_FILTER_APPLY, ACTION_FILTER_MONITOR_ONLY}
)
SUPERVISOR_AUTHORITY_ON = "on"
SUPERVISOR_AUTHORITY_OFF = "off"
VALID_SUPERVISOR_AUTHORITY_MODES = frozenset(
    {SUPERVISOR_AUTHORITY_ON, SUPERVISOR_AUTHORITY_OFF}
)
COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS = frozenset({
    "reference_shaping",
    "supervisor_forced_reference_linearization",
    "lane_entry_heading_cost",
    "rule_smpc_bypass",
    "post_solver_action_and_desired_speed",
    "release_recovery_state",
    "next_control_history",
})


def normalize_supervisor_authority_mode(value: object) -> str:
    """Return the canonical complete behavioural-authority treatment."""

    mode = str(value or SUPERVISOR_AUTHORITY_ON).strip().lower()
    if mode not in VALID_SUPERVISOR_AUTHORITY_MODES:
        allowed = ", ".join(sorted(VALID_SUPERVISOR_AUTHORITY_MODES))
        raise ValueError(
            "yield_supervisor_behavioural_authority_mode must be one of "
            f"{{{allowed}}}, got {value!r}"
        )
    return mode


def supervisor_authority_enabled(mode: object) -> bool:
    return normalize_supervisor_authority_mode(mode) == SUPERVISOR_AUTHORITY_ON


def stable_value_sha256(value: object) -> str:
    """Hash scalar/sequence/NumPy-like values without importing NumPy."""

    digest = hashlib.sha256()
    if hasattr(value, "dtype") and hasattr(value, "shape") and hasattr(value, "tobytes"):
        digest.update(str(getattr(value, "dtype")).encode("utf-8"))
        digest.update(repr(tuple(getattr(value, "shape"))).encode("ascii"))
        digest.update(value.tobytes(order="C"))
    else:
        digest.update(repr(value).encode("utf-8"))
    return digest.hexdigest()


def canonical_scalar_channel(value: object, *, name: str) -> float:
    """Canonicalise one numeric solver parameter without hiding vector drift.

    CasADi accepts a Python/NumPy scalar and a singleton NumPy view as the same
    scalar parameter.  Their representations and hashes differ, so authority
    audits must compare their numeric value rather than report a false
    behavioural leak.  More than one value, non-numeric input and non-finite
    values remain hard failures.
    """

    if hasattr(value, "reshape") and hasattr(value, "tolist"):
        flattened = value.reshape(-1).tolist()
    elif isinstance(value, (list, tuple)):
        flattened = []
        pending = list(value)
        while pending:
            item = pending.pop(0)
            if isinstance(item, (list, tuple)):
                pending[0:0] = list(item)
            else:
                flattened.append(item)
    else:
        flattened = [value]
    if len(flattened) != 1:
        raise ValueError(f"{name} must contain exactly one scalar value")
    try:
        result = float(flattened[0])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return 0.0 if result == 0.0 else result


def verify_authority_channels(
    *,
    mode: object,
    nominal: Mapping[str, object],
    actual: Mapping[str, object],
    adaptive_risk_only_channels: Sequence[str] = (),
) -> Dict[str, Any]:
    """Fail closed if authority-off changes a non-risk solver/control channel."""

    canonical = normalize_supervisor_authority_mode(mode)
    if set(nominal) != set(actual):
        raise ValueError("Supervisor authority channel sets differ")
    allowed = set(adaptive_risk_only_channels)
    records: Dict[str, Any] = {}
    failures = []
    for name in sorted(nominal):
        before = stable_value_sha256(nominal[name])
        after = stable_value_sha256(actual[name])
        equal = before == after
        records[name] = {
            "nominal_sha256": before,
            "actual_sha256": after,
            "equal": equal,
            "adaptive_risk_only_exception": name in allowed,
        }
        if canonical == SUPERVISOR_AUTHORITY_OFF and not equal and name not in allowed:
            failures.append(name)
    if failures:
        raise ValueError(
            "Supervisor authority-off leaked into channels: "
            + ", ".join(failures)
        )
    return {
        "schema_version": "supervisor_behavioural_authority_channels_v1",
        "mode": canonical,
        "authority_enabled": canonical == SUPERVISOR_AUTHORITY_ON,
        "status": "pass",
        "adaptive_risk_only_channels": sorted(allowed),
        "channels": records,
    }


def verify_supervisor_candidate_application(
    *,
    mode: object,
    candidate: Mapping[str, object],
    actual: Mapping[str, object],
    expected_channels: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Fail closed unless authority-on applies every candidate solver channel.

    Authority-off is independently checked against its nominal factual path by
    :func:`verify_authority_channels`; its shadow candidate may therefore
    differ from the actual solver input.  This companion audit closes the
    opposite boundary: authority-on cannot compute a candidate and then omit
    that candidate from the factual solver path.
    """

    canonical = normalize_supervisor_authority_mode(mode)
    if not candidate:
        raise ValueError("Supervisor candidate/actual channel set is empty")
    if set(candidate) != set(actual):
        raise ValueError("Supervisor candidate/actual channel sets differ")
    if expected_channels is not None and set(candidate) != set(expected_channels):
        missing = sorted(set(expected_channels) - set(candidate))
        extra = sorted(set(candidate) - set(expected_channels))
        raise ValueError(
            "Supervisor candidate channel set mismatch; "
            f"missing={missing}, extra={extra}"
        )
    required = canonical == SUPERVISOR_AUTHORITY_ON
    records: Dict[str, Any] = {}
    failures = []
    for name in sorted(candidate):
        candidate_hash = stable_value_sha256(candidate[name])
        actual_hash = stable_value_sha256(actual[name])
        equal = candidate_hash == actual_hash
        records[name] = {
            "candidate_sha256": candidate_hash,
            "actual_sha256": actual_hash,
            "equal": equal,
        }
        if required and not equal:
            failures.append(name)
    if failures:
        raise ValueError(
            "Supervisor authority-on failed to apply candidate channels: "
            + ", ".join(failures)
        )
    return {
        "schema_version": "supervisor_candidate_application_channels_v1",
        "mode": canonical,
        "authority_enabled": required,
        "candidate_equality_required": required,
        "status": "pass",
        "channels": records,
    }


def verify_complete_behavioural_authority_manifest(
    *, mode: object, channels: Mapping[str, Mapping[str, object]]
) -> Dict[str, Any]:
    """Require all seven behavioural channels on every audited step.

    ``requested`` means the computed candidate differs from the nominal path
    on that step.  Authority-on must apply every requested candidate;
    authority-off must apply none and independently attest factual neutrality.
    Exact key equality prevents a missing or newly added behavioural channel
    from silently falling outside the causal treatment boundary.
    """

    canonical = normalize_supervisor_authority_mode(mode)
    expected = set(COMPLETE_BEHAVIOURAL_AUTHORITY_CHANNELS)
    actual_keys = set(channels)
    if actual_keys != expected:
        missing = sorted(expected - actual_keys)
        extra = sorted(actual_keys - expected)
        raise ValueError(
            "Complete supervisor behavioural channel set mismatch; "
            f"missing={missing}, extra={extra}"
        )
    failures = []
    records: Dict[str, Any] = {}
    for name in sorted(expected):
        value = channels[name]
        if not isinstance(value, Mapping):
            failures.append(name + ":not_mapping")
            continue
        computed = value.get("candidate_computed") is True
        requested = value.get("requested") is True
        applied = value.get("applied") is True
        consistent = value.get("authority_assignment_consistent") is True
        factual_neutral = value.get("factual_neutral_when_off") is True
        if not computed:
            failures.append(name + ":candidate_not_computed")
        if not consistent:
            failures.append(name + ":assignment_inconsistent")
        if canonical == SUPERVISOR_AUTHORITY_ON and applied != requested:
            failures.append(name + ":authority_on_application")
        if canonical == SUPERVISOR_AUTHORITY_OFF and applied:
            failures.append(name + ":authority_off_applied")
        if canonical == SUPERVISOR_AUTHORITY_OFF and not factual_neutral:
            failures.append(name + ":authority_off_not_neutral")
        records[name] = {
            "candidate_computed": computed,
            "requested": requested,
            "applied": applied,
            "authority_assignment_consistent": consistent,
            "factual_neutral_when_off": factual_neutral,
        }
    if failures:
        raise ValueError(
            "Complete supervisor behavioural-authority manifest failed: "
            + ", ".join(failures)
        )
    return {
        "schema_version": "complete_supervisor_behavioural_authority_manifest_v1",
        "mode": canonical,
        "authority_enabled": canonical == SUPERVISOR_AUTHORITY_ON,
        "status": "pass",
        "expected_channels": sorted(expected),
        "channels": records,
    }


@dataclass(frozen=True)
class IsolatedSupervisorShadow:
    result: Any
    next_shadow_state: Dict[str, Any]
    protected_restored: bool


def run_isolated_supervisor_shadow(
    *,
    owner: object,
    shadow_state: Mapping[str, Any],
    shadow_fields: Sequence[str],
    protected_fields: Sequence[str],
    callback: Callable[[], Any],
) -> IsolatedSupervisorShadow:
    """Run a stateful supervisor counterfactual without factual-state leakage.

    Only ``shadow_fields`` persist into the next shadow call.  All factual and
    protected fields are restored even if the callback raises.  Production
    uses this for the authority-off reference and post-solver candidates.
    """

    names = tuple(dict.fromkeys(tuple(shadow_fields) + tuple(protected_fields)))
    missing = [name for name in names if not hasattr(owner, name)]
    if missing:
        raise AttributeError("Missing isolated supervisor fields: " + ", ".join(missing))
    factual = {name: deepcopy(getattr(owner, name)) for name in names}
    result: Any = None
    next_shadow: Dict[str, Any] = {}
    try:
        for name in shadow_fields:
            if name in shadow_state:
                setattr(owner, name, deepcopy(shadow_state[name]))
        result = callback()
        next_shadow = {
            name: deepcopy(getattr(owner, name)) for name in shadow_fields
        }
    finally:
        for name, value in factual.items():
            setattr(owner, name, value)
    restored = all(
        stable_value_sha256(getattr(owner, name)) == stable_value_sha256(value)
        for name, value in factual.items()
    )
    if not restored:
        raise RuntimeError("Supervisor shadow isolation failed to restore factual state")
    return IsolatedSupervisorShadow(
        result=result,
        next_shadow_state=next_shadow,
        protected_restored=True,
    )


def normalize_action_filter_mode(value: object) -> str:
    """Return a validated canonical post-solver action-filter mode."""

    mode = str(value or ACTION_FILTER_APPLY).strip().lower()
    if mode not in VALID_ACTION_FILTER_MODES:
        allowed = ", ".join(sorted(VALID_ACTION_FILTER_MODES))
        raise ValueError(
            "yield_post_solver_action_filter_mode must be one of "
            f"{{{allowed}}}, got {value!r}"
        )
    return mode


def _finite_pair(values: Iterable[object], label: str) -> Tuple[float, float]:
    converted = tuple(float(value) for value in values)
    if len(converted) != 2:
        raise ValueError(f"{label} must contain exactly acceleration and steering")
    if not all(math.isfinite(value) for value in converted):
        raise ValueError(f"{label} must contain only finite values, got {converted!r}")
    return converted[0], converted[1]


@dataclass(frozen=True)
class ActionFilterDecision:
    """Immutable factual/counterfactual record at the action-authority boundary."""

    mode: str
    nominal_u: Tuple[float, float]
    nominal_v_des: float
    candidate_u: Tuple[float, float]
    candidate_v_des: float
    actual_u: Tuple[float, float]
    actual_v_des: float
    intervention_requested: bool
    intervention_applied: bool

    @property
    def authority_enabled(self) -> bool:
        return self.mode == ACTION_FILTER_APPLY

    def as_dict(self) -> dict:
        return {
            "schema_version": "post_solver_action_filter_decision_v1",
            "mode": self.mode,
            "authority_enabled": self.authority_enabled,
            "nominal_solver_command": {
                "a_des": self.nominal_u[0],
                "df_des": self.nominal_u[1],
                "v_des": self.nominal_v_des,
            },
            "supervisor_candidate_command": {
                "a_des": self.candidate_u[0],
                "df_des": self.candidate_u[1],
                "v_des": self.candidate_v_des,
            },
            "actual_command": {
                "a_des": self.actual_u[0],
                "df_des": self.actual_u[1],
                "v_des": self.actual_v_des,
            },
            "intervention_requested": self.intervention_requested,
            "intervention_applied": self.intervention_applied,
            "causal_boundary": (
                "This record audits the post-solver (a_des, df_des, v_des) channel "
                "of the complete behavioural-authority treatment; upstream and "
                "next-state channels are audited by the enclosing SMPC step record."
            ),
        }


def arbitrate_post_solver_action(
    *,
    mode: object,
    nominal_u: Iterable[object],
    nominal_v_des: object,
    candidate_u: Iterable[object],
    candidate_v_des: object,
    tolerance: float = 1.0e-9,
) -> ActionFilterDecision:
    """Select the factual command while retaining the shadow candidate.

    ``monitor_only`` is intentionally not a shortcut around supervisor
    computation.  Callers must compute ``candidate_*`` first, including normal
    release/recovery state transitions, then use this function at the final
    action boundary.
    """

    canonical_mode = normalize_action_filter_mode(mode)
    nominal_pair = _finite_pair(nominal_u, "nominal_u")
    candidate_pair = _finite_pair(candidate_u, "candidate_u")
    nominal_speed = float(nominal_v_des)
    candidate_speed = float(candidate_v_des)
    if not math.isfinite(nominal_speed) or not math.isfinite(candidate_speed):
        raise ValueError("nominal_v_des and candidate_v_des must be finite")
    tolerance = float(tolerance)
    if not math.isfinite(tolerance) or tolerance < 0.0:
        raise ValueError(f"tolerance must be finite and non-negative, got {tolerance!r}")

    requested = any(
        abs(left - right) > tolerance
        for left, right in zip(
            (*nominal_pair, nominal_speed),
            (*candidate_pair, candidate_speed),
        )
    )
    if canonical_mode == ACTION_FILTER_APPLY:
        actual_pair = candidate_pair
        actual_speed = candidate_speed
    else:
        actual_pair = nominal_pair
        actual_speed = nominal_speed

    return ActionFilterDecision(
        mode=canonical_mode,
        nominal_u=nominal_pair,
        nominal_v_des=nominal_speed,
        candidate_u=candidate_pair,
        candidate_v_des=candidate_speed,
        actual_u=actual_pair,
        actual_v_des=actual_speed,
        intervention_requested=requested,
        intervention_applied=(
            canonical_mode == ACTION_FILTER_APPLY and requested
        ),
    )


def integrate_post_solver_action_filter(
    *,
    mode: object,
    nominal_u: Iterable[object],
    nominal_v_des: object,
    candidate_u: Iterable[object],
    candidate_v_des: object,
    supervisor_state: Mapping[str, Any],
    tolerance: float = 1.0e-9,
) -> Tuple[ActionFilterDecision, Dict[str, Any], Dict[str, Any]]:
    """Audit one post-solver channel after its candidate was computed.

    The caller supplies a candidate command and diagnostic state.  In the full
    authority-off production path that state machine runs in isolated shadow
    state before this helper is called: the candidate/shadow diagnostics are
    retained, while factual phase/release/recovery state remains untouched.
    ``monitor_only`` therefore selects the nominal command and relabels any
    candidate-only ``applied`` details as shadow evidence; it does not imply
    that supervisor state is factual in the off arm.
    """

    state = deepcopy(dict(supervisor_state))
    decision = arbitrate_post_solver_action(
        mode=mode,
        nominal_u=nominal_u,
        nominal_v_des=nominal_v_des,
        candidate_u=candidate_u,
        candidate_v_des=candidate_v_des,
        tolerance=tolerance,
    )
    candidate_applied = deepcopy(state.get("applied"))
    recovery = state.get("recovery")
    candidate_recovery_applied = (
        deepcopy(recovery.get("applied"))
        if isinstance(recovery, dict)
        else None
    )
    record = decision.as_dict()
    record["supervisor_candidate_details"] = candidate_applied
    record["recovery_candidate_details"] = candidate_recovery_applied
    if decision.mode == ACTION_FILTER_MONITOR_ONLY:
        state["shadow_applied"] = candidate_applied
        state["applied"] = None
        if isinstance(recovery, dict):
            recovery["shadow_applied"] = candidate_recovery_applied
            recovery["applied"] = None
    state["post_solver_action_filter"] = record
    return decision, state, record
