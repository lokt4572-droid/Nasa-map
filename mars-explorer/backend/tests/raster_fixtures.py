"""Synthetic test rasters. These are clearly artificial fixtures used only to check the
software arithmetic; they are never presented as Mars measurements."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from services.dem_reader import raster_backend_status

HAS_RASTER = raster_backend_status()["available"]
requires_raster = unittest.skipUnless(HAS_RASTER, "rasterio/GDAL not installed")

# Mars 2000 sphere, planetocentric: the PROJ database entry for this CRS.
MARS_SPHERE = "ESRI:104971"
EARTH_WGS84 = "EPSG:4326"


def write_geotiff(
    path: Path,
    data: np.ndarray,
    *,
    west: float,
    north: float,
    pixel_deg: float,
    crs: str | None = MARS_SPHERE,
    nodata: float | None = -9999.0,
    units: str | None = "m",
) -> Path:
    import rasterio
    from rasterio.transform import from_origin

    bands = data if data.ndim == 3 else data[np.newaxis, ...]
    profile = {
        "driver": "GTiff",
        "width": bands.shape[2],
        "height": bands.shape[1],
        "count": bands.shape[0],
        "dtype": str(bands.dtype),
        "transform": from_origin(west, north, pixel_deg, pixel_deg),
    }
    if crs:
        profile["crs"] = rasterio.crs.CRS.from_user_input(crs)
    if nodata is not None:
        profile["nodata"] = nodata
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(bands)
        if units:
            for i in range(1, bands.shape[0] + 1):
                dst.set_band_unit(i, units)
    return path


class TempDirMixin:
    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        super().tearDown()
