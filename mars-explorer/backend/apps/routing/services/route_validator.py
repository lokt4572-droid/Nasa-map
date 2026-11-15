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
