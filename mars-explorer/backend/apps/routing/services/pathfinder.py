"""A* route planner on a numeric DEM grid.

Pipeline
1. Points (query CRS, explicit latitude convention) → DEM CRS.
2. Read ONLY the DEM window around all points (+ margin), decimated to at most
   ``MAX_GRID_SIDE`` cells per side. The effective grid resolution is reported.
3. Ground cell sizes in metres are geodesic distances between neighbouring cell centres
   on the DEM body's ellipsoid (correct for geographic AND projected DEMs, e.g. the
   equirectangular MOLA MEGDR, whose x metres shrink with cos(latitude) on the ground).
4. Per-cell slope (central differences) and roughness (TRI); hazards (not REJECTED) block
   a disc of (radius + profile buffer).
5. A* over an 8-connected grid with the profile cost (see profiles.py); admissible
   heuristic = straight-line distance with the smallest cell sizes. Diagonal steps may not
   cut the corner between two cells when either orthogonal neighbour is impassable.
6. Results: geometry, distance (horizontal & 3-D), elevation profile, ascent/descent,
   max grade, share of distance over cells without DEM data.

Cells without DEM data are NEVER treated as safe: CONSERVATIVE forbids them, STANDARD
allows them at a penalty and reports them; above the profile's limit the route is refused
with INSUFFICIENT_TERRAIN_DATA.
"""
from __future__ import annotations

import heapq
import math
from typing import Any

import numpy as np

from apps.routing.profiles import MovementProfile
from services import dem_reader, remote_raster  # noqa: F401 - kept for callers that patch them here
from services.mars_coordinates import adapt_latitude

# The planner is split into small modules (v0.4); the names are re-exported here so existing
# callers and tests keep working.
from .cost_surface import block_hazards, path_cost, step_cost  # noqa: F401
from .route_metrics import compare_routes, describe_route, summarize  # noqa: F401
from .route_validator import segment_clear, simplify_path, supercover_cells, validate_route  # noqa: F401
from .spatial_grid import (  # noqa: F401
    CLASS_KNOWN,
    CLASS_NONE,
    CLASS_PARTIAL,
    MARGIN_FRACTION,
    MAX_GRID_SIDE,
    MIN_MARGIN_CELLS,
    STATUS_FOUND,
    STATUS_INSUFFICIENT,
    STATUS_NO_PASSABLE,
    WINDOW_SCALES,
    RoutePlanningError,
    TerrainGrid,
    build_grid,
)
from .terrain_constraints import blocking_reasons, cell_passable  # noqa: F401

NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
NEIGHBOURS_4 = [(-1, 0), (0, -1), (0, 1), (1, 0)]


def astar(grid: TerrainGrid, start: tuple[int, int], goal: tuple[int, int], profile: MovementProfile,
          extra_cost: np.ndarray | None = None, allow_unknown: bool | None = None,
          use_heuristic: bool = True) -> list[tuple[int, int]] | None:
    """Least-cost path. ``use_heuristic=False`` turns A* into Dijkstra (the reference used by the
    tests: both must return the same cost, because the heuristic is admissible)."""
    allow_unknown = profile.allow_unknown_terrain if allow_unknown is None else allow_unknown
    unknown_mult = profile.unknown_multiplier if math.isfinite(profile.unknown_multiplier) else 1.0
    h, w = grid.shape
    dxmin, dymin = float(grid.dx_m.min()), float(grid.dy_m.min())
    gi, gj = goal

    neighbours = NEIGHBOURS_4 if profile.connectivity == 4 else NEIGHBOURS

    def heuristic(i: int, j: int) -> float:
        if not use_heuristic:
            return 0.0
        if profile.connectivity == 4:  # Manhattan lower bound when diagonals are not allowed
            return abs(gj - j) * dxmin + abs(gi - i) * dymin
        return math.hypot((gj - j) * dxmin, (gi - i) * dymin)

    g = np.full(h * w, np.inf)
    came = np.full(h * w, -1, dtype=np.int64)
    s = start[0] * w + start[1]
    g[s] = 0.0
    heap = [(heuristic(*start), 0.0, s)]
    closed = np.zeros(h * w, dtype=bool)
    goal_idx = gi * w + gj
    while heap:
        _, gc, cur = heapq.heappop(heap)
        if closed[cur]:
            continue
        if cur == goal_idx:
            break
        closed[cur] = True
        i, j = divmod(cur, w)
        for di, dj in neighbours:
            ni, nj = i + di, j + dj
            if not (0 <= ni < h and 0 <= nj < w):
                continue
            nxt = ni * w + nj
            if closed[nxt]:
                continue
            step = step_cost(grid, i, j, ni, nj, profile, allow_unknown, unknown_mult)
            if step is None:
                continue
            if extra_cost is not None:
                step *= float(extra_cost[ni, nj])
            ng = gc + step
            if ng < g[nxt]:
                g[nxt] = ng
                came[nxt] = cur
                heapq.heappush(heap, (ng + heuristic(ni, nj), ng, nxt))
    if not math.isfinite(g[goal_idx]):
        return None
    path = []
    cur = goal_idx
    while cur != -1:
        path.append(divmod(int(cur), w))
        if cur == s:
            break
        cur = came[cur]
    return path[::-1]


