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
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from apps.routing.profiles import MovementProfile
from services import remote_raster, dem_reader
from services.mars_coordinates import adapt_latitude

MAX_GRID_SIDE = 300
MARGIN_FRACTION = 0.25  # extra area around the points' bounding box
MIN_MARGIN_CELLS = 10
WINDOW_SCALES = (1.0, 3.0, 1e6)  # last = whole DEM

STATUS_FOUND = "ROUTE_FOUND"
STATUS_INSUFFICIENT = "INSUFFICIENT_TERRAIN_DATA"
STATUS_NO_PASSABLE = "NO_PASSABLE_ROUTE"

CLASS_KNOWN = "KNOWN_TERRAIN_ROUTE"
CLASS_PARTIAL = "PARTIALLY_UNVERIFIED_ROUTE"
CLASS_NONE = "NO_VALID_ROUTE"

NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


class RoutePlanningError(Exception):
    def __init__(self, status: str, reason: str, details: dict | None = None):
        super().__init__(reason)
        self.status = status
        self.reason = reason
        self.details = details or {}


@dataclass
class TerrainGrid:
    z: np.ndarray            # (H, W) metres, NaN = no data
    dx_m: np.ndarray         # (H,) east-west ground step of each row
    dy_m: np.ndarray         # (H-1,) north-south ground step between row i and i+1
    slope_deg: np.ndarray    # (H, W)
    tri_m: np.ndarray        # (H, W)
    blocked: np.ndarray      # (H, W) bool (hazards)
    x0: float                # dataset-CRS coordinate of cell (0,0) centre
    y0: float
    px: float                # dataset-CRS step per grid column / row (signed)
    py: float
    decimation: float
    to_query: Any            # Transformer dataset CRS -> query CRS
    meta: dict = field(default_factory=dict)
    proximity: np.ndarray | None = None  # (H, W) 0..1 hazard proximity outside the blocked discs

    @property
    def shape(self) -> tuple[int, int]:
        return self.z.shape

    def cell_of(self, x: float, y: float) -> tuple[int, int] | None:
        j = int(math.floor((x - self.x0) / self.px + 0.5))
        i = int(math.floor((y - self.y0) / self.py + 0.5))
        h, w = self.shape
        return (i, j) if 0 <= i < h and 0 <= j < w else None

    def xy_of(self, i: int, j: int) -> tuple[float, float]:
        return self.x0 + j * self.px, self.y0 + i * self.py

    def step_length(self, i: int, j: int, ni: int, nj: int) -> float:
        dx = 0.5 * (self.dx_m[i] + self.dx_m[ni]) * abs(nj - j)
        dy = self.dy_m[min(i, ni)] * abs(ni - i) if ni != i else 0.0
        return math.hypot(dx, dy)


