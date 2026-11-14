"""Local terrain patch (Phase 4): a square-ish elevation grid around a point, read from a
registered, validated DEM — never synthesised.

Rules:
- The grid is never finer than the DEM: the number of cells across the patch is capped by the
  DEM's native cell count (``2 * radius / native resolution``), so no detail is invented by
  upsampling. If fewer than MIN_NATIVE_CELLS native cells fall across the patch, the request is
  refused with the smallest radius that would work (DEM_TOO_COARSE_FOR_PATCH).
- NoData / outside-raster cells stay NaN and are reported as a fraction; they are never filled.
- Elevations are returned as zlib-compressed little-endian float32 (row-major, north to south,
  west to east), base64 encoded; NaN marks NoData.
"""
from __future__ import annotations

import base64
import math
import zlib

import numpy as np

from services import raster_render
from services.planet_registry import get_planet

MIN_NATIVE_CELLS = 4
RADIUS_LIMITS_M = (100.0, 500_000.0)
DIMENSION_LIMITS = (16, 512)
POLE_LIMIT_DEG = 89.9


class PatchError(ValueError):
    def __init__(self, message: str, code: str, details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def patch_bbox(lon: float, lat: float, radius_m: float, body_radius_m: float) -> tuple[float, float, float, float]:
    """Lon/lat box covering +-radius around the point on a sphere of the body's radius."""
    dlat = math.degrees(radius_m / body_radius_m)
    south, north = lat - dlat, lat + dlat
    if north > POLE_LIMIT_DEG or south < -POLE_LIMIT_DEG:
        raise PatchError(
            "Patch would cross a pole; equirectangular patches are not supported there",
            "PATCH_CROSSES_POLE",
            {"max_radius_m": round(math.radians(POLE_LIMIT_DEG - abs(lat)) * body_radius_m, 1)},
        )
    dlon = dlat / max(math.cos(math.radians(lat)), 1e-6)
    return lon - dlon, south, lon + dlon, north


def grid_dimensions(radius_m: float, native_res_m: float, max_dimension: int) -> tuple[int, int]:
    """(cells across the patch at native resolution, grid side used)."""
    native_cells = int(math.floor(2 * radius_m / native_res_m))
    return native_cells, max(2, min(max_dimension, native_cells))


def build_patch(ds, lon: float, lat: float, radius_m: float, max_dimension: int, query_crs, lat_convention: str) -> dict:
    planet = get_planet(ds.planet)
    native = float(ds.resolution_meters)
    native_cells, side = grid_dimensions(radius_m, native, max_dimension)
    if native_cells < MIN_NATIVE_CELLS:
        raise PatchError(
            f"{ds.name} has {native:.0f} m cells: a {radius_m:.0f} m radius covers only {native_cells} cell(s). "
            f"Use a radius of at least {math.ceil(MIN_NATIVE_CELLS * native / 2)} m or a finer DEM.",
            "DEM_TOO_COARSE_FOR_PATCH",
            {"native_resolution_m": native, "min_radius_m": math.ceil(MIN_NATIVE_CELLS * native / 2)},
        )
    west, south, east, north = patch_bbox(lon, lat, radius_m, planet.radius_equatorial_m)
    z = raster_render.sample_grid(ds, (west, south, east, north), side, side, query_crs, lat_convention)
    valid = np.isfinite(z)
    nodata_fraction = float(1 - valid.mean())
    if not valid.any():
        raise PatchError("The DEM has no valid values in this patch", "DEM_NO_VALID_CELLS", {"nodata_fraction": 1.0})
    body_r = planet.radius_equatorial_m
    cell_y = math.radians((north - south) / side) * body_r
    cell_x = math.radians((east - west) / side) * body_r * math.cos(math.radians(lat))
    raw = z.astype("<f4").tobytes(order="C")
    return {
        "planet": ds.planet,
        "center": {"lon_east_deg": lon, "lat_deg": lat},
        "radius_m": radius_m,
        "bbox": {"west": west, "south": south, "east": east, "north": north},
        "grid": {
            "width": side,
            "height": side,
            "cell_size_x_m": round(cell_x, 3),
            "cell_size_y_m": round(cell_y, 3),
            "native_cells_across": native_cells,
            "resampling": "nearest DEM cell (no interpolation, never finer than the DEM)",
        },
        "dataset": {
            "id": ds.id,
            "name": ds.name,
            "instrument": ds.instrument,
            "product_id": ds.product_id,
            "source": ds.source,
            "license": ds.license,
            "native_resolution_m": native,
            "crs_name": ds.crs_name,
            "latitude_convention": ds.latitude_convention,
            "vertical_datum": ds.vertical_datum,
            "units": ds.units,
        },
        "statistics": {
            "min": float(np.nanmin(z)),
            "max": float(np.nanmax(z)),
            "mean": float(np.nanmean(z)),
            "relief": float(np.nanmax(z) - np.nanmin(z)),
            "nodata_fraction": round(nodata_fraction, 6),
        },
        "encoding": "zlib+base64; float32 little-endian; row-major north->south, west->east; NaN = NoData",
        "elevation": base64.b64encode(zlib.compress(raw, 6)).decode("ascii"),
        "suitability": (
            "REGIONAL_OVERVIEW_ONLY" if native > 100 else "SITE_RECONNAISSANCE" if native > 2 else "DETAILED_STUDY"
        ),
        "notes": [
            "Vertical exaggeration in the viewer is a visual aid only; values are true elevations.",
            "NoData cells are left empty, never interpolated.",
        ],
    }


def decode_elevation(b64: str, width: int, height: int) -> np.ndarray:
    return np.frombuffer(zlib.decompress(base64.b64decode(b64)), dtype="<f4").reshape(height, width)
