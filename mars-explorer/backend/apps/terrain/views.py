"""Terrain endpoints. Elevations come only from registered, validated DEM files.

When no DEM covers a point, the API says so (HTTP 404, code DEM_NOT_AVAILABLE). It never
estimates elevation from imagery colours and never returns placeholder numbers.
"""
from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.coordinates import PointQuerySerializer
from apps.core.exceptions import ApiError
from services import dataset_manager, dem_reader, terrain_analysis
from services.mars_coordinates import resolve_crs

logger = logging.getLogger("mars.terrain")

ELEVATION_NOT_AVAILABLE = "DATA NOT AVAILABLE"

LATITUDE_WARNING = (
    "Latitude type of the query is not verified (AS_DECLARED_BY_SOURCE): the value was used "
    "unchanged in the DEM frame. If the source latitude is planetographic and the DEM is "
    "planetocentric (or vice versa) the position can be off by up to ~0.34 deg (~20 km) at "
    "mid-latitudes. Pass lat_convention=PLANETOCENTRIC or PLANETOGRAPHIC to convert explicitly."
)


def _parse_point(request):
    qp = request.query_params
    data = {"lon_east_deg": qp.get("lon"), "lat_deg": qp.get("lat")}
    if qp.get("crs"):
        data["crs"] = qp["crs"]
    if qp.get("lat_convention"):
        data["latitude_convention"] = qp["lat_convention"]
    ser = PointQuerySerializer(data=data)
    ser.is_valid(raise_exception=True)
    v = ser.validated_data
    crs, alias = resolve_crs(v["crs"])
    query = {
        "lon_east_deg": v["lon_east_deg"],
        "lat_deg": v["lat_deg"],
        "crs": v["crs"],
        "latitude_convention": v["latitude_convention"],
        "crs_resolution": (
            {"resolved_as": alias.resolved_as, "note": alias.reason} if alias else {"resolved_as": v["crs"], "note": None}
        ),
    }
    return v["lon_east_deg"], v["lat_deg"], crs, v["latitude_convention"], query


def _require_backend():
    st = dem_reader.raster_backend_status()
    if not st["available"]:
        raise ApiError(st["error"], code="DEM_BACKEND_UNAVAILABLE", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


def _dataset_summary(ds) -> dict:
    return {
        "id": ds.id,
        "name": ds.name,
        "instrument": ds.instrument,
        "source": ds.source,
        "product_id": ds.product_id,
        "resolution_meters": ds.resolution_meters,
        "crs_name": ds.crs_name,
        "latitude_convention": ds.latitude_convention,
        "vertical_datum": ds.vertical_datum,
        "units": ds.units,
    }


def _latitude_info(status_code: str, lat_in: float, lat_used: float, ds) -> dict:
    return {
        "status": status_code,
        "dataset_latitude_convention": ds.latitude_convention,
        "lat_query_deg": lat_in,
        "lat_used_deg": lat_used,
        "warning": LATITUDE_WARNING if status_code == "NOT_VERIFIED" else None,
    }


def _not_available(query: dict) -> ApiError:
    return ApiError(
        "No validated DEM covering this point is loaded. Elevation: DATA NOT AVAILABLE",
        code="DEM_NOT_AVAILABLE",
        status_code=status.HTTP_404_NOT_FOUND,
        details={"query": query, "elevation": ELEVATION_NOT_AVAILABLE},
    )


def _covering_existing(lon, lat, crs, lat_conv):
    for ds in dataset_manager.datasets_covering(lon, lat, crs, lat_convention=lat_conv):
        if dataset_manager.refresh_file_status(ds):
            yield ds


@api_view(["GET"])
def sample(request):
    lon, lat, crs, lat_conv, query = _parse_point(request)
    _require_backend()
    for ds in _covering_existing(lon, lat, crs, lat_conv):
        _, lat_used, conv = dataset_manager.point_for_dataset(lon, lat, lat_conv, ds)
        try:
            s = dem_reader.sample_point(ds.file_path, lon, lat_used, crs)
        except dem_reader.PointOutsideRaster:
            continue
        except dem_reader.RasterReadError as exc:
            logger.error("Sampling %s failed: %s", ds.name, exc)
            raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=500) from exc
        return Response(
            {
                "status": "NODATA" if s.is_nodata else "AVAILABLE",
                "query": query,
                "elevation_m": s.value,
                "elevation_display": ELEVATION_NOT_AVAILABLE if s.is_nodata else None,
                "units": ds.units,
                "vertical_datum": ds.vertical_datum,
                "method": "nearest DEM cell, no interpolation",
                "pixel": {"row": s.row, "col": s.col, "x_dataset": s.x_dataset, "y_dataset": s.y_dataset},
                "latitude_handling": _latitude_info(conv, lat, lat_used, ds),
                "dataset": _dataset_summary(ds),
            }
        )
    raise _not_available(query)


@api_view(["GET"])
def slope(request):
    lon, lat, crs, lat_conv, query = _parse_point(request)
    _require_backend()
    for ds in _covering_existing(lon, lat, crs, lat_conv):
        _, lat_used, conv = dataset_manager.point_for_dataset(lon, lat, lat_conv, ds)
        try:
            w = dem_reader.read_window(ds.file_path, lon, lat_used, crs, half_size=1)
        except dem_reader.PointOutsideRaster:
            continue
        except dem_reader.RasterReadError as exc:
            raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=500) from exc
        try:
            cs = terrain_analysis.cell_size_m(
                w.pixel_size_x, w.pixel_size_y, w.crs, w.y_dataset if w.crs.is_geographic else None
            )
        except ValueError as exc:
            raise ApiError(str(exc), code="TERRAIN_ANALYSIS_ERROR", status_code=422) from exc
        res = terrain_analysis.horn_slope_aspect(w.values, cs.dx_m, cs.dy_m)
        return Response(
            {
                "status": "AVAILABLE" if res.slope_deg is not None else "NODATA",
                "query": query,
                "slope_deg": res.slope_deg,
                "aspect_deg": res.aspect_deg,
                "terrain_ruggedness_index_m": terrain_analysis.terrain_ruggedness_index(w.values),
                "elevation_std_m": terrain_analysis.elevation_std(w.values),
                "nodata_fraction": terrain_analysis.nodata_fraction(w.values),
                "window": "3x3 cells",
                "latitude_handling": _latitude_info(conv, lat, lat_used, ds),
                "cell_size_m": {"dx": cs.dx_m, "dy": cs.dy_m, "method": cs.method},
                "method": "Horn (1981) finite differences on numeric DEM elevations",
                "disclaimer": "Slope describes the DEM at its own resolution; it is not a validated traversability or safety assessment.",
                "dataset": _dataset_summary(ds),
            }
        )
    raise _not_available(query)


@api_view(["GET"])
def coverage(request):
    lon, lat, crs, lat_conv, query = _parse_point(request)
    backend = dem_reader.raster_backend_status()
    covering = list(_covering_existing(lon, lat, crs, lat_conv)) if backend["available"] else []
    if not backend["available"]:
        analysis_status = "ERROR"
    elif covering:
        analysis_status = "AVAILABLE"
    else:
        analysis_status = "NO DATA"
    return Response(
        {
            "query": query,
            "terrain_analysis_status": analysis_status,
            "raster_backend": backend,
            "datasets": [_dataset_summary(d) for d in covering],
        }
    )