def build_grid(ds, points_ds: list[tuple[float, float]], to_query, max_side: int = MAX_GRID_SIDE, margin_scale: float = 1.0) -> TerrainGrid:
    from pyproj import CRS, Geod, Transformer

    rasterio = dem_reader._import_rasterio()
    from rasterio.windows import Window

    ds_crs = CRS.from_wkt(ds.crs)
    with remote_raster.open_raster(ds.file_path) as src:
        t = src.transform
        if t.b != 0 or t.d != 0:
            raise RoutePlanningError(STATUS_INSUFFICIENT, "Rotated DEM grids are not supported")
        rc = []
        period = dem_reader.x_wrap_period(ds_crs, src.bounds.left, src.bounds.right)
        for x, y in points_ds:
            if period:
                x = (x - src.bounds.left) % period + src.bounds.left
            col = math.floor((x - t.c) / t.a)
            row = math.floor((y - t.f) / t.e)
            if not (0 <= row < src.height and 0 <= col < src.width):
                raise RoutePlanningError(STATUS_INSUFFICIENT, "A route point lies outside the DEM", {"point_dataset_xy": [x, y]})
            rc.append((row, col))
        rows = [r for r, _ in rc]
        cols = [c for _, c in rc]
        span = max(max(rows) - min(rows), max(cols) - min(cols), 1)
        margin = int(max(MIN_MARGIN_CELLS, span * MARGIN_FRACTION) * margin_scale)
        r0, r1 = max(0, min(rows) - margin), min(src.height - 1, max(rows) + margin)
        c0, c1 = max(0, min(cols) - margin), min(src.width - 1, max(cols) + margin)
        wh, ww = r1 - r0 + 1, c1 - c0 + 1
        factor = max(1.0, max(wh, ww) / max_side)
        out_h, out_w = max(2, round(wh / factor)), max(2, round(ww / factor))
        data = src.read(1, window=Window(c0, r0, ww, wh), out_shape=(out_h, out_w), masked=True)
        scale = float(src.scales[0]) if src.scales else 1.0
        offset = float(src.offsets[0]) if src.offsets else 0.0
    z = np.ma.filled(data.astype("float64"), np.nan) * scale + offset
    z[~np.isfinite(z)] = np.nan
    px = t.a * ww / out_w
    py = t.e * wh / out_h
    x0 = t.c + c0 * t.a + 0.5 * px
    y0 = t.f + r0 * t.e + 0.5 * py

    # Geodesic ground distances on the DEM body's ellipsoid.
    ell = ds_crs.ellipsoid
    geod = Geod(a=ell.semi_major_metre, b=ell.semi_minor_metre)
    to_geo = Transformer.from_crs(ds_crs, ds_crs.geodetic_crs, always_xy=True)
    ys = y0 + np.arange(out_h) * py
    lon_a, lat_a = to_geo.transform(np.full(out_h, x0), ys)
    lon_b, lat_b = to_geo.transform(np.full(out_h, x0 + px), ys)
    _, _, dx = geod.inv(lon_a, lat_a, lon_b, lat_b)
    _, _, dy = geod.inv(lon_a[:-1], lat_a[:-1], lon_a[1:], lat_a[1:])
    dx = np.maximum(np.asarray(dx, dtype="float64"), 1e-6)
    dy = np.maximum(np.asarray(dy, dtype="float64"), 1e-6)

    gy, gx = np.gradient(z)
    slope = np.degrees(np.arctan(np.hypot(gx / dx[:, None], gy / float(dy.mean()))))
    pad = np.pad(z, 1, mode="edge")
    acc = np.zeros_like(z)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            acc += (pad[1 + di : 1 + di + out_h, 1 + dj : 1 + dj + out_w] - z) ** 2
    tri = np.sqrt(acc)
    return TerrainGrid(
        z=z, dx_m=dx, dy_m=dy, slope_deg=slope, tri_m=tri, blocked=np.zeros_like(z, dtype=bool),
        x0=x0, y0=y0, px=px, py=py, decimation=factor, to_query=to_query,
        meta={
            "rows": out_h, "cols": out_w, "decimation_factor": round(factor, 3),
            "cell_size_m": {"dx_min": float(dx.min()), "dx_max": float(dx.max()), "dy_mean": float(dy.mean())},
            "dem_window": {"row0": r0, "col0": c0, "rows": wh, "cols": ww},
            "nodata_fraction": float(np.isnan(z).mean()),
        },
    )


def block_hazards(grid: TerrainGrid, hazards_ds: list[tuple[float, float, float]]) -> int:
    """Block discs of radius r (metres) around hazards given in DATASET CRS (x, y, r).

    Cells between r and 2r get a hazard proximity 0..1 (1 at the disc edge), used by the
    hazard-proximity cost term. Returns the number of blocked cells."""
    h, w = grid.shape
    if grid.proximity is None:
        grid.proximity = np.zeros(grid.shape)
    n = 0
    for x, y, radius in hazards_ds:
        cell = grid.cell_of(x, y)
        if cell is None:
            continue
        i, j = cell
        r = max(radius, 0.0)
        outer = 2 * r
        ri = int(math.ceil(outer / max(grid.dy_m.mean(), 1e-6)))
        rj = int(math.ceil(outer / max(grid.dx_m[i], 1e-6)))
        for ii in range(max(0, i - ri), min(h, i + ri + 1)):
            for jj in range(max(0, j - rj), min(w, j + rj + 1)):
                dyy = (ii - i) * grid.dy_m.mean()
                dxx = (jj - j) * grid.dx_m[ii]
                d = math.hypot(dxx, dyy)
                if d <= r or (ii == i and jj == j):
                    if not grid.blocked[ii, jj]:
                        n += 1
                    grid.blocked[ii, jj] = True
                elif r > 0 and d <= outer:
                    grid.proximity[ii, jj] = max(grid.proximity[ii, jj], 1.0 - (d - r) / r)
    return n


