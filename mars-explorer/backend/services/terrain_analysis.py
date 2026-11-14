"""Terrain metrics computed from numeric DEM elevations (never from RGB imagery).

All functions take elevation arrays in metres and horizontal cell sizes in metres. For
geographic (degree-based) DEMs the cell size in metres depends on latitude: the
east-west size shrinks with cos(latitude). :func:`cell_size_m` performs that conversion
using the DEM's own ellipsoid/sphere.

Slope and aspect use Horn's (1981) 3x3 finite-difference method, the same formulation
as ``gdaldem slope/aspect``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from services.mars_coordinates import meridional_radius_m, prime_vertical_radius_m


@dataclass(frozen=True)
class CellSize:
    dx_m: float  # east-west
    dy_m: float  # north-south
    method: str


def cell_size_m(pixel_size_x: float, pixel_size_y: float, crs, latitude_deg: float | None = None) -> CellSize:
    """Horizontal cell size in metres for a DEM pixel.

    * Projected CRS with metre axes: pixel sizes are already metres.
    * Geographic CRS: convert degrees using the radii of curvature of the CRS ellipsoid
      at ``latitude_deg`` (latitude in that CRS):
          dx = Δλ[rad] · N(φ) · cos φ,  dy = Δφ[rad] · M(φ)
    """
    if crs.is_geographic:
        if latitude_deg is None:
            raise ValueError("latitude is required for geographic DEMs")
        ell = crs.ellipsoid
        a = ell.semi_major_metre
        b = ell.semi_minor_metre
        e2 = 1.0 - (b * b) / (a * a)
        n = prime_vertical_radius_m(latitude_deg, a=a, e2=e2)
        m = meridional_radius_m(latitude_deg, a=a, e2=e2)
        dx = math.radians(pixel_size_x) * n * math.cos(math.radians(latitude_deg))
        dy = math.radians(pixel_size_y) * m
        if dx <= 0:
            raise ValueError("east-west cell size collapses to zero at the pole")
        return CellSize(dx, dy, "geographic: ellipsoid radii of curvature at latitude")
    units = crs.axis_info[0].unit_name if crs.axis_info else None
    if units not in ("metre", "meter"):
        raise ValueError(f"Unsupported projected axis unit {units!r}; expected metre")
    return CellSize(pixel_size_x, pixel_size_y, "projected: metre axes")


@dataclass(frozen=True)
class SlopeResult:
    slope_deg: float | None
    aspect_deg: float | None  # clockwise from north, direction of steepest descent; None when flat
    dz_dx: float | None
    dz_dy: float | None


def horn_slope_aspect(window: np.ndarray, dx_m: float, dy_m: float) -> SlopeResult:
    """Slope/aspect at the centre of a 3x3 window (row 0 = north, col 0 = west)."""
    w = np.asarray(window, dtype="float64")
    if w.shape != (3, 3):
        raise ValueError("Horn's method needs a 3x3 window")
    if np.isnan(w).any():
        return SlopeResult(None, None, None, None)
    z1, z2, z3 = w[0]
    z4, _, z6 = w[1]
    z7, z8, z9 = w[2]
    dz_dx = ((z3 + 2 * z6 + z9) - (z1 + 2 * z4 + z7)) / (8.0 * dx_m)  # + toward east
    dz_dy = ((z1 + 2 * z2 + z3) - (z7 + 2 * z8 + z9)) / (8.0 * dy_m)  # + toward north
    grad = math.hypot(dz_dx, dz_dy)
    slope = math.degrees(math.atan(grad))
    if grad == 0.0:
        return SlopeResult(slope, None, dz_dx, dz_dy)
    # Downslope direction is -gradient. Azimuth clockwise from north: atan2(east, north).
    aspect = (math.degrees(math.atan2(-dz_dx, -dz_dy)) + 360.0) % 360.0
    return SlopeResult(slope, aspect, dz_dx, dz_dy)


def nodata_fraction(window: np.ndarray) -> float:
    w = np.asarray(window, dtype="float64")
    return float(np.isnan(w).sum()) / float(w.size)


def terrain_ruggedness_index(window: np.ndarray) -> float | None:
    """Riley et al. (1999) TRI: sqrt of summed squared differences to the centre cell
    for a 3x3 window (metres). Returns None if any cell is nodata."""
    w = np.asarray(window, dtype="float64")
    if w.shape != (3, 3) or np.isnan(w).any():
        return None
    centre = w[1, 1]
    return float(math.sqrt(float(((w - centre) ** 2).sum())))


def elevation_std(window: np.ndarray) -> float | None:
    """Standard deviation of valid elevations in the window (a simple roughness proxy)."""
    w = np.asarray(window, dtype="float64")
    valid = w[~np.isnan(w)]
    if valid.size < 2:
        return None
    return float(valid.std(ddof=0))


def elevation_difference(z_from: float | None, z_to: float | None) -> float | None:
    if z_from is None or z_to is None:
        return None
    return float(z_to - z_from)
