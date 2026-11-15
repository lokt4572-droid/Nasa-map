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
        "access": ds.access,
        "license": ds.license,
        "quality_status": ds.quality_status,
        "source_url": ds.source_url or None,
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
    """DEMs covering a point. ``remote=1`` also asks the provider catalogue (USGS STAC) for
    DTM products that are not registered yet; they are listed, not read."""
    lon, lat, crs, lat_conv, query = _parse_point(request)
    backend = dem_reader.raster_backend_status()
    covering = list(_covering_existing(request, lon, lat, crs, lat_conv, query["planet"])) if backend["available"] else []
    body = {
        "query": query,
        "raster_backend": backend,
        "datasets": [_dataset_summary(d) for d in covering],
    }
    remote_usable = 0
    if request.query_params.get("remote") == "1" and backend["available"]:
        from apps.datasets.services import coverage_service

        found = coverage_service.at_point(lon, lat, crs, lat_conv, query["planet"], include_remote=True)
        body["catalogue"] = {"provider": found["provider"], "products": [r for r in found["datasets"] if r["status"] in ("ONLINE_SOURCE", "INVALID")]}
        body["best"] = found["best"]
        remote_usable = sum(1 for r in body["catalogue"]["products"] if r["status"] == "ONLINE_SOURCE")
    if not backend["available"]:
        body["terrain_analysis_status"] = "ERROR"
    elif covering:
        body["terrain_analysis_status"] = "AVAILABLE"
    else:
        body["terrain_analysis_status"] = "NO DATA"
    body["coverage_status"] = "AVAILABLE" if covering else ("AVAILABLE_REMOTE" if remote_usable else "NO_DATA_COVERAGE")
    return Response(body)


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
    value_range = None
    if qp.get("range"):
        try:
            r_lo, r_hi = (float(v) for v in qp["range"].split(","))
        except ValueError as exc:
            raise ApiError("range must be min,max", code="VALIDATION_ERROR", status_code=400) from exc
        if not (r_lo < r_hi) or abs(r_lo) > 1e6 or abs(r_hi) > 1e6:
            raise ApiError("range must be min,max with min < max", code="VALIDATION_ERROR", status_code=400)
        value_range = (r_lo, r_hi)
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
        png, meta = raster_render.render(ds, qp.get("product", "elevation"), (west, south, east, north), width, height, crs, lat_conv, value_range)
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


MAX_AUTO_TRIES = 4  # DEMs tried per patch request


def _auto_radius(ds, max_dim: int, limits: tuple[float, float]) -> float:
    """Radius that shows the DEM at its own resolution (one mesh cell per DEM cell)."""
    native = float(ds.resolution_meters or 0.0)
    return min(max(native * max_dim / 2.0, limits[0]), limits[1]) if native else 20_000.0


