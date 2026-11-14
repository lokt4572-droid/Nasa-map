"""Read-only access to Digital Elevation Model rasters.

The raster backend is GDAL, accessed through the ``rasterio`` package (its wheels bundle
GDAL and PROJ, including the PDS, PDS4, ISIS3 and VICAR planetary drivers). The import is
lazy: the Django application starts and all non-raster endpoints work when rasterio/GDAL
is not installed. In that case :func:`raster_backend_status` reports the problem and the
terrain endpoints answer with ``DEM_BACKEND_UNAVAILABLE``.

Files are always opened read-only. Nothing in this module modifies source data.
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from services.mars_coordinates import transform_point

logger = logging.getLogger("mars.dem")


class RasterBackendUnavailable(RuntimeError):
    pass


class RasterReadError(RuntimeError):
    pass


class PointOutsideRaster(LookupError):
    pass


def _import_rasterio():
    try:
        import rasterio  # noqa: PLC0415

        return rasterio
    except Exception as exc:  # ImportError, or DLL load errors on Windows
        raise RasterBackendUnavailable(
            "Raster backend (rasterio/GDAL) is not available: "
            f"{type(exc).__name__}: {exc}. Install it with "
            "'pip install -r requirements-raster.txt'. See docs/SETUP.md."
        ) from exc


def raster_backend_status() -> dict[str, Any]:
    try:
        rasterio = _import_rasterio()
    except RasterBackendUnavailable as exc:
        return {"available": False, "backend": None, "gdal_version": None, "error": str(exc)}
    drivers: list[str] = []
    try:
        with rasterio.Env() as env:
            all_drivers = env.drivers()
        drivers = sorted(d for d in ("GTiff", "COG", "PDS", "PDS4", "ISIS2", "ISIS3", "VICAR") if d in all_drivers)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not list GDAL drivers: %s", exc)
    return {
        "available": True,
        "backend": f"rasterio {rasterio.__version__}",
        "gdal_version": rasterio.__gdal_version__,
        "planetary_drivers": drivers,
        "error": None,
    }


@dataclass
class RasterInfo:
    path: str
    driver: str
    width: int
    height: int
    band_count: int
    dtype: str
    crs_wkt: str | None
    crs_name: str | None
    crs_is_geographic: bool | None
    crs_axis_units: str | None
    bounds: dict[str, float]
    transform: list[float]
    pixel_size_x: float
    pixel_size_y: float
    nodata: float | None
    band_units: str | None
    scale: float
    offset: float
    tags: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_raster(path: str | Path) -> RasterInfo:
    rasterio = _import_rasterio()
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {p}")
    try:
        with rasterio.open(p, "r") as src:
            crs = src.crs
            crs_name = None
            crs_geo = None
            axis_units = None
            if crs is not None:
                try:
                    from pyproj import CRS

                    pcrs = CRS.from_wkt(crs.to_wkt())
                    crs_name = pcrs.name
                    crs_geo = pcrs.is_geographic
                    axis_units = pcrs.axis_info[0].unit_name if pcrs.axis_info else None
                except Exception as exc:  # keep the raw WKT, do not guess
                    logger.warning("pyproj could not parse CRS of %s: %s", p, exc)
            tags = {str(k): str(v) for k, v in src.tags().items()}
            unit = src.units[0] if src.units and src.units[0] else None
            return RasterInfo(
                path=str(p),
                driver=src.driver,
                width=src.width,
                height=src.height,
                band_count=src.count,
                dtype=src.dtypes[0],
                crs_wkt=crs.to_wkt() if crs else None,
                crs_name=crs_name,
                crs_is_geographic=crs_geo,
                crs_axis_units=axis_units,
                bounds={
                    "left": src.bounds.left,
                    "bottom": src.bounds.bottom,
                    "right": src.bounds.right,
                    "top": src.bounds.top,
                },
                transform=list(src.transform)[:6],
                pixel_size_x=abs(src.transform.a),
                pixel_size_y=abs(src.transform.e),
                nodata=src.nodata,
                band_units=unit,
                scale=float(src.scales[0]) if src.scales else 1.0,
                offset=float(src.offsets[0]) if src.offsets else 0.0,
                tags=tags,
            )
    except RasterBackendUnavailable:
        raise
    except Exception as exc:
        raise RasterReadError(f"GDAL could not read {p}: {exc}") from exc


def _dataset_pyproj_crs(src):
    from pyproj import CRS

    if src.crs is None:
        raise RasterReadError("Raster has no CRS; refusing to sample without georeferencing")
    return CRS.from_wkt(src.crs.to_wkt())


def _locate(src, x: float, y: float, point_crs) -> tuple[int, int, float, float]:
    """Return (row, col, x_ds, y_ds) of the point inside the raster, handling 360° wrap."""
    ds_crs = _dataset_pyproj_crs(src)
    x_ds, y_ds = transform_point(x, y, point_crs, ds_crs)
    candidates = [x_ds]
    if ds_crs.is_geographic:
        candidates += [x_ds + 360.0, x_ds - 360.0]
    b = src.bounds
    for cx in candidates:
        if b.left <= cx < b.right and b.bottom < y_ds <= b.top:
            row, col = src.index(cx, y_ds)
            if 0 <= row < src.height and 0 <= col < src.width:
                return row, col, cx, y_ds
    raise PointOutsideRaster(f"Point ({x}, {y}) is outside the raster extent")


@dataclass
class PointSample:
    value: float | None  # physical value after scale/offset; None when nodata
    is_nodata: bool
    row: int
    col: int
    x_dataset: float
    y_dataset: float
    units: str | None


def sample_point(path: str | Path, x: float, y: float, point_crs) -> PointSample:
    rasterio = _import_rasterio()
    from rasterio.windows import Window

    with rasterio.open(Path(path), "r") as src:
        row, col, xd, yd = _locate(src, x, y, point_crs)
        raw = src.read(1, window=Window(col, row, 1, 1), masked=True)
        units = src.units[0] if src.units and src.units[0] else None
        if np.ma.is_masked(raw):
            return PointSample(None, True, row, col, xd, yd, units)
        val = float(raw[0, 0])
        if not math.isfinite(val):
            return PointSample(None, True, row, col, xd, yd, units)
        scale = float(src.scales[0]) if src.scales else 1.0
        offset = float(src.offsets[0]) if src.offsets else 0.0
        return PointSample(val * scale + offset, False, row, col, xd, yd, units)


@dataclass
class WindowSample:
    values: np.ndarray  # float64, NaN where nodata or outside raster
    center_row: int
    center_col: int
    x_dataset: float
    y_dataset: float
    pixel_size_x: float
    pixel_size_y: float
    crs: Any  # pyproj.CRS of the dataset
    units: str | None


def read_window(path: str | Path, x: float, y: float, point_crs, half_size: int = 1) -> WindowSample:
    """Read a (2*half_size+1)^2 window centred on the point. Cells outside -> NaN."""
    rasterio = _import_rasterio()
    from rasterio.windows import Window

    if half_size < 1:
        raise ValueError("half_size must be >= 1")
    with rasterio.open(Path(path), "r") as src:
        row, col, xd, yd = _locate(src, x, y, point_crs)
        size = 2 * half_size + 1
        win = Window(col - half_size, row - half_size, size, size)
        data = src.read(1, window=win, boundless=True, masked=True, fill_value=src.nodata if src.nodata is not None else 0)
        arr = np.ma.filled(data.astype("float64"), np.nan)
        # boundless read: mark cells outside the raster as NaN explicitly
        for r in range(size):
            for c in range(size):
                rr, cc = row - half_size + r, col - half_size + c
                if not (0 <= rr < src.height and 0 <= cc < src.width):
                    arr[r, c] = np.nan
        scale = float(src.scales[0]) if src.scales else 1.0
        offset = float(src.offsets[0]) if src.offsets else 0.0
        arr = arr * scale + offset
        return WindowSample(
            values=arr,
            center_row=row,
            center_col=col,
            x_dataset=xd,
            y_dataset=yd,
            pixel_size_x=abs(src.transform.a),
            pixel_size_y=abs(src.transform.e),
            crs=_dataset_pyproj_crs(src),
            units=src.units[0] if src.units and src.units[0] else None,
        )
