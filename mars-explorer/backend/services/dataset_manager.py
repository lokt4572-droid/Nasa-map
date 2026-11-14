"""Registration, validation and lookup of local scientific datasets.

Validation rules (a DEM is VALID only if all hold):
  * file exists and GDAL can open it;
  * the raster has a CRS that pyproj can parse and that describes Mars;
  * width/height > 0 and the first band is numeric;
  * elevation units are known (from the file or given explicitly by the operator);
Warnings (do not invalidate, but are stored and shown):
  * no nodata value declared;
  * vertical datum not given;
  * multi-band raster (band 1 is used).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from services import dem_reader
from services.mars_coordinates import (
    LatitudeConvention,
    LongitudeConvention,
    adapt_latitude,
    is_mars_crs,
    latitude_convention_for_crs,
    transform_point,
)
from services.terrain_analysis import cell_size_m

logger = logging.getLogger("mars.datasets")

METRE_UNITS = {"m", "metre", "meter", "metres", "meters"}
NUMERIC_DTYPES = {"int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64", "float32", "float64"}


class DatasetValidationError(ValueError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings or []


@dataclass
class ValidationReport:
    info: dem_reader.RasterInfo
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    units: str | None = None
    latitude_convention: str = LatitudeConvention.UNKNOWN
    longitude_convention: str = LongitudeConvention.UNKNOWN
    resolution_meters: float | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


def sha256_file(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return "sha256:" + h.hexdigest()


def validate_dem(path: Path, units_override: str | None = None, data_type: str = "DEM") -> ValidationReport:
    """Inspect a raster and decide whether it can be used as a numeric DEM."""
    from pyproj import CRS

    info = dem_reader.inspect_raster(path)
    report = ValidationReport(info=info)

    if info.width <= 0 or info.height <= 0:
        report.errors.append(f"Invalid raster size {info.width}x{info.height}")
    if info.dtype not in NUMERIC_DTYPES:
        report.errors.append(f"Band 1 data type {info.dtype!r} is not numeric")
    if info.band_count > 1:
        report.warnings.append(f"Raster has {info.band_count} bands; band 1 is used as elevation")
    if data_type == "DEM" and info.dtype == "uint8" and info.band_count >= 3:
        report.errors.append("Looks like an RGB image (3+ uint8 bands), not a DEM. RGB pixels are not elevations.")

    if not info.crs_wkt:
        report.errors.append(
            "No CRS found in the file metadata. Provide a correctly georeferenced product "
            "(e.g. the PDS4 label next to the image, or a GeoTIFF with Mars CRS); the "
            "importer will not guess a CRS."
        )
        crs = None
    else:
        try:
            crs = CRS.from_wkt(info.crs_wkt)
        except Exception as exc:
            crs = None
            report.errors.append(f"CRS cannot be parsed by PROJ: {exc}")
    if crs is not None:
        if not is_mars_crs(crs):
            report.errors.append(f"CRS {crs.name!r} does not describe Mars (semi-major axis {crs.ellipsoid.semi_major_metre if crs.ellipsoid else '?'} m)")
        else:
            report.latitude_convention = latitude_convention_for_crs(crs)
            if crs.is_geographic:
                left, right = info.bounds["left"], info.bounds["right"]
                if left >= 0 and right > 180:
                    report.longitude_convention = LongitudeConvention.EAST_POSITIVE_360
                elif left >= -180.0001 and right <= 180.0001:
                    report.longitude_convention = LongitudeConvention.EAST_POSITIVE_180
            else:
                # Projected: longitude convention is defined by the projection (east-positive in PROJ)
                report.longitude_convention = LongitudeConvention.EAST_POSITIVE_180
            try:
                lat_mid = (info.bounds["bottom"] + info.bounds["top"]) / 2.0 if crs.is_geographic else 0.0
                cs = cell_size_m(info.pixel_size_x, info.pixel_size_y, crs, lat_mid if crs.is_geographic else None)
                # Report the N-S spacing for geographic grids (constant), the x spacing for projected ones.
                report.resolution_meters = round(cs.dy_m if crs.is_geographic else cs.dx_m, 6)
            except ValueError as exc:
                report.warnings.append(f"Could not derive resolution in metres: {exc}")

    units = info.band_units or units_override
    if info.band_units and units_override and info.band_units.lower() != units_override.lower():
        report.errors.append(
            f"--units {units_override!r} contradicts units stored in the file ({info.band_units!r})"
        )
    if not units:
        report.errors.append(
            "Elevation units are not stated in the file. Check the product label and pass --units explicitly."
        )
    elif data_type == "DEM" and units.lower() not in METRE_UNITS:
        report.errors.append(f"Unsupported elevation units {units!r}; this version expects metres")
    report.units = units

    if info.nodata is None:
        report.warnings.append("No nodata value declared; every pixel is treated as valid")
    return report


def register_dataset(
    *,
    path: Path,
    name: str,
    source: str = "",
    instrument: str = "",
    product_id: str = "",
    data_type: str = "DEM",
    vertical_datum: str | None = None,
    units: str | None = None,
    latitude_convention: str | None = None,
    observation_date: date | None = None,
    download_date: date | None = None,
    compute_checksum: bool = True,
    dry_run: bool = False,
):
    """Validate and register (or update) a dataset. Raises DatasetValidationError."""
    from apps.datasets.models import Dataset

    path = Path(path).resolve()
    if not path.is_file():
        raise DatasetValidationError([f"File not found: {path}"])

    report = validate_dem(path, units_override=units, data_type=data_type)
    warnings = list(report.warnings)
    if not vertical_datum:
        warnings.append("Vertical datum not given (e.g. 'MOLA areoid'); stored as UNSPECIFIED")
    lat_conv = report.latitude_convention
    if latitude_convention:
        if lat_conv not in (LatitudeConvention.UNKNOWN,) and latitude_convention != lat_conv:
            report.errors.append(
                f"--latitude-convention {latitude_convention} contradicts the CRS geometry ({lat_conv})"
            )
        lat_conv = latitude_convention
    if not report.ok:
        raise DatasetValidationError(report.errors, warnings)
    if dry_run:
        return None, report, warnings

    info = report.info
    defaults: dict[str, Any] = dict(
        source=source,
        instrument=instrument,
        product_id=product_id,
        data_type=data_type,
        file_path=str(path),
        driver=info.driver,
        width=info.width,
        height=info.height,
        resolution_meters=report.resolution_meters,
        pixel_size_x=info.pixel_size_x,
        pixel_size_y=info.pixel_size_y,
        crs=info.crs_wkt or "",
        crs_name=info.crs_name or "",
        longitude_convention=str(report.longitude_convention),
        latitude_convention=str(lat_conv),
        vertical_datum=vertical_datum or "UNSPECIFIED",
        units=report.units or "",
        nodata_value=info.nodata,
        coverage_bbox={"crs_units": info.crs_axis_units, **info.bounds},
        observation_date=observation_date,
        download_date=download_date,
        file_size=path.stat().st_size,
        checksum=sha256_file(path) if compute_checksum else "",
        is_validated=True,
        status=Dataset.Status.VALID,
        validation_messages=[{"level": "warning", "message": w} for w in warnings],
        metadata=info.to_dict(),
    )
    dataset, created = Dataset.objects.update_or_create(name=name, defaults=defaults)
    logger.info("%s dataset %s from %s", "Registered" if created else "Updated", name, path)
    return dataset, report, warnings


def refresh_file_status(dataset) -> bool:
    """Mark a dataset MISSING if its file disappeared. Returns True if the file exists."""
    exists = Path(dataset.file_path).is_file()
    if not exists and dataset.status != dataset.Status.MISSING:
        dataset.status = dataset.Status.MISSING
        dataset.is_validated = False
        dataset.save(update_fields=["status", "is_validated", "updated_at"])
    return exists


def point_for_dataset(lon: float, lat: float, lat_convention: str, dataset) -> tuple[float, float, str]:
    """Express the query point in the dataset's latitude convention (explicitly).

    Returns (lon, lat_adjusted, conversion_status); see mars_coordinates.adapt_latitude."""
    lat_adj, status = adapt_latitude(lat, lat_convention, dataset.latitude_convention)
    return lon, lat_adj, status


def datasets_covering(x: float, y: float, point_crs, data_type: str = "DEM", lat_convention: str = "UNKNOWN") -> list[Any]:
    """Return VALID datasets whose native bounds contain the point.

    Ordered finest resolution first (unknown resolution last)."""
    from pyproj import CRS

    from apps.datasets.models import Dataset

    hits = []
    for ds in Dataset.objects.filter(status=Dataset.Status.VALID, data_type=data_type):
        if not ds.crs or not ds.coverage_bbox:
            continue
        try:
            ds_crs = CRS.from_wkt(ds.crs)
            px, py, _ = point_for_dataset(x, y, lat_convention, ds)
            xd, yd = transform_point(px, py, point_crs, ds_crs)
        except Exception as exc:
            logger.warning("Cannot transform point into %s: %s", ds.name, exc)
            continue
        b = ds.coverage_bbox
        xs = [xd, xd + 360.0, xd - 360.0] if ds_crs.is_geographic else [xd]
        if any(b["left"] <= cx < b["right"] for cx in xs) and b["bottom"] < yd <= b["top"]:
            hits.append(ds)
    hits.sort(key=lambda d: (d.resolution_meters is None, d.resolution_meters or 0.0))
    return hits