@api_view(["GET"])
def patch(request):
    """Elevation grid around a point for the local 3D terrain viewer.

    Query: planet, longitude|lon, latitude|lat, radius_m (100..500000; default = the radius that
    shows the chosen DEM at native resolution), max_dimension (16..512, default 256), optional
    dataset (id), crs, lat_convention, and

    * ``source=local`` (default): registered DEMs only;
    * ``source=auto``: also the provider catalogue — the finest DTM product covering the point is
      validated and registered for remote window reads (no bulk download);
    * ``product=<collection>/<product_id>``: that catalogue product.

    404 DEM_NOT_AVAILABLE when no validated DEM covers the point; 422 when the DEM is too coarse
    for the requested radius (the response says the minimum radius)."""
    from apps.datasets.services import catalogues, coverage_service, dataset_discovery
    from services import terrain_patch

    qp = request.query_params.copy()
    for long_name, short in (("longitude", "lon"), ("latitude", "lat")):
        if long_name in qp and short not in qp:
            qp[short] = qp[long_name]
    request._request.GET = qp  # accept both spellings
    max_dim = _int_param(request, "max_dimension", 256, *terrain_patch.DIMENSION_LIMITS)
    source = (qp.get("source") or "local").lower()
    if source not in ("local", "auto"):
        raise ApiError("source must be local or auto", code="VALIDATION_ERROR")
    lon, lat, crs, lat_conv, query = _parse_point(request)
    _require_backend()
    planet = query["planet"]
    selection = {"mode": source, "reason": "finest registered DEM covering the point"}

    def _register(product: dict):
        try:
            return dataset_discovery.register_remote_dem(product)
        except dataset_discovery.DiscoveryError as exc:
            http = {"REMOTE_DEM_DISABLED": 503, "DEM_READ_ERROR": 502}.get(exc.code, 422)
            raise ApiError(str(exc), code=exc.code, status_code=http, details=exc.details) from exc

    forced = None
    if qp.get("product"):
        coll, _, pid = qp["product"].partition("/")
        try:
            forced = _register(catalogues.get_product(coll, pid))
        except catalogues.StacError as exc:
            raise ApiError(str(exc), code=exc.code, status_code=404 if exc.code == "NOT_FOUND" else 502) from exc
        selection = {"mode": "product", "reason": "catalogue product chosen by the user"}
    skipped: list[dict] = []
    candidates = list(_covering_existing(request, lon, lat, crs, lat_conv, planet))
    if forced is not None and forced.id not in {d.id for d in candidates}:
        raise ApiError("The chosen product does not cover this point", code="DEM_NOT_AVAILABLE", status_code=404,
                       details={"query": query, "coverage_status": "NO_DATA_COVERAGE"})
    # Options, finest first: registered DEMs and (source=auto) catalogue products not yet registered.
    if forced is not None:
        options: list[tuple[float, str, object]] = [(0.0, "ds", forced)]
    else:
        options = [(d.resolution_meters or float("inf"), "ds", d) for d in candidates]
        if source == "auto" and not qp.get("dataset"):
            found = coverage_service.at_point(lon, lat, crs, lat_conv, planet, include_remote=True)
            selection["provider"] = found["provider"]
            options += [(r["resolution_m"] or float("inf"), "rec", r) for r in found["datasets"] if r["status"] == "ONLINE_SOURCE"]
        options.sort(key=lambda o: o[0])

    def attempt(cand):
        radius = (_float_param(request, "radius_m", 20_000.0, *terrain_patch.RADIUS_LIMITS_M) if qp.get("radius_m")
                  else _auto_radius(cand, max_dim, terrain_patch.RADIUS_LIMITS_M))
        try:
            return terrain_patch.build_patch(cand, lon, lat, radius, max_dim, crs, lat_conv)
        except dem_reader.RasterReadError as exc:
            raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=502 if cand.access == "REMOTE_COG" else 500) from exc

    # A DEM that cannot be read, or whose footprint contains the point but which has a data gap
    # there, is reported and the next one is tried (at most MAX_AUTO_TRIES).
    ds = body = None
    gap = False
    for _, kind, obj in options[:MAX_AUTO_TRIES]:
        cand = obj
        if kind == "rec":
            try:
                cand = dataset_discovery.register_remote_dem(obj)
            except dataset_discovery.DiscoveryError as exc:
                skipped.append({"product_id": obj["product_id"], "code": exc.code, "message": str(exc)})
                continue
        try:
            body, ds = attempt(cand), cand
            if kind == "rec":
                selection["reason"] = "finest DTM with valid elevations at the point (provider catalogue)"
            break
        except terrain_patch.PatchError as exc:
            if exc.code != "DEM_NO_VALID_CELLS" or forced is not None:
                raise ApiError(str(exc), code=exc.code, status_code=422, details={"query": query, **exc.details}) from exc
            gap = True
            skipped.append({"product_id": cand.product_id or cand.name, "code": "DATA_GAP", "message": "the DTM has no valid values at this location"})
    if skipped:
        selection["skipped_products"] = skipped
    if body is None:
        if gap:
            raise ApiError("Every DEM covering this location has a data gap here; no elevation is shown", code="DEM_NO_VALID_CELLS",
                           status_code=422, details={"query": query, "skipped_products": skipped, "coverage_status": "DATA_GAP"})
        err = _not_available(query)
        if skipped:
            err.details["skipped_products"] = skipped
        if selection.get("provider"):
            err.details["provider"] = selection["provider"]
        raise err
    _, lat_used, conv = dataset_manager.point_for_dataset(lon, lat, lat_conv, ds)
    body["query"] = query
    body["selection"] = selection
    body["latitude"] = _latitude_info(conv, lat, lat_used, ds)
    body["alternatives"] = [_dataset_summary(d) for d in candidates if d.id != ds.id]
    resp = Response(body)
    resp["Cache-Control"] = "private, max-age=300"
    return resp