def cell_passable(grid: TerrainGrid, i: int, j: int, profile: MovementProfile, allow_unknown: bool) -> bool:
    """A cell may be entered: inside the grid, not in a hazard disc, has a DEM value (unless the
    policy allows unknown terrain) and its slope does not exceed the profile limit."""
    h, w = grid.shape
    if not (0 <= i < h and 0 <= j < w) or grid.blocked[i, j]:
        return False
    if math.isnan(grid.z[i, j]):
        return allow_unknown
    sl = grid.slope_deg[i, j]
    return math.isnan(sl) or sl <= profile.max_slope_deg


def step_cost(grid: TerrainGrid, i: int, j: int, ni: int, nj: int, profile: MovementProfile,
              allow_unknown: bool, unknown_mult: float) -> float | None:
    """Cost of moving from (i, j) to the neighbour (ni, nj), or None if the step is forbidden."""
    if not cell_passable(grid, ni, nj, profile, allow_unknown):
        return None
    di, dj = ni - i, nj - j
    if di and dj:
        # No corner cutting: both cells the diagonal passes between must be passable.
        if not (cell_passable(grid, i + di, j, profile, allow_unknown) and cell_passable(grid, i, j + dj, profile, allow_unknown)):
            return None
    z_a, z_b = grid.z[i, j], grid.z[ni, nj]
    unknown = math.isnan(z_a) or math.isnan(z_b)
    if unknown and not allow_unknown:
        return None
    d = grid.step_length(i, j, ni, nj)
    if unknown:
        dz, grade, rough, mult = 0.0, 0.0, 0.0, unknown_mult
    else:
        dz = z_b - z_a
        grade = math.degrees(math.atan2(abs(dz), d))
        if grade > profile.max_slope_deg:
            return None
        t = grid.tri_m[ni, nj]
        rough = 0.0 if math.isnan(t) else min(t / profile.roughness_ref_m, 1.0)
        mult = 1.0
    prox = float(grid.proximity[ni, nj]) if grid.proximity is not None else 0.0
    return math.hypot(d, dz) * (
        1.0
        + profile.slope_weight * (grade / profile.max_slope_deg) ** 2
        + profile.roughness_weight * rough
        + profile.hazard_proximity_weight * prox
    ) * mult


def path_cost(grid: TerrainGrid, cells: list[tuple[int, int]], profile: MovementProfile) -> float:
    """Total profile cost of a cell path (same function A* minimises)."""
    allow = profile.allow_unknown_terrain
    mult = profile.unknown_multiplier if math.isfinite(profile.unknown_multiplier) else 1.0
    total = 0.0
    for (i, j), (ni, nj) in zip(cells[:-1], cells[1:]):
        c = step_cost(grid, i, j, ni, nj, profile, allow, mult)
        if c is None:
            return float("inf")
        total += c
    return total


def supercover_cells(i0: int, j0: int, i1: int, j1: int) -> list[tuple[int, int]]:
    """Every grid cell a straight segment between two cell centres touches (incl. both cells at
    an exact corner crossing), so a simplified segment can be checked cell by cell."""
    cells = [(i0, j0)]
    di, dj = i1 - i0, j1 - j0
    ni, nj = abs(di), abs(dj)
    si, sj = (1 if di > 0 else -1), (1 if dj > 0 else -1)
    i, j = i0, j0
    a = b = 0
    while a < ni or b < nj:
        # compare (0.5 + a) / ni with (0.5 + b) / nj without division
        lhs, rhs = (1 + 2 * a) * nj, (1 + 2 * b) * ni
        if lhs == rhs:  # passes exactly through a corner: touches both side cells
            cells.append((i + si, j))
            cells.append((i, j + sj))
            i, j, a, b = i + si, j + sj, a + 1, b + 1
        elif lhs < rhs:
            i, a = i + si, a + 1
        else:
            j, b = j + sj, b + 1
        cells.append((i, j))
    return cells


def segment_clear(grid: TerrainGrid, a: tuple[int, int], b: tuple[int, int], profile: MovementProfile) -> bool:
    """True when the straight segment a-b touches only passable cells with known terrain (a
    simplified line must never cross obstacles or NoData) and no step on it exceeds the slope limit."""
    cells = supercover_cells(*a, *b)
    prev = None
    for c in cells:
        if not cell_passable(grid, *c, profile, allow_unknown=False):
            return False
        if prev is not None and prev != c and abs(prev[0] - c[0]) + abs(prev[1] - c[1]) == 1:
            d = grid.step_length(*prev, *c)
            if math.degrees(math.atan2(abs(grid.z[c] - grid.z[prev]), d)) > profile.max_slope_deg:
                return False
        prev = c
    return True


