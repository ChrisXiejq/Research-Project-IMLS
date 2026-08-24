"""Target-independent road-corridor geometry for supervisor-free SMPC."""

from __future__ import annotations

import numpy as np


def reference_index_from_route_progress(reference_s, current_s):
    """Return the reference index closest to the ego's route progress.

    Selecting a reference by Euclidean position is ambiguous when a route
    bends back near itself.  Frenet progress is one-dimensional and preserves
    route topology, so it cannot jump from the approach to a spatially nearby
    exit segment.
    """

    progress = np.asarray(reference_s, dtype=float).reshape(-1)
    current = float(current_s)
    if progress.size == 0:
        raise ValueError("reference_s must contain at least one value")
    if not np.isfinite(progress).all() or not np.isfinite(current):
        raise ValueError("reference progress values must be finite")
    if np.any(np.diff(progress) < -1.0e-9):
        raise ValueError("reference_s must be non-decreasing")

    upper = int(np.searchsorted(progress, current, side="left"))
    candidates = {
        int(np.clip(upper, 0, progress.size - 1)),
        int(np.clip(upper - 1, 0, progress.size - 1)),
    }
    return min(candidates, key=lambda idx: (abs(progress[idx] - current), idx))


def project_points_to_route_segments(route_xy, query_xy, anchor_xy=None):
    """Project horizon points onto a forward-only suffix of a sampled route.

    Returns path points and unit lateral normals for a convex, locally
    path-aligned corridor constraint.  Target state and interaction phase are
    deliberately absent: this represents road feasibility, not a yield rule.

    Each query is projected causally after the previous projection in route
    arclength.  This prevents a folded or noisy warm start from making the
    corridor run backwards along the route.  ``anchor_xy`` fixes the lower
    arclength bound to the ego's current route position.
    """

    route = np.asarray(route_xy, dtype=float)
    queries = np.asarray(query_xy, dtype=float)
    if route.ndim != 2 or route.shape[0] < 2 or route.shape[1] != 2:
        raise ValueError("route_xy must have shape [N>=2, 2]")
    if queries.ndim != 2 or queries.shape[0] < 1 or queries.shape[1] != 2:
        raise ValueError("query_xy must have shape [M>=1, 2]")
    if not np.isfinite(route).all() or not np.isfinite(queries).all():
        raise ValueError("route and query coordinates must be finite")
    anchor = None if anchor_xy is None else np.asarray(anchor_xy, dtype=float).reshape(-1)
    if anchor is not None and (anchor.shape != (2,) or not np.isfinite(anchor).all()):
        raise ValueError("anchor_xy must contain two finite coordinates")

    all_starts = route[:-1]
    all_deltas = route[1:] - all_starts
    all_lengths_sq = np.einsum("si,si->s", all_deltas, all_deltas)
    all_lengths = np.sqrt(all_lengths_sq)
    route_vertex_s = np.concatenate(([0.0], np.cumsum(all_lengths)))
    valid = all_lengths_sq > 1.0e-10
    if not np.any(valid):
        raise ValueError("route must contain at least one non-degenerate segment")
    starts = all_starts[valid]
    deltas = all_deltas[valid]
    lengths_sq = all_lengths_sq[valid]
    lengths = all_lengths[valid]
    segment_start_s = route_vertex_s[:-1][valid]
    segment_end_s = route_vertex_s[1:][valid]
    source_indices = np.flatnonzero(valid)

    def nearest_progress(point, minimum_s=0.0):
        eligible = segment_end_s >= minimum_s - 1.0e-9
        lower_fraction = np.clip(
            (minimum_s - segment_start_s) / lengths,
            0.0,
            1.0,
        )
        raw_fraction = np.einsum("si,si->s", point - starts, deltas) / lengths_sq
        fractions = np.maximum(np.clip(raw_fraction, 0.0, 1.0), lower_fraction)
        projections = starts + fractions[:, None] * deltas
        squared_distance = np.sum((point - projections) ** 2, axis=1)
        squared_distance[~eligible] = np.inf
        nearest = int(np.argmin(squared_distance))
        progress = float(segment_start_s[nearest] + fractions[nearest] * lengths[nearest])
        return nearest, projections[nearest], float(np.sqrt(squared_distance[nearest])), progress

    previous_s = 0.0
    if anchor is not None:
        _, _, _, previous_s = nearest_progress(anchor)

    selected = []
    points = []
    distances = []
    for query in queries:
        nearest, point, distance, previous_s = nearest_progress(query, previous_s)
        selected.append(nearest)
        points.append(point)
        distances.append(distance)

    selected = np.asarray(selected, dtype=int)
    points = np.asarray(points, dtype=float)
    distances = np.asarray(distances, dtype=float)
    tangents = deltas[selected] / lengths[selected, None]
    normals = np.column_stack((-tangents[:, 1], tangents[:, 0]))
    return points, normals, source_indices[selected], distances
