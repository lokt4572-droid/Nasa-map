"""DEM-derived hazard candidates and the hazard exposure of a route.

Everything here is computed from elevation values. The results are MODEL_ESTIMATED: a slope
or roughness threshold on a DEM is an inference about the terrain at the DEM's resolution, not
an observation of a rock, a crater or loose ground. Nothing smaller than about two DEM cells
can appear, and nothing is ever derived from image brightness (a dark pixel is not a crater).
"""
from __future__ import annotations

import math

import numpy as np

from .spatial_grid import TerrainGrid

CATEGORIES = ("STEEP_SLOPE", "CRATER", "BOULDER_FIELD", "ROUGH_TERRAIN", "SAND_DUNE", "UNKNOWN_SURFACE", "MISSING_DATA")
OBSERVATION_CLASSES = ("OBSERVED", "INFERRED", "USER_REPORTED", "MODEL_ESTIMATED", "UNKNOWN")

# What a DEM threshold can and cannot say (shown with the results).
DERIVABLE = {
    "STEEP_SLOPE": "cell slope above the threshold (central differences on the DEM)",
    "ROUGH_TERRAIN": "Terrain Ruggedness Index above the threshold",
    "MISSING_DATA": "cells without a DEM value",
}
NOT_DERIVABLE = {
    "CRATER": "needs a crater catalogue or a validated detector; not inferred from slope or brightness",
    "BOULDER_FIELD": "boulders are smaller than DEM cells; needs metre-scale imagery and a validated detector",
    "SAND_DUNE": "needs imagery interpretation or a validated classifier",
    "UNKNOWN_SURFACE": "surface properties (dust, loose regolith) are not measurable from a DEM",
}


def _regions(mask: np.ndarray, max_regions: int) -> list[np.ndarray]:
    """Connected regions (8-neighbourhood) of a boolean mask, largest first."""
    from scipy import ndimage

    labels, n = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    if n == 0:
        return []
    sizes = ndimage.sum(mask, labels, index=np.arange(1, n + 1))
    order = np.argsort(sizes)[::-1][:max_regions]
    return [np.argwhere(labels == k + 1) for k in order]


def derive_hazards(grid: TerrainGrid, slope_limit_deg: float, roughness_limit_m: float | None = None,
                   max_regions: int = 50, min_cells: int = 1) -> dict:
    """Hazard candidates on a routing grid: connected areas above the slope / roughness limits
    and areas without data. Coordinates are returned in the grid's dataset CRS (cell centres)."""
    cell_m = float(max(grid.dx_m.max(), grid.dy_m.mean()))
    out: list[dict] = []

    def add(mask: np.ndarray, category: str, layer: np.ndarray | None, unit: str, limit: float | None):
        for cells in _regions(mask, max_regions):
            if len(cells) < min_cells:
                continue
            ci, cj = cells.mean(axis=0)
            i, j = int(round(ci)), int(round(cj))
            x, y = grid.xy_of(i, j)
            # Radius of the circle with the same area as the region (never below half a cell).
            area = float(sum(grid.dx_m[c[0]] for c in cells) * grid.dy_m.mean())
            vals = layer[cells[:, 0], cells[:, 1]] if layer is not None else None
            out.append({
                "category": category,
                "observation_class": "MODEL_ESTIMATED",
                "verification": "UNVERIFIED",
                "method": DERIVABLE[category],
                "x": float(x), "y": float(y),
                "cells": int(len(cells)),
                "area_m2": area,
                "radius_m": max(math.sqrt(area / math.pi), cell_m / 2),
                "threshold": limit, "unit": unit,
                "max_value": float(np.nanmax(vals)) if vals is not None and np.isfinite(vals).any() else None,
                "smallest_resolvable_feature_m": round(2 * cell_m, 1),
            })

    add(np.nan_to_num(grid.slope_deg, nan=0.0) > slope_limit_deg, "STEEP_SLOPE", grid.slope_deg, "deg", slope_limit_deg)
    if roughness_limit_m is not None:
        add(np.nan_to_num(grid.tri_m, nan=0.0) > roughness_limit_m, "ROUGH_TERRAIN", grid.tri_m, "m", roughness_limit_m)
    add(np.isnan(grid.z), "MISSING_DATA", None, "", None)
    return {
        "hazards": out,
        "grid_cell_m": cell_m,
        "derivable_from_dem": DERIVABLE,
        "not_derivable_from_dem": NOT_DERIVABLE,
        "note": ("Candidates are thresholds on the DEM at its own resolution (MODEL_ESTIMATED, UNVERIFIED). "
                 "They are not stored and do not block routes unless a person saves and confirms them. "
                 "Features smaller than about two DEM cells cannot be detected; subsurface or surface-strength "
                 "hazards cannot be detected at all."),
    }


def hazard_exposure_m(grid: TerrainGrid, cells: list[tuple[int, int]]) -> float:
    """Distance of a route that lies inside a hazard's proximity zone (between its buffered
    radius and twice that radius). 0 when no hazard is near or none is known."""
    if grid.proximity is None:
        return 0.0
    total = 0.0
    for (i, j), (ni, nj) in zip(cells[:-1], cells[1:]):
        if grid.proximity[ni, nj] > 0 or grid.proximity[i, j] > 0:
            total += grid.step_length(i, j, ni, nj)
    return total