PROFILE_SAMPLES = (2, 1024)


@api_view(["GET"])
def profile(request):
    """Elevation profile along the geodesic between two points.

    Query: planet, from_lon, from_lat, to_lon, to_lat, samples (2..1024, default 200),
    optional dataset, crs, lat_convention. Distances are geodesic on the body's ellipsoid;
    elevations are nearest DEM cells (null = NoData, never interpolated)."""
    import numpy as np
    from pyproj import Geod

    from services import raster_render
    from services.planet_registry import get_planet

    lon1, lat1, crs, lat_conv, q1 = _parse_point(request, "from_")
    lon2, lat2, _, _, q2 = _parse_point(request, "to_")
    n = _int_param(request, "samples", 200, *PROFILE_SAMPLES)
    _require_backend()
    planet = get_planet(q1["planet"])
    first = {d.id: d for d in _covering_existing(request, lon1, lat1, crs, lat_conv, q1["planet"])}
    both = [d for d in _covering_existing(request, lon2, lat2, crs, lat_conv, q1["planet"]) if d.id in first]
    if not both:
        raise ApiError(
            "No validated DEM covers both profile end points", code="DEM_NOT_AVAILABLE", status_code=404,
            details={"from": q1, "to": q2, "coverage_status": "NO_DATA_COVERAGE"},
        )
    ds = min(both, key=lambda d: d.resolution_meters or float("inf"))
    geod = Geod(a=planet.radius_equatorial_m, b=planet.radius_polar_m)
    az, _, total = geod.inv(lon1, lat1, lon2, lat2)
    mid = geod.npts(lon1, lat1, lon2, lat2, n - 2) if n > 2 else []
    pts = [(lon1, lat1), *mid, (lon2, lat2)]
    lons = np.array([p[0] for p in pts])
    lats = np.array([p[1] for p in pts])
    try:
        # Bounded read: about two DEM cells per sample at most (overviews are used for long lines).
        budget = max(256, 2 * len(pts))
        z = raster_render.sample_lonlat(ds, lons, lats, crs, lat_conv, max_read=(budget, budget))
    except dem_reader.RasterReadError as exc:
        raise ApiError(str(exc), code="DEM_READ_ERROR", status_code=500) from exc
    dist = np.linspace(0.0, float(total), len(pts))
    valid = np.isfinite(z)
    dz = np.diff(z[valid]) if valid.sum() > 1 else np.array([])
    spacing = float(total) / max(1, len(pts) - 1)
    return Response({
        "query": {"from": q1, "to": q2, "samples": len(pts)},
        "dataset": _dataset_summary(ds),
        "distance_m": float(total),
        "initial_azimuth_deg": float(az),
        "sample_spacing_m": spacing,
        "native_resolution_m": ds.resolution_meters,
        "oversampled": bool(ds.resolution_meters and spacing < ds.resolution_meters),
        "points": [
            {"distance_m": round(float(d), 2), "lon_east_deg": float(lo), "lat_deg": float(la),
             "elevation_m": (round(float(v), 3) if np.isfinite(v) else None)}
            for d, lo, la, v in zip(dist, lons, lats, z)
        ],
        "statistics": {
            "min_m": float(np.nanmin(z)) if valid.any() else None,
            "max_m": float(np.nanmax(z)) if valid.any() else None,
            "total_ascent_m": float(dz[dz > 0].sum()) if dz.size else None,
            "total_descent_m": float(-dz[dz < 0].sum()) if dz.size else None,
            "nodata_percentage": round(100 * float(1 - valid.mean()), 3),
        },
        "vertical_datum": ds.vertical_datum,
        "units": ds.units,
        "notes": ["Nearest DEM cell per sample; NoData stays null.",
                  "Long lines on a fine DEM are read from its overviews (decimated), bounded to about two cells per sample.",
                  "Ascent/descent are sums over valid samples at this sample spacing, not a measured path."],
    })
