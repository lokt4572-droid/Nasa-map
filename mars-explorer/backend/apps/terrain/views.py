"""Terrain endpoints. Elevations come only from registered, validated DEM files.

When no DEM covers a point, the API says so (HTTP 404, code DEM_NOT_AVAILABLE). It never
estimates elevation from imagery colours and never returns placeholder numbers.

Common query parameters: lon, lat, optional crs, lat_convention, planet (default MARS),
dataset (restrict to one dataset id), radius (window half-size in cells, 1..10).
"""
from __future__ import annotations

import logging

from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.coordinates import PointQuerySerializer, default_point_crs
from apps.core.exceptions import ApiError
from apps.datasets.models import Dataset
from services import dataset_manager, dem_reader, raster_render, terrain_analysis
from services.mars_coordinates import UnknownCRSError, resolve_crs

logger = logging.getLogger("mars.terrain")

ELEVATION_NOT_AVAILABLE = "DATA NOT AVAILABLE"

LATITUDE_WARNING = (
    "Latitude type of the query is not verified (AS_DECLARED_BY_SOURCE): the value was used "
    "unchanged in the DEM frame. If the source latitude is planetographic and the DEM is "
    "planetocentric (or vice versa) the position can be off by up to ~0.34 deg (~20 km) at "
    "mid-latitudes on Mars. Pass lat_convention=PLANETOCENTRIC or PLANETOGRAPHIC to convert explicitly."
)


def _parse_point(request, prefix: str = ""):
    qp = request.query_params
    planet = (qp.get("planet") or "MARS").upper()
    data = {
        "lon_east_deg": qp.get(f"{prefix}lon"),
        "lat_deg": qp.get(f"{prefix}lat"),
        "planet": planet,
        "crs": qp.get("crs") or None,
    }
    if data["crs"] is None:
        try:
            data["crs"] = default_point_crs(planet)
        except ValueError as exc:
            raise ApiError(str(exc), code="VALIDATION_ERROR") from exc
    if qp.get("lat_convention"):
        data["latitude_convention"] = qp["lat_convention"]
    ser = PointQuerySerializer(data=data)
    ser.is_valid(raise_exception=True)
    v = ser.validated_data
    crs, alias = resolve_crs(v["crs"], planet=v["planet"])
    query = {
        "planet": v["planet"],
        "lon_east_deg": v["lon_east_deg"],
        "lat_deg": v["lat_deg"],
        "crs": v["crs"],
        "latitude_convention": v["latitude_convention"],
        "crs_resolution": (
            {"resolved_as": alias.resolved_as, "note": alias.reason} if alias else {"resolved_as": v["crs"], "note": None}
        ),
    }
    return v["lon_east_deg"], v["lat_deg"], crs, v["latitude_convention"], query


def _int_param(request, name: str, default: int, lo: int, hi: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        val = int(raw)
    except ValueError as exc:
        raise ApiError(f"{name} must be an integer", code="VALIDATION_ERROR") from exc
    if not lo <= val <= hi:
        raise ApiError(f"{name} must be in {lo}..{hi}", code="VALIDATION_ERROR")
    return val


def _require_backend():
    st = dem_reader.raster_backend_status()
    if not st["available"]:
        raise ApiError(st["error"], code="DEM_BACKEND_UNAVAILABLE", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)


def _dataset_summary(ds) -> dict:
    return {
        "id": ds.id,
        "name": ds.name,
        "planet": ds.planet,
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
        details={"query": query, "elevation": ELEVATION_NOT_AVAILABLE, "status": "NOT_AVAILABLE"},
    )


def _covering_existing(request, lon, lat, crs, lat_conv, planet):
    only = request.query_params.get("dataset")
    for ds in dataset_manager.datasets_covering(lon, lat, crs, lat_convention=lat_conv, planet=planet):
        if only and str(ds.id) != only:
            continue
        if dataset_manager.refresh_file_status(ds):
            yield ds


def _window_for(request, metrics: list[str], radius: int = 1):
    """Shared driver: find a covering DEM, read the window, compute metrics."""
    lon, lat, crs, lat_conv, query = _parse_point(request)
    _require_backend()
    for ds in _covering_existing(request, lon, lat, crs, lat_conv, query["planet"]):
        _, lat_used, conv = dataset_manager.point_for_dataset(lon, lat, lat_conv, ds)
        try:
            w = dem_reader.read_window(ds.file_path, lon, lat_used, crs, half_size=radius)
        except dem_reader.PointOutsideRaster:
            continue
        except dem_reader.RasterReadError as exc:
            raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=500) from exc
        try:
            results = {m: terrain_analysis.analyze_window(ds, w, m, radius) for m in metrics}
        except ValueError as exc:
            raise ApiError(str(exc), code="TERRAIN_ANALYSIS_ERROR", status_code=422) from exc
        return ds, w, results, _latitude_info(conv, lat, lat_used, ds), query
    raise _not_available(query)


