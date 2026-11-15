"""Line-of-sight checks, path simplification and final validation of a computed route."""
from __future__ import annotations

import math

from apps.routing.profiles import MovementProfile

from .spatial_grid import TerrainGrid
from .terrain_constraints import cell_passable


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


def validate_route(grid: TerrainGrid, cells: list[tuple[int, int]], profile: MovementProfile,
                   simplified: list[tuple[int, int]] | None = None) -> dict:
    """Independent re-check of a finished route against the grid it was planned on.

    A* already enforces these rules; this is a second, separate pass so that a bug in the
    search or in smoothing cannot return a route that breaks a hard constraint."""
    from .cost_surface import step_cost  # local import: cost_surface does not depend on this module

    problems: list[str] = []
    allow = profile.allow_unknown_terrain
    mult = profile.unknown_multiplier if math.isfinite(profile.unknown_multiplier) else 1.0
    if not cells:
        return {"valid": False, "problems": ["empty route"], "checked_steps": 0}
    h, w = grid.shape
    for k, (i, j) in enumerate(cells):
        if not (0 <= i < h and 0 <= j < w):
            problems.append(f"cell {k} outside the grid")
        elif grid.blocked[i, j]:
            problems.append(f"cell {k} inside a hazard area")
        elif math.isnan(grid.z[i, j]) and not allow:
            problems.append(f"cell {k} has no DEM value")
    if not problems:
        for k, (a, b) in enumerate(zip(cells[:-1], cells[1:])):
            di, dj = abs(a[0] - b[0]), abs(a[1] - b[1])
            if max(di, dj) != 1:
                problems.append(f"step {k} is not between neighbouring cells")
            elif profile.connectivity == 4 and di + dj != 1:
                problems.append(f"step {k} is diagonal but the profile uses 4-connectivity")
            elif step_cost(grid, *a, *b, profile, allow, mult) is None:
                problems.append(f"step {k} breaks a hard constraint (slope, hazard, NoData or corner cutting)")
            if len(problems) >= 10:
                break
    if simplified and not problems:
        idx = {c: n for n, c in enumerate(cells)}
        for k, (a, b) in enumerate(zip(simplified[:-1], simplified[1:])):
            # A straightened segment (more than one cell apart on the path) must be clear.
            if abs(idx.get(b, 0) - idx.get(a, 0)) > 1 and not segment_clear(grid, a, b, profile):
                problems.append(f"simplified segment {k} crosses an obstacle or NoData")
    return {"valid": not problems, "problems": problems, "checked_steps": max(0, len(cells) - 1)}


MAX_SOURCE_SAMPLES = 20_000


def densify_lonlat(coords: list[list[float]], spacing_m: float, geod) -> list[tuple[float, float]]:
    """Points along the route at about ``spacing_m`` (geodesic), seam-aware, start and end included."""
    out: list[tuple[float, float]] = []
    for (lo1, la1), (lo2, la2) in zip(coords[:-1], coords[1:]):
        d = geod.inv(lo1, la1, lo2, la2)[2]
        n = max(1, int(math.ceil(d / max(spacing_m, 1e-6))))
        mids = geod.npts(lo1, la1, lo2, la2, n - 1) if n > 1 else []
        out.append((lo1, la1))
        out.extend((((x + 180.0) % 360.0) - 180.0, y) for x, y in mids)
    out.append(tuple(coords[-1]))
    return out


def validate_on_source(ds, coords: list[list[float]], query_crs, query_lat_conv: str, profile: MovementProfile,
                       hazards_query: list[tuple[float, float, float]] = ()) -> dict:
    """Second, independent check of the FINAL route line on the original DEM (not the search grid).

    Samples the DEM along the displayed geometry at its native spacing, then checks NoData, the
    grade of every step between samples against the profile limit, and hazard buffers; returns
    metrics recomputed from these samples. Grades over one native cell are steeper than slopes
    averaged over coarser cells, so this check is stricter than the search."""
    import numpy as np
    from pyproj import CRS, Geod

    from services import raster_render

    ell = CRS.from_wkt(ds.crs).ellipsoid
    geod = Geod(a=ell.semi_major_metre, b=ell.semi_minor_metre)
    native = float(ds.resolution_meters or 0.0) or 100.0
    total = sum(geod.inv(a[0], a[1], b[0], b[1])[2] for a, b in zip(coords[:-1], coords[1:]))
    spacing = max(native, total / MAX_SOURCE_SAMPLES)
    pts = densify_lonlat(coords, spacing, geod)
    lons = np.array([p[0] for p in pts])
    lats = np.array([p[1] for p in pts])
    budget = 4096
    z = raster_render.sample_lonlat(ds, lons, lats, query_crs, query_lat_conv, max_read=(budget, budget))
    step_d = np.asarray(geod.inv(lons[:-1], lats[:-1], lons[1:], lats[1:])[2], dtype="float64") if len(pts) > 1 else np.zeros(0)
    dz = np.diff(z)
    ok_step = np.isfinite(dz) & (step_d > 0)
    grades = np.degrees(np.arctan2(np.abs(dz[ok_step]), step_d[ok_step])) if ok_step.any() else np.zeros(0)
    nodata = ~np.isfinite(z)
    problems: list[str] = []
    if nodata.any() and not profile.allow_unknown_terrain:
        problems.append(f"{int(nodata.sum())} of {len(z)} samples have no DEM value")
    steep = int((grades > profile.max_slope_deg).sum())
    if steep:
        problems.append(f"{steep} step(s) steeper than {profile.max_slope_deg:g} deg (max {grades.max():.1f} deg) on the source DEM")
    for hlon, hlat, r in hazards_query:
        if r <= 0:
            continue
        dmin = float(np.min(geod.inv(lons, lats, np.full_like(lons, hlon), np.full_like(lats, hlat))[2]))
        if dmin < r:
            problems.append(f"passes {dmin:.0f} m from a hazard (buffered radius {r:.0f} m)")
    valid_dz = dz[np.isfinite(dz)]
    dist = float(step_d.sum())
    cum = np.concatenate([[0.0], np.cumsum(step_d)])
    idx = np.linspace(0, len(z) - 1, min(len(z), 500)).round().astype(int)
    profile_pts = [{"distance_m": round(float(cum[i]), 2), "elevation_m": None if not np.isfinite(z[i]) else round(float(z[i]), 3)} for i in idx]
    d3 = float(np.hypot(step_d[np.isfinite(dz)], dz[np.isfinite(dz)]).sum() + step_d[~np.isfinite(dz)].sum())
    return {
        "status": "VALIDATED" if not problems else "INVALID_ROUTE",
        "problems": problems,
        "source": {"dataset": ds.name, "native_resolution_m": ds.resolution_meters, "sample_spacing_m": round(spacing, 3),
                   "samples": int(len(z)), "read_budget_px": budget},
        "metrics": {
            "distance_m": dist, "distance_3d_m": d3,
            "total_ascent_m": float(valid_dz[valid_dz > 0].sum()), "total_descent_m": float(-valid_dz[valid_dz < 0].sum()),
            "maximum_step_grade_deg": float(grades.max()) if grades.size else 0.0,
            "average_step_grade_deg": float(np.average(grades, weights=step_d[ok_step])) if grades.size else 0.0,
            "nodata_pct": round(100 * float(nodata.mean()), 3),
        },
        "elevation_profile": profile_pts,
    }