def simplify_path(grid: TerrainGrid, cells: list[tuple[int, int]], profile: MovementProfile) -> list[tuple[int, int]]:
    """Greedy line-of-sight simplification. Segments through unknown terrain are kept cell by
    cell (never straightened across NoData)."""
    if len(cells) <= 2:
        return list(cells)
    out = [cells[0]]
    k = 0
    while k < len(cells) - 1:
        far = k + 1
        for m in range(len(cells) - 1, k + 1, -1):
            if segment_clear(grid, cells[k], cells[m], profile):
                far = m
                break
        out.append(cells[far])
        k = far
    return out


def astar(grid: TerrainGrid, start: tuple[int, int], goal: tuple[int, int], profile: MovementProfile,
          extra_cost: np.ndarray | None = None, allow_unknown: bool | None = None) -> list[tuple[int, int]] | None:
    allow_unknown = profile.allow_unknown_terrain if allow_unknown is None else allow_unknown
    unknown_mult = profile.unknown_multiplier if math.isfinite(profile.unknown_multiplier) else 1.0
    h, w = grid.shape
    dxmin, dymin = float(grid.dx_m.min()), float(grid.dy_m.min())
    gi, gj = goal

    def heuristic(i: int, j: int) -> float:
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
        for di, dj in NEIGHBOURS:
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


def summarize(grid: TerrainGrid, cells: list[tuple[int, int]], ds_lat_conv: str, query_lat_conv: str) -> dict:
    coords = []
    profile_pts = []
    dist = dist3 = ascent = descent = unknown_dist = 0.0
    max_grade = 0.0
    max_cell_slope = 0.0
    unverified: list[list[float]] = []  # [from_m, to_m] along the route
    prev = None
    for i, j in cells:
        x, y = grid.xy_of(i, j)
        lon, lat = grid.to_query.transform(x, y)
        lat, _ = adapt_latitude(float(lat), ds_lat_conv, query_lat_conv)
        coords.append([float(lon), float(lat)])
        zc = grid.z[i, j]
        if prev is not None:
            pi, pj = prev
            d = grid.step_length(pi, pj, i, j)
            zp = grid.z[pi, pj]
            if math.isnan(zc) or math.isnan(zp):
                unknown_dist += d
                dist3 += d
                if unverified and abs(unverified[-1][1] - dist) < 1e-6:
                    unverified[-1][1] = dist + d
                else:
                    unverified.append([dist, dist + d])
            else:
                dz = zc - zp
                dist3 += math.hypot(d, dz)
                ascent += max(dz, 0.0)
                descent += max(-dz, 0.0)
                max_grade = max(max_grade, math.degrees(math.atan2(abs(dz), d)))
            dist += d
        profile_pts.append({"distance_m": round(dist, 2), "elevation_m": None if math.isnan(zc) else float(zc)})
        sl = grid.slope_deg[i, j]
        if not math.isnan(sl):
            max_cell_slope = max(max_cell_slope, float(sl))
        prev = (i, j)
    if len(profile_pts) > 500:  # keep responses small
        idx = np.linspace(0, len(profile_pts) - 1, 500).round().astype(int)
        profile_pts = [profile_pts[k] for k in idx]
    return {
        "geometry": {"type": "LineString", "coordinates": coords},
        "cells": len(cells),
        "distance_m": dist,
        "distance_3d_m": dist3,
        "total_ascent_m": ascent,
        "total_descent_m": descent,
        "max_step_grade_deg": max_grade,
        "unknown_terrain_distance_m": unknown_dist,
        "unknown_terrain_fraction": (unknown_dist / dist) if dist > 0 else 0.0,
        "unverified_segments": [{"from_m": round(a, 2), "to_m": round(b, 2), "status": "UNVERIFIED_NO_DEM_DATA"} for a, b in unverified],
        "max_cell_slope_deg": max_cell_slope,
        "classification": CLASS_PARTIAL if unknown_dist > 0 else CLASS_KNOWN,
        "elevation_profile": profile_pts,
    }