@api_view(["GET"])
def sample(request):
    lon, lat, crs, lat_conv, query = _parse_point(request)
    _require_backend()
    for ds in _covering_existing(request, lon, lat, crs, lat_conv, query["planet"]):
        _, lat_used, conv = dataset_manager.point_for_dataset(lon, lat, lat_conv, ds)
        try:
            s = dem_reader.sample_point(ds.file_path, lon, lat_used, crs)
        except dem_reader.PointOutsideRaster:
            continue
        except dem_reader.RasterReadError as exc:
            logger.error("Sampling %s failed: %s", ds.name, exc)
            raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=500) from exc
        result = terrain_analysis._result(
            "elevation", s.value, ds.units or "m", ds, "NODATA" if s.is_nodata else "OK", "1 cell"
        )
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
                "results": [result],
            }
        )
    raise _not_available(query)


@api_view(["GET"])
def slope(request):
    ds, w, results, lat_info, query = _window_for(request, ["slope", "aspect", "roughness", "nodata_coverage"])
    sl = results["slope"]
    return Response(
        {
            "status": "AVAILABLE" if sl["value"] is not None else "NODATA",
            "query": query,
            "slope_deg": sl["value"],
            "aspect_deg": results["aspect"]["value"],
            "terrain_ruggedness_index_m": results["roughness"]["value"],
            "elevation_std_m": terrain_analysis.elevation_std(w.values),
            "nodata_fraction": results["nodata_coverage"]["value"],
            "window": "3x3 cells",
            "latitude_handling": lat_info,
            "cell_size_m": {**sl["cell_size_m"], "method": "ellipsoid radii of curvature at latitude" if w.crs.is_geographic else "projected: metre axes"},
            "method": "Horn (1981) finite differences on numeric DEM elevations",
            "disclaimer": "Slope describes the DEM at its own resolution; it is not a validated traversability or safety assessment.",
            "dataset": _dataset_summary(ds),
            "results": list(results.values()),
        }
    )


def _single_metric(request, metric: str, radius: int = 1):
    ds, _, results, lat_info, query = _window_for(request, [metric], radius)
    r = results[metric]
    return Response(
        {
            "status": "AVAILABLE" if r["value"] is not None else "NOT_AVAILABLE",
            "query": query,
            "result": r,
            "latitude_handling": lat_info,
            "dataset": _dataset_summary(ds),
        }
    )


@api_view(["GET"])
def aspect(request):
    return _single_metric(request, "aspect")


@api_view(["GET"])
def roughness(request):
    return _single_metric(request, "roughness")


@api_view(["GET"])
def relief(request):
    return _single_metric(request, "local_relief", _int_param(request, "radius", 2, 1, 10))


@api_view(["GET"])
def nodata(request):
    return _single_metric(request, "nodata_coverage", _int_param(request, "radius", 2, 1, 10))


@api_view(["GET"])
def elevation(request):
    """Elevation in the uniform result schema (same value as /terrain/sample/)."""
    return _single_metric(request, "elevation")


@api_view(["GET"])
def difference(request):
    """Elevation difference B - A. Query: lon,lat (A) and lon2,lat2 (B)."""
    lon, lat, crs, lat_conv, q_a = _parse_point(request)
    try:
        lon2 = float(request.query_params["lon2"])
        lat2 = float(request.query_params["lat2"])
    except (KeyError, ValueError) as exc:
        raise ApiError("lon2 and lat2 are required numbers", code="VALIDATION_ERROR") from exc
    if not -90 <= lat2 <= 90 or not -180 <= lon2 <= 360:
        raise ApiError("lon2/lat2 out of range", code="VALIDATION_ERROR")
    _require_backend()
    for ds in _covering_existing(request, lon, lat, crs, lat_conv, q_a["planet"]):
        values = []
        for plon, plat in ((lon, lat), (lon2, lat2)):
            _, lat_used, _ = dataset_manager.point_for_dataset(plon, plat, lat_conv, ds)
            try:
                s = dem_reader.sample_point(ds.file_path, plon, lat_used, crs)
                values.append(s.value)
            except dem_reader.PointOutsideRaster:
                values.append(None)
        diff = terrain_analysis.elevation_difference(values[0], values[1])
        r = terrain_analysis._result(
            "elevation_difference", diff, "m", ds, "OK" if diff is not None else "NODATA",
            "2 cells", elevation_a_m=values[0], elevation_b_m=values[1],
        )
        return Response({"status": "AVAILABLE" if diff is not None else "NOT_AVAILABLE", "query": q_a, "point_b": {"lon_east_deg": lon2, "lat_deg": lat2}, "result": r, "dataset": _dataset_summary(ds)})
    raise _not_available(q_a)


