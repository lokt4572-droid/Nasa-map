"""Hard constraints: what may never be entered, whatever the cost."""
from __future__ import annotations

import math

from apps.routing.profiles import MovementProfile

from .spatial_grid import TerrainGrid


def cell_passable(grid: TerrainGrid, i: int, j: int, profile: MovementProfile, allow_unknown: bool) -> bool:
    """A cell may be entered: inside the grid, not in a hazard disc, has a DEM value (unless the
    policy allows unknown terrain) and its slope does not exceed the profile limit."""
    h, w = grid.shape
    if not (0 <= i < h and 0 <= j < w) or grid.blocked[i, j]:
        return False
    if math.isnan(grid.z[i, j]):
        return allow_unknown
    sl = grid.slope_deg[i, j]
    if not (math.isnan(sl) or sl <= profile.max_slope_deg):
        return False
    if profile.max_roughness_m is not None:
        t = grid.tri_m[i, j]
        if not math.isnan(t) and t > profile.max_roughness_m:
            return False
    if profile.max_local_relief_m is not None and grid.relief_m is not None:
        r = grid.relief_m[i, j]
        if not math.isnan(r) and r > profile.max_local_relief_m:
            return False
    return True


def blocking_reasons(grid: TerrainGrid, profile: MovementProfile) -> dict[str, int]:
    """How many grid cells each hard constraint blocks (for the data-quality report)."""
    import numpy as np

    nodata = np.isnan(grid.z)
    out = {
        "hazard": int(grid.blocked.sum()),
        "nodata": int(nodata.sum()) if not profile.allow_unknown_terrain else 0,
        "slope": int((np.nan_to_num(grid.slope_deg, nan=0.0) > profile.max_slope_deg).sum()),
    }
    if profile.max_roughness_m is not None:
        out["roughness"] = int((np.nan_to_num(grid.tri_m, nan=0.0) > profile.max_roughness_m).sum())
    if profile.max_local_relief_m is not None and grid.relief_m is not None:
        out["local_relief"] = int((np.nan_to_num(grid.relief_m, nan=0.0) > profile.max_local_relief_m).sum())
    return out