def _legs(grid, cells_pts, profile, extra_cost=None):
    path: list[tuple[int, int]] = []
    for a, b in zip(cells_pts[:-1], cells_pts[1:]):
        leg = astar(grid, a, b, profile, extra_cost=extra_cost)
        if leg is None:
            return None
        path.extend(leg if not path else leg[1:])
    return path


def plan_route(ds, points_query: list[tuple[float, float]], query_crs, query_lat_conv: str, profile: MovementProfile,
               hazards_query: list[tuple[float, float, float]] = (), include_return: bool = True,
               include_alternative: bool = True) -> dict:
    from pyproj import CRS, Transformer

    if len(points_query) < 2:
        raise RoutePlanningError(STATUS_INSUFFICIENT, "At least a start and an end point are required")
    ds_crs = CRS.from_wkt(ds.crs)
    to_ds = Transformer.from_crs(query_crs, ds_crs, always_xy=True)
    to_query = Transformer.from_crs(ds_crs, query_crs, always_xy=True)

    def q2ds(lon, lat):
        lat2, _ = adapt_latitude(lat, query_lat_conv, ds.latitude_convention)
        return to_ds.transform(lon, lat2)

    pts_ds = [q2ds(lon, lat) for lon, lat in points_query]
    hz_ds = [(*q2ds(lon, lat), (r or 0.0) + profile.hazard_buffer_m) for lon, lat, r in hazards_query]
    # Search windows grow when no route is found: a detour may lie outside the first window.
    # The last attempt covers the whole DEM (decimated to MAX_GRID_SIDE).
    last_error = None
    for scale in WINDOW_SCALES:
        try:
            return _plan_in_window(ds, pts_ds, points_query, to_query, query_lat_conv, profile, hz_ds,
                                   include_return, include_alternative, scale)
        except RoutePlanningError as exc:
            if not exc.details.get("retry_larger_window"):
                raise
            exc.details.pop("retry_larger_window", None)
            last_error = exc
    raise last_error