@api_view(["GET"])
def area(request):
    """Statistics inside bbox=west,south,east,north (map CRS degrees) for one dataset."""
    ds = _dataset_param(request)
    bbox, map_crs = _bbox_param(request, ds.planet)
    from pyproj import CRS, Transformer

    tr = Transformer.from_crs(map_crs, CRS.from_wkt(ds.crs), always_xy=True)
    xs, ys = tr.transform([bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]])
    try:
        r = terrain_analysis.area_statistics(ds, (min(xs), min(ys), max(xs), max(ys)))
    except dem_reader.PointOutsideRaster as exc:
        raise ApiError(str(exc), code="DEM_NOT_AVAILABLE", status_code=404) from exc
    return Response({"status": "AVAILABLE" if r["value"] is not None else "NOT_AVAILABLE", "bbox": bbox, "result": r, "dataset": _dataset_summary(ds)})


def _dataset_param(request) -> Dataset:
    raw = request.query_params.get("dataset")
    if not raw or not raw.isdigit():
        raise ApiError("dataset (id) is required", code="VALIDATION_ERROR")
    ds = Dataset.objects.filter(pk=int(raw)).first()
    if not ds:
        raise ApiError("Dataset not found", code="NOT_FOUND", status_code=404)
    if ds.status != Dataset.Status.VALID or not dataset_manager.refresh_file_status(ds):
        raise ApiError(f"Dataset {ds.name} is {ds.status}", code="DEM_NOT_AVAILABLE", status_code=404)
    return ds


def _bbox_param(request, planet: str):
    try:
        bbox = [float(v) for v in request.query_params.get("bbox", "").split(",")]
    except ValueError as exc:
        raise ApiError("bbox must be west,south,east,north", code="VALIDATION_ERROR") from exc
    if len(bbox) != 4 or not (bbox[0] < bbox[2] and bbox[1] < bbox[3]) or not (-90 <= bbox[1] and bbox[3] <= 90):
        raise ApiError("bbox must be west,south,east,north with west<east, south<north", code="VALIDATION_ERROR")
    crs_id = request.query_params.get("crs") or default_point_crs(planet)
    try:
        map_crs, _ = resolve_crs(crs_id, planet=planet)
    except UnknownCRSError as exc:
        raise ApiError(str(exc), code="VALIDATION_ERROR") from exc
    return bbox, map_crs


@api_view(["GET"])
def coverage(request):
    lon, lat, crs, lat_conv, query = _parse_point(request)
    backend = dem_reader.raster_backend_status()
    covering = list(_covering_existing(request, lon, lat, crs, lat_conv, query["planet"])) if backend["available"] else []
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


