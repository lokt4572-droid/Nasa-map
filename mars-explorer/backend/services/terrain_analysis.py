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
    # GDAL/PROJ report e.g. "metre", "Metre" (PDS4 MOLA) or "meter": compare case-insensitively.
    if (units or "").lower() not in ("metre", "meter"):
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


# ===========================================================================
# v0.2 — dataset-level analysis with a uniform result schema.
#
# Every metric is returned as:
#   {metric, value, units, dataset_id, source, resolution_m, crs, nodata_status,
#    processing_method, window, latitude_handling?}
# value is None (never 0) when the data do not allow the computation.

METHODS = {
    "elevation": "Nearest DEM cell, no interpolation; value after the file's scale/offset.",
    "slope": "Horn (1981) 3x3 finite differences; cell size in metres from the DEM CRS ellipsoid at the cell latitude. Degrees from horizontal.",
    "aspect": "Horn (1981) 3x3. Azimuth of steepest DESCENT, degrees clockwise from north (0 = north-facing, 90 = east). None on flat cells.",
    "roughness": "Terrain Ruggedness Index, Riley et al. (1999): sqrt(sum((z_i - z_centre)^2)) over the 8 neighbours of a 3x3 window, metres.",
    "local_relief": "Maximum minus minimum elevation inside a (2r+1)x(2r+1) cell window, metres.",
    "nodata_coverage": "Fraction of nodata/NaN cells inside the (2r+1)x(2r+1) window around the point.",
    "elevation_difference": "Elevation at point B minus elevation at point A (nearest cells), metres.",
}

NODATA_OK = "OK"
NODATA_PARTIAL = "PARTIAL_NODATA"
NODATA_ALL = "NODATA"
NOT_AVAILABLE = "NOT_AVAILABLE"


def _result(metric, value, units, ds, nodata_status, window=None, **extra):
    return {
        "metric": metric,
        "value": value,
        "units": units,
        "dataset_id": ds.id,
        "dataset": ds.name,
        "source": ds.source or ds.instrument or ds.name,
        "resolution_m": ds.resolution_meters,
        "crs": ds.crs_name,
        "vertical_datum": ds.vertical_datum,
        "nodata_status": nodata_status,
        "processing_method": METHODS[metric],
        "window": window,
        **extra,
    }


def _nodata_status(window: np.ndarray) -> str:
    n = int(np.isnan(window).sum())
    if n == 0:
        return NODATA_OK
    return NODATA_ALL if n == window.size else NODATA_PARTIAL


def analyze_window(ds, w, metric: str, radius: int = 1) -> dict:
    """Compute one metric from a dem_reader.WindowSample read around the point."""

    vals = w.values
    centre = vals[vals.shape[0] // 2, vals.shape[1] // 2]
    size = f"{vals.shape[0]}x{vals.shape[1]} cells"
    if metric == "elevation":
        v = None if np.isnan(centre) else float(centre)
        return _result(metric, v, ds.units or "m", ds, NODATA_OK if v is not None else NODATA_ALL, "1 cell")
    if metric == "nodata_coverage":
        return _result(metric, nodata_fraction(vals), "fraction", ds, _nodata_status(vals), size)
    if metric == "local_relief":
        valid = vals[~np.isnan(vals)]
        v = float(valid.max() - valid.min()) if valid.size >= 2 else None
        return _result(metric, v, "m", ds, _nodata_status(vals), size)
    c = vals.shape[0] // 2
    w3 = vals[c - 1 : c + 2, c - 1 : c + 2]
    if metric == "roughness":
        v = terrain_ruggedness_index(w3)
        return _result(metric, v, "m", ds, _nodata_status(w3), "3x3 cells")
    if metric in ("slope", "aspect"):
        cs = cell_size_m(w.pixel_size_x, w.pixel_size_y, w.crs, w.y_dataset if w.crs.is_geographic else None)
        r = horn_slope_aspect(w3, cs.dx_m, cs.dy_m)
        v = r.slope_deg if metric == "slope" else r.aspect_deg
        extra = {"cell_size_m": {"dx": cs.dx_m, "dy": cs.dy_m}}
        if metric == "aspect" and r.slope_deg == 0.0:
            extra["note"] = "flat: aspect undefined"
        return _result(metric, v, "degrees", ds, _nodata_status(w3), "3x3 cells", **extra)
    raise ValueError(f"Unknown metric {metric!r}")


def area_statistics(ds, bbox_dataset: tuple[float, float, float, float], max_cells: int = 1_000_000) -> dict:
    """Elevation statistics inside a bbox given in the DATASET CRS (left, bottom, right, top).

    Only the window covering the bbox is read; it is decimated to at most max_cells."""
    from services import remote_raster, dem_reader

    rasterio = dem_reader._import_rasterio()
    from rasterio.windows import from_bounds

    with remote_raster.open_raster(ds.file_path) as src:
        win = from_bounds(*bbox_dataset, transform=src.transform).round_offsets().round_lengths()
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        if win.width < 1 or win.height < 1:
            raise dem_reader.PointOutsideRaster("bbox does not overlap the DEM")
        factor = max(1, int(np.ceil(np.sqrt(win.width * win.height / max_cells))))
        shape = (max(1, int(win.height) // factor), max(1, int(win.width) // factor))
        data = src.read(1, window=win, out_shape=shape, masked=True)
        scale = float(src.scales[0]) if src.scales else 1.0
        offset = float(src.offsets[0]) if src.offsets else 0.0
    arr = np.ma.filled(data.astype("float64"), np.nan) * scale + offset
    valid = arr[~np.isnan(arr)]
    stats = {
        "cells_read": int(arr.size),
        "decimation_factor": factor,
        "nodata_fraction": float(np.isnan(arr).mean()) if arr.size else 1.0,
    }
    if valid.size:
        stats.update(min=float(valid.min()), max=float(valid.max()), mean=float(valid.mean()), local_relief=float(valid.max() - valid.min()))
    return _result("local_relief", stats.get("local_relief"), "m", ds, _nodata_status(arr), f"bbox, {arr.shape[0]}x{arr.shape[1]} cells", statistics=stats)
