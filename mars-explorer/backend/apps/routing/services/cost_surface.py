"""Cost surface: hazards on the grid and the cost of one step (the only cost function)."""
from __future__ import annotations

import math

import numpy as np

from apps.routing.profiles import MovementProfile

from .spatial_grid import TerrainGrid
from .terrain_constraints import cell_passable


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