def describe_route(grid: TerrainGrid, cells: list[tuple[int, int]], profile: MovementProfile, ds_lat_conv: str,
                   query_lat_conv: str, endpoints: tuple[list[float], list[float]] | None = None) -> dict:
    """summarize() + cost under the profile + simplified geometry + metrics."""
    r = summarize(grid, cells, ds_lat_conv, query_lat_conv)
    cost = path_cost(grid, cells, profile)
    r["cost"] = cost
    # penalty above pure 3-D distance: slope + roughness + hazard proximity + uncertainty
    r["terrain_cost"] = cost - r["distance_3d_m"]
    simp = simplify_path(grid, cells, profile)
    coords = []
    for i, j in simp:
        lon, lat = grid.to_query.transform(*grid.xy_of(i, j))
        lat, _ = adapt_latitude(float(lat), ds_lat_conv, query_lat_conv)
        coords.append([float(lon), float(lat)])
    if endpoints:
        r["geometry"]["coordinates"][0] = list(endpoints[0])
        r["geometry"]["coordinates"][-1] = list(endpoints[1])
        coords[0], coords[-1] = list(endpoints[0]), list(endpoints[1])
    r["geometry_simplified"] = {"type": "LineString", "coordinates": coords}
    r["simplification"] = (
        "line-of-sight; every cell a simplified segment touches is passable with known DEM values; "
        "metrics are computed on the full cell path"
    )
    r["metrics"] = {
        "distance_m": r["distance_m"],
        "distance_3d_m": r["distance_3d_m"],
        "elevation_gain_m": r["total_ascent_m"],
        "elevation_loss_m": r["total_descent_m"],
        "max_step_grade_deg": r["max_step_grade_deg"],
        "max_cell_slope_deg": r["max_cell_slope_deg"],
        "known_terrain_pct": round(100 * (1 - r["unknown_terrain_fraction"]), 2),
        "nodata_pct_along_route": round(100 * r["unknown_terrain_fraction"], 2),
        "cost": cost,
        "terrain_cost": r["terrain_cost"],
    }
    return r


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
    if route["unknown_terrain_fraction"] > profile.max_unknown_fraction:
        raise RoutePlanningError(
            STATUS_INSUFFICIENT,
            f"{route['unknown_terrain_fraction']:.0%} of the best route crosses cells without DEM data (profile limit {profile.max_unknown_fraction:.0%})",
            {"grid": grid.meta},
        )

    grid.meta["window_scale"] = "whole DEM" if scale >= 1e6 else scale
    out: dict[str, Any] = {"status": STATUS_FOUND, "route_classification": route["classification"], "route": route,
                           "grid": grid.meta, "hazard_cells_blocked": blocked_cells}
    if include_return:
        back = _legs(grid, cells[::-1], profile)
        out["return_route"] = describe_route(grid, back, profile, ds.latitude_convention, query_lat_conv, (ends[1], ends[0])) if back else None
    if include_alternative:
        extra = np.ones(grid.shape)
        for i, j in primary:
            extra[max(0, i - 1) : i + 2, max(0, j - 1) : j + 2] = 4.0
        alt = _legs(grid, cells, profile, extra_cost=extra)
        if alt:
            overlap = len(set(alt) & set(primary)) / max(len(alt), 1)
            alt_sum = describe_route(grid, alt, profile, ds.latitude_convention, query_lat_conv, ends)
            alt_sum["overlap_with_primary"] = overlap
            out["alternative_route"] = alt_sum if overlap < 0.9 else None
            if overlap >= 0.9:
                out["alternative_note"] = "No sufficiently distinct alternative inside the analysed window"
        else:
            out["alternative_route"] = None
    out["comparison"] = compare_routes(route, out.get("alternative_route"))
    return out


def _brief(r: dict, label: str) -> dict:
    m = r["metrics"]
    return {"label": label, "classification": r["classification"], "distance_m": m["distance_m"], "cost": m["cost"],
            "terrain_cost": m["terrain_cost"], "elevation_gain_m": m["elevation_gain_m"],
            "max_cell_slope_deg": m["max_cell_slope_deg"], "known_terrain_pct": m["known_terrain_pct"]}


def compare_routes(a: dict, b: dict | None) -> dict:
    """Route A = lowest cost under the profile; Route B = the most distinct alternative. Both
    costs are evaluated with the same profile (no alternative-search penalty). No travel time."""
    out = {"route_a": _brief(a, "Route A — lowest cost"), "route_b": _brief(b, "Route B — alternative") if b else None}
    if b:
        out["difference_b_minus_a"] = {
            "distance_m": b["metrics"]["distance_m"] - a["metrics"]["distance_m"],
            "terrain_cost": b["metrics"]["terrain_cost"] - a["metrics"]["terrain_cost"],
            "cost": b["metrics"]["cost"] - a["metrics"]["cost"],
        }
    out["note"] = "Cost is a dimensionless weighted length (profile heuristic). No travel time is estimated."
    return out
