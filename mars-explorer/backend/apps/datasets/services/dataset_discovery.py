"""Turn a catalogue product into a usable dataset.

A STAC product is registered as a ``Dataset`` row whose ``file_path`` is the HTTPS URL of its
Cloud-Optimized GeoTIFF. Registration reads the file header and one decimated overview over
the network (no bulk download) and runs the same validation as a local import: CRS must
describe the right body, values must be numeric elevations in metres.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from django.core.cache import cache

from services import dataset_manager, dem_reader, remote_raster

from . import stac_client

logger = logging.getLogger("mars.datasets")

READ_FAILURE_TTL_S = 600  # do not hammer a product whose file is missing or unreachable


class DiscoveryError(Exception):
    def __init__(self, message: str, code: str = "DATASET_INVALID", details: dict | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def dataset_name(product: dict) -> str:
    slug = re.sub(r"[^a-z0-9_-]+", "-", f"stac-{product['product_id']}".lower()).strip("-")
    return slug[:120]


def find_registered(product: dict):
    from apps.datasets.models import Dataset

    return Dataset.objects.filter(name=dataset_name(product)).first()


def register_remote_dem(product: dict):
    """Validate and register the product's DTM (idempotent). Returns the Dataset.

    Raises DiscoveryError when remote access is off, the host is not allow-listed or the
    raster fails validation (the row is then stored as INVALID so it is not retried blindly)."""
    from apps.datasets.models import Dataset

    existing = find_registered(product)
    if existing and existing.status == Dataset.Status.VALID:
        return existing
    if existing and existing.status == Dataset.Status.INVALID:
        raise DiscoveryError("This product failed validation earlier", details={"messages": existing.validation_messages})
    url = product["assets"]["dem"]
    fail_key = f"remote_dem_fail:{dataset_name(product)}"
    if cache.get(fail_key):
        raise DiscoveryError("The product could not be read a moment ago; it is retried later", "DEM_READ_ERROR")
    if not remote_raster.remote_enabled():
        raise DiscoveryError("Remote DEM access is disabled on this server", "REMOTE_DEM_DISABLED")
    try:
        remote_raster.check_remote_url(url)
    except remote_raster.RemoteRasterError as exc:
        raise DiscoveryError(str(exc), "REMOTE_HOST_NOT_ALLOWED") from exc
    try:
        report = dataset_manager.validate_dem(
            url, units_override=product["units"], data_type="DEM", planet=product["planet_id"],
            vertical_datum=product["vertical_datum"], control_points=False,
        )
    except (dem_reader.RasterReadError, FileNotFoundError) as exc:
        cache.set(fail_key, True, READ_FAILURE_TTL_S)
        raise DiscoveryError("The product's file could not be read from the provider", "DEM_READ_ERROR") from exc
    info = report.info
    common = dict(
        planet=product["planet_id"], source=product["provider"], instrument=product["instrument"],
        product_id=product["product_id"], data_type="DEM", file_path=url, access="REMOTE_COG",
        license=product["license"], download_url=url, source_url=product.get("source_url") or "",
        footprint=product.get("footprint"), quality=product.get("quality") or {},
        quality_status=product.get("quality_status") or "NOT_DOCUMENTED",
        download_date=date.today(),
    )
    if not report.ok:
        Dataset.objects.update_or_create(name=dataset_name(product), defaults=dict(
            **common, status=Dataset.Status.INVALID, is_validated=False,
            validation_messages=[{"level": "error", "message": e} for e in report.errors],
        ))
        raise DiscoveryError("The product failed validation", details={"messages": report.errors})
    metadata = info.to_dict()
    metadata.update(
        statistics=report.statistics, vertical_datum_source="provider catalogue (collection description)",
        units_source=product.get("units_source"), import_steps=report.steps,
        stac={"collection": product["dataset_id"], "docs_url": product.get("docs_url"), "time_range": product.get("time_range")},
    )
    ds, _ = Dataset.objects.update_or_create(name=dataset_name(product), defaults=dict(
        **common, driver=info.driver, width=info.width, height=info.height,
        resolution_meters=report.resolution_meters, pixel_size_x=info.pixel_size_x, pixel_size_y=info.pixel_size_y,
        crs=info.crs_wkt or "", crs_name=info.crs_name or "",
        longitude_convention=str(report.longitude_convention), latitude_convention=str(report.latitude_convention),
        vertical_datum=report.vertical_datum or "UNSPECIFIED", units=report.units or "",
        nodata_value=info.nodata, coverage_bbox={"crs_units": info.crs_axis_units, **info.bounds},
        is_validated=True, status=Dataset.Status.VALID,
        validation_messages=[{"level": "warning", "message": w} for w in report.warnings],
        metadata=metadata,
    ))
    logger.info("Registered remote DEM %s (%s)", ds.name, product["dataset_id"])
    return ds