def _plan_in_window(ds, pts_ds, points_query, to_query, query_lat_conv, profile, hz_ds, include_return,
                    include_alternative, scale) -> dict:
    grid = build_grid(ds, pts_ds, to_query, margin_scale=scale)
    if profile.required_resolution_m is not None:
        coarsest = max(grid.meta["cell_size_m"]["dx_max"], grid.meta["cell_size_m"]["dy_mean"])
        if coarsest > profile.required_resolution_m:
            raise RoutePlanningError(
                STATUS_INSUFFICIENT,
                f"The routing grid has {coarsest:,.0f} m cells; this plan requires {profile.required_resolution_m:,.0f} m or finer",
                {"grid": grid.meta, "required_resolution_m": profile.required_resolution_m},
            )
    blocked_cells = block_hazards(grid, hz_ds)
    cells = [grid.cell_of(x, y) for x, y in pts_ds]
    for k, c in enumerate(cells):
        if c is None:
            raise RoutePlanningError(STATUS_INSUFFICIENT, f"Point {k} is outside the analysed DEM window")
        if grid.blocked[c]:
            raise RoutePlanningError(STATUS_NO_PASSABLE, f"Point {k} lies inside a hazard area (incl. profile buffer)")
        if math.isnan(grid.z[c]) and not profile.allow_unknown_terrain:
            raise RoutePlanningError(STATUS_INSUFFICIENT, f"Point {k} has no DEM elevation")

    primary = _legs(grid, cells, profile)
    if primary is None:
        # Distinguish "blocked by missing data" from "blocked by slope/hazards".
        relaxed = MovementProfile(**{**profile.__dict__, "allow_unknown_terrain": True, "unknown_multiplier": 1.0})
        if not profile.allow_unknown_terrain and _legs(grid, cells, relaxed) is not None:
            raise RoutePlanningError(STATUS_INSUFFICIENT, "A route would have to cross cells without DEM data, which this profile forbids", {"grid": grid.meta, "retry_larger_window": True})
        raise RoutePlanningError(STATUS_NO_PASSABLE, "No route satisfies the profile limits (slope / hazards) inside the analysed window", {"grid": grid.meta, "retry_larger_window": True})

    ends = (list(points_query[0]), list(points_query[-1]))
    route = describe_route(grid, primary, profile, ds.latitude_convention, query_lat_conv, ends)
    check = validate_route(grid, primary, profile, route.pop("simplified_cells", None))
    route["validation"] = check
    if not check["valid"]:  # never return a route that fails the independent re-check
        raise RoutePlanningError("PROCESSING_ERROR", "The computed route failed validation and was discarded", {"grid": grid.meta, "problems": check["problems"]})
    if route["unknown_terrain_fraction"] > profile.max_unknown_fraction:
        raise RoutePlanningError(
            STATUS_INSUFFICIENT,
            f"{route['unknown_terrain_fraction']:.0%} of the best route crosses cells without DEM data (profile limit {profile.max_unknown_fraction:.0%})",
            {"grid": grid.meta},
        )

    grid.meta["window_scale"] = "whole DEM" if scale >= 1e6 else scale
    grid.meta["cells_blocked_by"] = blocking_reasons(grid, profile)
    out: dict[str, Any] = {"status": STATUS_FOUND, "route_classification": route["classification"], "route": route,
                           "grid": grid.meta, "hazard_cells_blocked": blocked_cells}
    if include_return:
        back = _legs(grid, cells[::-1], profile)
        out["return_route"] = describe_route(grid, back, profile, ds.latitude_convention, query_lat_conv, (ends[1], ends[0])) if back else None
        if out["return_route"]:
            out["return_route"]["validation"] = validate_route(grid, back, profile, out["return_route"].pop("simplified_cells", None))
    if include_alternative:
        extra = np.ones(grid.shape)
        for i, j in primary:
            extra[max(0, i - 1) : i + 2, max(0, j - 1) : j + 2] = 4.0
        alt = _legs(grid, cells, profile, extra_cost=extra)
        if alt:
            overlap = len(set(alt) & set(primary)) / max(len(alt), 1)
            alt_sum = describe_route(grid, alt, profile, ds.latitude_convention, query_lat_conv, ends)
            alt_sum["overlap_with_primary"] = overlap
            alt_sum["validation"] = validate_route(grid, alt, profile, alt_sum.pop("simplified_cells", None))
            out["alternative_route"] = alt_sum if overlap < 0.9 else None
            if overlap >= 0.9:
                out["alternative_note"] = "No sufficiently distinct alternative inside the analysed window"
        else:
            out["alternative_route"] = None
    out["comparison"] = compare_routes(route, out.get("alternative_route"))
    return out
