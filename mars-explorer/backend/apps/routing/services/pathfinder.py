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
   heuristic = straight-line distance with the smallest cell sizes.
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
from services import dem_reader
from services.mars_coordinates import adapt_latitude

MAX_GRID_SIDE = 300
MARGIN_FRACTION = 0.25  # extra area around the points' bounding box
MIN_MARGIN_CELLS = 10
WINDOW_SCALES = (1.0, 3.0, 1e6)  # last = whole DEM

STATUS_FOUND = "ROUTE_FOUND"
STATUS_INSUFFICIENT = "INSUFFICIENT_TERRAIN_DATA"
STATUS_NO_PASSABLE = "NO_PASSABLE_ROUTE"

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
    with rasterio.open(ds.file_path) as src:
        t = src.transform
        if t.b != 0 or t.d != 0:
            raise RoutePlanningError(STATUS_INSUFFICIENT, "Rotated DEM grids are not supported")
        rc = []
        for x, y in points_ds:
            if ds_crs.is_geographic:
                x = (x - src.bounds.left) % 360.0 + src.bounds.left
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
    """Block discs of radius r (metres) around hazards given in DATASET CRS (x, y, r)."""
    h, w = grid.shape
    n = 0
    for x, y, radius in hazards_ds:
        cell = grid.cell_of(x, y)
        if cell is None:
            continue
        i, j = cell
        ri = int(math.ceil(radius / max(grid.dy_m.mean(), 1e-6)))
        rj = int(math.ceil(radius / max(grid.dx_m[i], 1e-6)))
        for ii in range(max(0, i - ri), min(h, i + ri + 1)):
            for jj in range(max(0, j - rj), min(w, j + rj + 1)):
                dyy = (ii - i) * grid.dy_m.mean()
                dxx = (jj - j) * grid.dx_m[ii]
                if math.hypot(dxx, dyy) <= max(radius, 0.0) or (ii == i and jj == j):
                    if not grid.blocked[ii, jj]:
                        n += 1
                    grid.blocked[ii, jj] = True
    return n


def astar(grid: TerrainGrid, start: tuple[int, int], goal: tuple[int, int], profile: MovementProfile,
          extra_cost: np.ndarray | None = None, allow_unknown: bool | None = None) -> list[tuple[int, int]] | None:
    allow_unknown = profile.allow_unknown_terrain if allow_unknown is None else allow_unknown
    unknown_mult = profile.unknown_multiplier if math.isfinite(profile.unknown_multiplier) else 1.0
    h, w = grid.shape
    z, slope, tri, blocked = grid.z, grid.slope_deg, grid.tri_m, grid.blocked
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
        z_a = z[i, j]
        for di, dj in NEIGHBOURS:
            ni, nj = i + di, j + dj
            if not (0 <= ni < h and 0 <= nj < w):
                continue
            nxt = ni * w + nj
            if closed[nxt] or blocked[ni, nj]:
                continue
            z_b = z[ni, nj]
            unknown = math.isnan(z_a) or math.isnan(z_b)
            if unknown and not allow_unknown:
                continue
            d = grid.step_length(i, j, ni, nj)
            if unknown:
                dz, grade, rough, mult = 0.0, 0.0, 0.0, unknown_mult
            else:
                dz = z_b - z_a
                grade = math.degrees(math.atan2(abs(dz), d))
                sl = slope[ni, nj]
                if grade > profile.max_slope_deg or (not math.isnan(sl) and sl > profile.max_slope_deg):
                    continue
                t = tri[ni, nj]
                rough = 0.0 if math.isnan(t) else min(t / profile.roughness_ref_m, 1.0)
                mult = 1.0
            step = math.hypot(d, dz) * (1.0 + profile.slope_weight * (grade / profile.max_slope_deg) ** 2 + profile.roughness_weight * rough) * mult
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
            else:
                dz = zc - zp
                dist3 += math.hypot(d, dz)
                ascent += max(dz, 0.0)
                descent += max(-dz, 0.0)
                max_grade = max(max_grade, math.degrees(math.atan2(abs(dz), d)))
            dist += d
        profile_pts.append({"distance_m": round(dist, 2), "elevation_m": None if math.isnan(zc) else float(zc)})
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
        "elevation_profile": profile_pts,
    }


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

    route = summarize(grid, primary, ds.latitude_convention, query_lat_conv)
    route["geometry"]["coordinates"][0] = list(points_query[0])
    route["geometry"]["coordinates"][-1] = list(points_query[-1])
    if route["unknown_terrain_fraction"] > profile.max_unknown_fraction:
        raise RoutePlanningError(
            STATUS_INSUFFICIENT,
            f"{route['unknown_terrain_fraction']:.0%} of the best route crosses cells without DEM data (profile limit {profile.max_unknown_fraction:.0%})",
            {"grid": grid.meta},
        )

    grid.meta["window_scale"] = "whole DEM" if scale >= 1e6 else scale
    out: dict[str, Any] = {"status": STATUS_FOUND, "route": route, "grid": grid.meta, "hazard_cells_blocked": blocked_cells}
    if include_return:
        back = _legs(grid, cells[::-1], profile)
        out["return_route"] = summarize(grid, back, ds.latitude_convention, query_lat_conv) if back else None
    if include_alternative:
        extra = np.ones(grid.shape)
        for i, j in primary:
            extra[max(0, i - 1) : i + 2, max(0, j - 1) : j + 2] = 4.0
        alt = _legs(grid, cells, profile, extra_cost=extra)
        if alt:
            overlap = len(set(alt) & set(primary)) / max(len(alt), 1)
            alt_sum = summarize(grid, alt, ds.latitude_convention, query_lat_conv)
            alt_sum["overlap_with_primary"] = overlap
            out["alternative_route"] = alt_sum if overlap < 0.9 else None
            if overlap >= 0.9:
                out["alternative_note"] = "No sufficiently distinct alternative inside the analysed window"
        else:
            out["alternative_route"] = None
    return out
