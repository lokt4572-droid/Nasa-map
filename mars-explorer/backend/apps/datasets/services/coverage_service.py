"""What elevation data exists at a place: registered datasets plus catalogue products."""
from __future__ import annotations

import math

from services import dataset_manager, remote_raster
from services.planet_registry import get_planet

from . import catalogues, dataset_discovery

LEVELS = ("GLOBAL", "REGIONAL", "LOCAL_HIGH_RESOLUTION")


def level_for_resolution(resolution_m: float | None) -> str:
    if resolution_m is None:
        return "REGIONAL"
    if resolution_m > 200:
        return "GLOBAL"
    return "REGIONAL" if resolution_m > 5 else "LOCAL_HIGH_RESOLUTION"


def local_record(ds) -> dict:
    """A registered Dataset in the same shape as a catalogue product."""
    remote = remote_raster.is_remote(ds.file_path)
    return {
        "planet_id": ds.planet, "dataset_id": ds.name, "product_id": ds.product_id or ds.name,
        "provider": ds.source or "LOCAL", "source": ds.source, "instrument": ds.instrument,
        "data_type": ds.data_type, "level": level_for_resolution(ds.resolution_meters),
        "format": ds.driver, "resolution_m": ds.resolution_meters, "effective_accuracy": "NOT_DOCUMENTED",
        "footprint": ds.footprint, "bbox": None, "crs": ds.crs_name,
        "latitude_type": ds.latitude_convention, "longitude_convention": ds.longitude_convention,
        "vertical_datum": ds.vertical_datum, "units": ds.units, "license": ds.license or "NOT_DOCUMENTED",
        "attribution": ds.source, "time_range": {"datetime": ds.observation_date.isoformat() if ds.observation_date else None},
        "title": ds.name, "quality_status": ds.quality_status, "quality": ds.quality or {},
        "dem_available": ds.data_type == "DEM", "imagery_available": ds.data_type == "ORTHOIMAGE",
        "source_url": ds.source_url or ds.download_url or None,
        "local_file": None if remote else "REGISTERED",  # never the server path
        "registered_dataset_id": ds.id,
        "status": "REMOTE_REGISTERED" if remote else "LOCAL",
    }


def bbox_around(lon: float, lat: float, radius_m: float, planet_id: str) -> tuple[float, float, float, float]:
    r = get_planet(planet_id).radius_equatorial_m
    dlat = math.degrees(radius_m / r)
    dlon = min(180.0, dlat / max(math.cos(math.radians(min(abs(lat) + dlat, 89.9))), 1e-6))
    return (lon - dlon, max(-90.0, lat - dlat), lon + dlon, min(90.0, lat + dlat))


def at_point(lon: float, lat: float, query_crs, lat_convention: str, planet: str, include_remote: bool = True) -> dict:
    """Elevation datasets covering a point, finest first, with the provider status.

    The catalogue is asked with planetocentric east-positive degrees: callers pass lon/lat in
    the planet's default geographic CRS (the only CRS the map uses for clicks)."""
    local = [d for d in dataset_manager.datasets_covering(lon, lat, query_crs, lat_convention=lat_convention, planet=planet)
             if dataset_manager.refresh_file_status(d)]
    records = [local_record(d) for d in local]
    registered_products = {d.product_id for d in local if remote_raster.is_remote(d.file_path)}
    provider = {"name": catalogues.provider_name(planet), "status": "NOT_QUERIED", "collections": []}
    if include_remote and catalogues.collections_for(planet, "DEM"):
        if not remote_raster.remote_enabled():
            provider["status"] = "DISABLED"
        else:
            try:
                found = catalogues.search(planet, point=(lon, lat), data_type="DEM")
                provider.update(status="OK", collections=found["collections"], matched=len(found["products"]))
                for rec in found["products"]:
                    if rec["product_id"] in registered_products:
                        continue
                    reg = dataset_discovery.find_registered(rec)
                    if reg is not None and reg.status == "INVALID":
                        rec = {**rec, "status": "INVALID", "quality_status": "FAILED_VALIDATION"}
                    records.append(rec)
            except catalogues.StacError as exc:
                provider.update(status="ERROR", error=str(exc), code=exc.code)
    elif include_remote:
        provider["status"] = "NO_CATALOGUE_FOR_BODY"
    records.sort(key=lambda r: (r.get("status") == "INVALID", r["resolution_m"] is None, r["resolution_m"] or 0.0))
    usable = [r for r in records if r.get("status") != "INVALID"]
    return {
        "coverage_status": "AVAILABLE" if usable else ("PROVIDER_ERROR" if provider["status"] == "ERROR" and not records else "NO_DATA_COVERAGE"),
        "best": usable[0] if usable else None,
        "datasets": records,
        "provider": provider,
    }
