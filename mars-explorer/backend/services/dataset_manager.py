"""Registration, validation and lookup of local scientific datasets.

Validation rules — a DEM is VALID only if all hold:
  * file exists and GDAL can open it;
  * the raster has a CRS that PROJ can parse and that describes the selected planet
    (no CRS is ever assigned automatically);
  * width/height > 0 and band 1 is numeric (3+ uint8 bands = RGB image → rejected);
  * elevation units are known (from the file or given explicitly) and are metres;
  * the vertical datum is known: given by the operator or stated in the PDS label;
  * the raster contains valid values (decimated read);
  * the values are plausible heights, not planetary radius (|median| < 1 000 km);
  * control cells can be read.
Warnings (stored and shown, do not invalidate): no nodata value declared, multi-band,
latitude type taken from CRS geometry only.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from services import dem_reader
from services.mars_coordinates import (
    LatitudeConvention,
    LongitudeConvention,
    adapt_latitude,
    latitude_convention_for_crs,
    transform_point,
)
from services.planet_registry import DEFAULT_PLANET, crs_matches_planet, get_planet, planet_for_semi_major
from services.terrain_analysis import cell_size_m

logger = logging.getLogger("mars.datasets")

METRE_UNITS = {"m", "metre", "meter", "metres", "meters"}
NUMERIC_DTYPES = {"int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64", "float32", "float64"}
# Largest |median| accepted as a height. Planetary radii are 1.7e6 .. 6.4e6 m; real relief
# on any of the supported bodies is far below this.
MAX_PLAUSIBLE_HEIGHT_M = 1_000_000.0

# Import workflow steps (shown in the Data Manager and the CLI report).
IMPORT_STEPS = [
    "SELECT_FILE", "VALIDATE", "READ_METADATA", "CHECK_CRS", "CHECK_NODATA", "CHECK_UNITS",
    "CHECK_VERTICAL_DATUM", "CHECK_VALUES", "CONTROL_POINTS", "REGISTER_DATASET", "READY",
]


class DatasetValidationError(ValueError):
    def __init__(self, errors: list[str], warnings: list[str] | None = None, steps: list[dict] | None = None):
        super().__init__("; ".join(errors))
        self.errors = errors
        self.warnings = warnings or []
        self.steps = steps or []


@dataclass
class ValidationReport:
    info: dem_reader.RasterInfo
    planet: str = DEFAULT_PLANET
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    units: str | None = None
    latitude_convention: str = LatitudeConvention.UNKNOWN
    longitude_convention: str = LongitudeConvention.UNKNOWN
    resolution_meters: float | None = None
    vertical_datum: str | None = None
    vertical_datum_source: str | None = None
    label_statements: list[str] = field(default_factory=list)
    statistics: dict[str, Any] = field(default_factory=dict)
    control_points: list[dict[str, Any]] = field(default_factory=list)
    steps: list[dict[str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def step(self, name: str, status: str, detail: str = "") -> None:
        self.steps.append({"step": name, "status": status, "detail": detail})


def sha256_file(path: Path, chunk: int = 4 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return "sha256:" + h.hexdigest()


_DATUM_PATTERNS = [
    # Sentences in PDS labels that state what the stored value is relative to.
    re.compile(r"[^.<>\n]*(?:areoid|geoid|datum|reference (?:sphere|surface|radius)|relative to)[^.<>\n]*\.", re.I),
]
_RADIUS_STATEMENT = re.compile(r"[^.<>\n]*\bplanetary radius\b[^.<>\n]*\.", re.I)


def label_statements(text: str | None) -> tuple[list[str], str | None]:
    """Extract datum-related sentences from a PDS label and a datum hint."""
    if not text:
        return [], None
    # Labels wrap sentences across lines; normalize whitespace before matching.
    text = " ".join(text.split())
    found: list[str] = []
    for pat in _DATUM_PATTERNS + [_RADIUS_STATEMENT]:
        for m in pat.finditer(text):
            s = " ".join(m.group(0).split())
            if 20 <= len(s) <= 300 and s not in found:
                found.append(s)
    hint = None
    m = re.search(r"areoid[^.<>\n]*?(GMM\d[^.<>\n]*?\))", text, re.I)
    if re.search(r"radius minus the areoid", text, re.I):
        hint = "MOLA areoid" + (f" ({m.group(1).strip()})" if m else "")
    return found[:8], hint


def validate_dem(
    path: Path,
    units_override: str | None = None,
    data_type: str = "DEM",
    planet: str = DEFAULT_PLANET,
    vertical_datum: str | None = None,
) -> ValidationReport:
    """Inspect a raster and decide whether it can be used as a numeric DEM."""
    from pyproj import CRS

    body = get_planet(planet)
    info = dem_reader.inspect_raster(path)
    report = ValidationReport(info=info, planet=body.id)
    report.step("SELECT_FILE", "OK", str(path))
    report.step("VALIDATE", "OK", f"GDAL driver {info.driver}")

    if info.width <= 0 or info.height <= 0:
        report.errors.append(f"Invalid raster size {info.width}x{info.height}")
    if info.dtype not in NUMERIC_DTYPES:
        report.errors.append(f"Band 1 data type {info.dtype!r} is not numeric")
    if info.band_count > 1:
        report.warnings.append(f"Raster has {info.band_count} bands; band 1 is used as elevation")
    if data_type == "DEM" and info.dtype == "uint8" and info.band_count >= 3:
        report.errors.append("Looks like an RGB image (3+ uint8 bands), not a DEM. RGB pixels are not elevations.")
    report.step("READ_METADATA", "ERROR" if report.errors else "OK", f"{info.width}x{info.height}x{info.band_count} {info.dtype}")

    # --- CRS: never assigned automatically
    crs = None
    if not info.crs_wkt:
        report.errors.append(
            "No CRS found in the file metadata. Provide a correctly georeferenced product "
            "(e.g. the PDS4 label next to the image, or a GeoTIFF with a planetary CRS); the "
            "importer will not guess a CRS."
        )
    else:
        try:
            crs = CRS.from_wkt(info.crs_wkt)
        except Exception as exc:
            report.errors.append(f"CRS cannot be parsed by PROJ: {exc}")
    if crs is not None:
        if not crs_matches_planet(crs, body.id):
            a = crs.ellipsoid.semi_major_metre if crs.ellipsoid else None
            other = planet_for_semi_major(a) if a else None
            report.errors.append(
                f"CRS {crs.name!r} does not describe {body.name.split(' ')[0]} (semi-major axis {a if a is not None else '?'} m"
                + (f", looks like {other.id}" if other else "")
                + ")"
            )
            crs = None
    if crs is not None:
        report.latitude_convention = latitude_convention_for_crs(crs)
        if crs.is_geographic:
            left, right = info.bounds["left"], info.bounds["right"]
            if left >= 0 and right > 180:
                report.longitude_convention = LongitudeConvention.EAST_POSITIVE_360
            elif left >= -180.0001 and right <= 180.0001:
                report.longitude_convention = LongitudeConvention.EAST_POSITIVE_180
        else:
            # Projected: longitudes are defined by the projection (east-positive in PROJ).
            report.longitude_convention = LongitudeConvention.EAST_POSITIVE_180
        try:
            lat_mid = (info.bounds["bottom"] + info.bounds["top"]) / 2.0 if crs.is_geographic else None
            cs = cell_size_m(info.pixel_size_x, info.pixel_size_y, crs, lat_mid)
            # Geographic grids: N-S spacing (constant). Projected: the x spacing.
            report.resolution_meters = round(cs.dy_m if crs.is_geographic else cs.dx_m, 6)
        except ValueError as exc:
            report.warnings.append(f"Could not derive resolution in metres: {exc}")
        report.step("CHECK_CRS", "OK", f"{crs.name}; latitude {report.latitude_convention}")
    else:
        report.step("CHECK_CRS", "ERROR", report.errors[-1] if report.errors else "")

    # --- nodata
    if info.nodata is None:
        report.warnings.append("No nodata value declared; every pixel is treated as valid")
        report.step("CHECK_NODATA", "WARNING", "no nodata value declared")
    else:
        report.step("CHECK_NODATA", "OK", f"nodata = {info.nodata}")

    # --- units
    units = info.band_units or units_override
    if info.band_units and units_override and info.band_units.lower() != units_override.lower():
        report.errors.append(f"--units {units_override!r} contradicts units stored in the file ({info.band_units!r})")
    if not units:
        report.errors.append("Elevation units are not stated in the file. Check the product label and pass --units explicitly.")
    elif data_type == "DEM" and units.lower() not in METRE_UNITS:
        report.errors.append(f"Unsupported elevation units {units!r}; this version expects metres")
    report.units = units
    report.step("CHECK_UNITS", "OK" if units and units.lower() in METRE_UNITS else "ERROR", str(units))

    # --- vertical datum (operator value, or what the PDS label states)
    stmts, hint = label_statements(dem_reader.read_label_text(path))
    report.label_statements = stmts
    if vertical_datum:
        report.vertical_datum, report.vertical_datum_source = vertical_datum, "operator (--vertical-datum)"
        if hint and hint.split(" (")[0].lower() not in vertical_datum.lower():
            report.warnings.append(f"PDS label suggests datum {hint!r}; operator gave {vertical_datum!r}")
    elif hint:
        report.vertical_datum, report.vertical_datum_source = hint, "PDS label statement"
    elif data_type == "DEM":
        report.errors.append(
            "Vertical datum is unknown: it is not stated in the file/label. Read the product "
            "documentation and pass --vertical-datum (e.g. 'MOLA areoid', 'EGM2008')."
        )
    report.step(
        "CHECK_VERTICAL_DATUM",
        "OK" if report.vertical_datum else ("ERROR" if data_type == "DEM" else "WARNING"),
        f"{report.vertical_datum} [{report.vertical_datum_source}]" if report.vertical_datum else "unknown",
    )

    # --- values: present and plausible (decimated read, never the full array)
    try:
        stats = dem_reader.overview_statistics(path)
        report.statistics = stats
        if stats["valid_cells"] == 0:
            report.errors.append("The raster contains no valid values (all nodata/NaN) in a decimated read")
            report.step("CHECK_VALUES", "ERROR", "no valid values")
        elif data_type == "DEM" and abs(stats["median"]) > MAX_PLAUSIBLE_HEIGHT_M:
            report.errors.append(
                f"Median value {stats['median']:.0f} m looks like planetary radius, not height. "
                "Convert it relative to the vertical datum (radius minus reference surface) "
                "before importing; the importer does not reinterpret radius as elevation."
            )
            report.step("CHECK_VALUES", "ERROR", "values look like radius")
        else:
            report.step(
                "CHECK_VALUES", "OK",
                f"{stats['valid_fraction'] * 100:.1f}% valid, range {stats['min']:.1f}..{stats['max']:.1f}"
                + (" (approximate, decimated)" if stats["approximate"] else ""),
            )
    except dem_reader.RasterReadError as exc:
        report.errors.append(f"Reading values failed: {exc}")
        report.step("CHECK_VALUES", "ERROR", str(exc))

    try:
        report.control_points = dem_reader.control_points(path)
        n_ok = sum(1 for p in report.control_points if p["value"] is not None)
        report.step("CONTROL_POINTS", "OK" if n_ok else "WARNING", f"{n_ok}/{len(report.control_points)} control cells hold values")
    except Exception as exc:  # noqa: BLE001
        report.errors.append(f"Control point read failed: {exc}")
        report.step("CONTROL_POINTS", "ERROR", str(exc))
    return report


def register_dataset(
    *,
    path: Path,
    name: str,
    source: str = "",
    instrument: str = "",
    product_id: str = "",
    data_type: str = "DEM",
    planet: str = DEFAULT_PLANET,
    vertical_datum: str | None = None,
    units: str | None = None,
    latitude_convention: str | None = None,
    observation_date: date | None = None,
    download_date: date | None = None,
    compute_checksum: bool = True,
    dry_run: bool = False,
    license: str = "",
    download_url: str = "",
):
    """Validate and register (or update) a dataset. Raises DatasetValidationError."""
    from apps.datasets.models import Dataset

    path = Path(path).resolve()
    if not path.is_file():
        raise DatasetValidationError([f"File not found: {path}"], steps=[{"step": "SELECT_FILE", "status": "ERROR", "detail": str(path)}])

    report = validate_dem(path, units_override=units, data_type=data_type, planet=planet, vertical_datum=vertical_datum)
    warnings = list(report.warnings)
    lat_conv = report.latitude_convention
    if latitude_convention:
        if lat_conv not in (LatitudeConvention.UNKNOWN,) and latitude_convention != lat_conv:
            report.errors.append(f"--latitude-convention {latitude_convention} contradicts the CRS geometry ({lat_conv})")
        lat_conv = latitude_convention
    if not report.ok:
        report.step("REGISTER_DATASET", "SKIPPED", "validation failed")
        raise DatasetValidationError(report.errors, warnings, report.steps)
    if dry_run:
        report.step("REGISTER_DATASET", "SKIPPED", "dry run")
        return None, report, warnings

    info = report.info
    metadata = info.to_dict()
    metadata.update(
        statistics=report.statistics,
        control_points=report.control_points,
        label_statements=report.label_statements,
        vertical_datum_source=report.vertical_datum_source,
        import_steps=report.steps,
    )
    defaults: dict[str, Any] = dict(
        planet=report.planet,
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
        vertical_datum=report.vertical_datum or "UNSPECIFIED",
        units=report.units or "",
        nodata_value=info.nodata,
        coverage_bbox={"crs_units": info.crs_axis_units, **info.bounds},
        observation_date=observation_date,
        download_date=download_date,
        file_size=path.stat().st_size,
        checksum=sha256_file(path) if compute_checksum else "",
        license=license,
        download_url=download_url,
        is_validated=True,
        status=Dataset.Status.VALID,
        validation_messages=[{"level": "warning", "message": w} for w in warnings],
        metadata=metadata,
    )
    dataset, created = Dataset.objects.update_or_create(name=name, defaults=defaults)
    report.step("REGISTER_DATASET", "OK", f"id={dataset.id}")
    report.step("READY", "OK", "")
    dataset.metadata["import_steps"] = report.steps
    dataset.save(update_fields=["metadata"])
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


def datasets_covering(
    x: float, y: float, point_crs, data_type: str = "DEM", lat_convention: str = "UNKNOWN", planet: str = DEFAULT_PLANET
) -> list[Any]:
    """VALID datasets of ``planet`` whose native bounds contain the point.

    Ordered finest resolution first (unknown resolution last)."""
    from pyproj import CRS

    from apps.datasets.models import Dataset

    hits = []
    for ds in Dataset.objects.filter(status=Dataset.Status.VALID, data_type=data_type, planet=planet):
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