@api_view(["GET"])
def render(request):
    """PNG visualization (elevation | hillshade | slope | aspect | roughness) for a map bbox.

    Query: dataset (id), product, bbox=west,south,east,north (degrees, query CRS), width,
    height (px, <= 1024), crs, lat_convention. Visual product only — see X-Visualization."""
    from django.http import HttpResponse

    from apps.datasets.models import Dataset
    from services import raster_render

    qp = request.query_params
    try:
        west, south, east, north = (float(v) for v in qp.get("bbox", "").split(","))
        width, height = int(qp.get("width", "512")), int(qp.get("height", "512"))
        ds_id = int(qp.get("dataset", ""))
    except ValueError as exc:
        raise ApiError("dataset (int), bbox 'w,s,e,n', width and height are required", code="VALIDATION_ERROR", status_code=400) from exc
    if not (-540 <= west < east <= 540 and -90 <= south < north <= 90):
        raise ApiError("bbox out of range or empty", code="VALIDATION_ERROR", status_code=400)
    lat_conv = qp.get("lat_convention") or "AS_DECLARED_BY_SOURCE"
    try:
        ds = Dataset.objects.get(pk=ds_id, status=Dataset.Status.VALID)
    except Dataset.DoesNotExist as exc:
        raise ApiError("Dataset not found or not VALID", code="NOT_FOUND", status_code=404) from exc
    crs_id = qp.get("crs") or default_point_crs(ds.planet)
    try:
        crs, _ = resolve_crs(crs_id, planet=ds.planet)
    except Exception as exc:
        raise ApiError(str(exc), code="VALIDATION_ERROR", status_code=400) from exc
    _require_backend()
    if not dataset_manager.refresh_file_status(ds):
        raise ApiError("Dataset file is missing", code="DEM_NOT_AVAILABLE", status_code=404)
    try:
        png, meta = raster_render.render(ds, qp.get("product", "elevation"), (west, south, east, north), width, height, crs, lat_conv)
    except raster_render.RenderError as exc:
        raise ApiError(str(exc), code="VALIDATION_ERROR", status_code=400) from exc
    resp = HttpResponse(png, content_type="image/png")
    resp["X-Visualization"] = "true; colours are not measurements"
    resp["X-Value-Min"] = "" if meta["value_min"] is None else f"{meta['value_min']:.4f}"
    resp["X-Value-Max"] = "" if meta["value_max"] is None else f"{meta['value_max']:.4f}"
    resp["X-Value-Units"] = meta["units"] or ""
    resp["X-Valid-Fraction"] = f"{meta['valid_fraction']:.4f}"
    resp["X-Dataset"] = ds.name
    resp["Access-Control-Expose-Headers"] = "X-Visualization, X-Value-Min, X-Value-Max, X-Value-Units, X-Valid-Fraction, X-Dataset"
    resp["Cache-Control"] = "private, max-age=300"
    return resp


def _float_param(request, name: str, default: float, lo: float, hi: float) -> float:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    try:
        val = float(raw)
    except ValueError as exc:
        raise ApiError(f"{name} must be a number", code="VALIDATION_ERROR") from exc
    if not (lo <= val <= hi) or not val == val:
        raise ApiError(f"{name} must be in {lo}..{hi}", code="VALIDATION_ERROR")
    return val


@api_view(["GET"])
def patch(request):
    """Elevation grid around a point for the local 3D terrain viewer.

    Query: planet, longitude|lon, latitude|lat, radius_m (100..500000, default 20000),
    max_dimension (16..512, default 256), optional dataset, crs, lat_convention.
    404 DEM_NOT_AVAILABLE when no validated DEM covers the point; 422 when the DEM is too
    coarse for the requested radius (the response says the minimum radius)."""
    from services import terrain_patch

    qp = request.query_params.copy()
    for long_name, short in (("longitude", "lon"), ("latitude", "lat")):
        if long_name in qp and short not in qp:
            qp[short] = qp[long_name]
    request._request.GET = qp  # accept both spellings
    radius = _float_param(request, "radius_m", 20_000.0, *terrain_patch.RADIUS_LIMITS_M)
    max_dim = _int_param(request, "max_dimension", 256, *terrain_patch.DIMENSION_LIMITS)
    lon, lat, crs, lat_conv, query = _parse_point(request)
    _require_backend()
    candidates = list(_covering_existing(request, lon, lat, crs, lat_conv, query["planet"]))
    if not candidates:
        raise _not_available(query)
    ds = min(candidates, key=lambda d: d.resolution_meters or float("inf"))  # finest covering DEM
    _, lat_used, conv = dataset_manager.point_for_dataset(lon, lat, lat_conv, ds)
    try:
        body = terrain_patch.build_patch(ds, lon, lat, radius, max_dim, crs, lat_conv)
    except terrain_patch.PatchError as exc:
        raise ApiError(str(exc), code=exc.code, status_code=422, details={"query": query, **exc.details}) from exc
    except dem_reader.RasterReadError as exc:
        raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=500) from exc
    body["query"] = query
    body["latitude"] = _latitude_info(conv, lat, lat_used, ds)
    body["alternatives"] = [_dataset_summary(d) for d in candidates if d.id != ds.id]
    resp = Response(body)
    resp["Cache-Control"] = "private, max-age=300"
    return resp
