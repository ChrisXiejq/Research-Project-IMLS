"""Validated MultiPath mode probabilities for the multimodal SMPC.

The controller uses the same normalized joint probability vector in the
expected tracking objective and in the adaptive chance-constraint budget.
Invalid probabilities are a scientific-integrity failure: silently replacing
them with equal weights would change the implemented controller.
"""

from __future__ import annotations

import hashlib
import numpy as np


OBJECTIVE_WEIGHTING_ID = "multipath_joint_probability_expected_cost_v2"
OBJECTIVE_WEIGHTING_CONTRACT = (
    "normalized complete joint-mode probabilities weight post-split branch "
    "costs; one shared pre-split branch has unit weight; the same probability "
    "vector weights adaptive risk; no unweighted runtime option"
)
OBJECTIVE_WEIGHTING_CONTRACT_SHA256 = hashlib.sha256(
    OBJECTIVE_WEIGHTING_CONTRACT.encode("utf-8")
).hexdigest()


def normalize_probability_vector(values, *, expected_size: int, label: str):
    """Return a finite non-negative probability vector that sums to one."""

    expected_size = int(expected_size)
    if expected_size < 1:
        raise ValueError("expected_size must be positive")
    vector = np.asarray(values, dtype=float).reshape(-1)
    if vector.size != expected_size:
        raise ValueError(
            f"{label} must contain {expected_size} values, got {vector.size}"
        )
    if not np.isfinite(vector).all():
        raise ValueError(f"{label} contains non-finite values")
    if np.any(vector < 0.0):
        raise ValueError(f"{label} contains negative values")
    total = float(np.sum(vector))
    if not np.isfinite(total) or total <= 0.0:
        raise ValueError(f"{label} must have positive finite mass")
    normalized = vector / total
    if not np.isclose(float(np.sum(normalized)), 1.0, atol=1.0e-12, rtol=0.0):
        raise ValueError(f"{label} normalization failed")
    return normalized


def joint_mode_probabilities(per_target_probabilities, *, n_targets: int, n_modes: int):
    """Build the joint-mode vector in the controller's flat index order.

    ``_joint_mode_component`` in :mod:`mpc_utils` treats target 0 as the least
    significant base-``n_modes`` digit. Repeated outer products followed by a
    C-order flatten produce the matching order for one target and the current
    two-target extension. The give-way experiments use one target, but the
    contract remains explicit for every supported problem size.
    """

    n_targets = int(n_targets)
    n_modes = int(n_modes)
    if n_targets < 1 or n_modes < 1:
        raise ValueError("n_targets and n_modes must be positive")
    matrix = np.asarray(per_target_probabilities, dtype=float)
    if matrix.shape != (n_targets, n_modes):
        raise ValueError(
            "per-target probabilities must have shape "
            f"({n_targets}, {n_modes}), got {matrix.shape}"
        )
    rows = [
        normalize_probability_vector(
            matrix[index],
            expected_size=n_modes,
            label=f"target[{index}] mode probabilities",
        )
        for index in range(n_targets)
    ]
    joint = np.asarray(
        [
            np.prod(
                [
                    rows[target_index][
                        (joint_index // (n_modes ** target_index)) % n_modes
                    ]
                    for target_index in range(n_targets)
                ]
            )
            for joint_index in range(n_modes ** n_targets)
        ],
        dtype=float,
    )
    return normalize_probability_vector(
        joint,
        expected_size=n_modes ** n_targets,
        label="joint mode probabilities",
    )


def active_objective_weights(joint_probabilities, *, active_branch_count: int):
    """Weights used by the branch tracking objective.

    Before the policy tree branches there is only one shared policy cost, so
    its expectation has weight one. Once all joint branches are explicit,
    every branch receives its normalized MultiPath joint probability.
    """

    active_branch_count = int(active_branch_count)
    joint = np.asarray(joint_probabilities, dtype=float).reshape(-1)
    if active_branch_count == 1:
        normalize_probability_vector(
            joint,
            expected_size=joint.size,
            label="joint mode probabilities",
        )
        return np.ones(1, dtype=float)
    if active_branch_count != joint.size:
        raise ValueError(
            "active branches must be one shared branch or the complete joint "
            f"mode set; got {active_branch_count} branches and {joint.size} probabilities"
        )
    return normalize_probability_vector(
        joint,
        expected_size=active_branch_count,
        label="active objective probabilities",
    )


__all__ = [
    "OBJECTIVE_WEIGHTING_CONTRACT",
    "OBJECTIVE_WEIGHTING_CONTRACT_SHA256",
    "OBJECTIVE_WEIGHTING_ID",
    "active_objective_weights",
    "joint_mode_probabilities",
    "normalize_probability_vector",
]
