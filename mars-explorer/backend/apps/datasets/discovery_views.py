"""Dataset discovery and coverage API (v0.4).

GET  datasets/search/            products by planet + bbox | point(+radius_m) (+filters)
GET  datasets/coverage/          what covers one point (registered + catalogue), finest first
POST datasets/register-remote/   validate and register one catalogue DTM for remote reads
GET  coverage/{planet}/          coverage categories and catalogues of a body
GET  coverage/{planet}/search/   same as datasets/search/ for that body
"""
from __future__ import annotations

from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.core.exceptions import ApiError
from services import remote_raster
from services.mars_coordinates import resolve_crs
from services.planet_registry import UnknownPlanetError, get_planet

from .models import Dataset
from .services import catalogues, coverage_service, dataset_discovery

QUALITY_RANK = {"LARGE_GAPS": 0, "NOT_DOCUMENTED": 1, "PARTIAL_GAPS": 2, "MOSTLY_COMPLETE": 3}
DATA_TYPES = {"DEM", "ORTHOIMAGE"}


def _planet(raw: str | None) -> str:
    try:
        return get_planet((raw or "MARS").upper()).id
    except UnknownPlanetError as exc:
        raise ApiError(str(exc), code="VALIDATION_ERROR") from exc


def _float(qp, name: str, lo: float, hi: float, required: bool = False) -> float | None:
    raw = qp.get(name)
    if raw in (None, ""):
        if required:
            raise ApiError(f"{name} is required", code="VALIDATION_ERROR")
        return None
    try:
        v = float(raw)
    except ValueError as exc:
        raise ApiError(f"{name} must be a number", code="VALIDATION_ERROR") from exc
    if not (lo <= v <= hi):  # also rejects NaN
        raise ApiError(f"{name} must be in {lo}..{hi}", code="VALIDATION_ERROR")
    return v


def _area(qp, planet: str):
    """(bbox, point) from bbox=west,south,east,north or longitude/latitude(+radius_m)."""
    if qp.get("bbox"):
        try:
            w, s, e, n = (float(v) for v in qp["bbox"].split(","))
        except ValueError as exc:
            raise ApiError("bbox must be west,south,east,north", code="VALIDATION_ERROR") from exc
        if not (-360 <= w < e <= 720 and e - w <= 360 and -90 <= s < n <= 90):
            raise ApiError("bbox must satisfy west<east (span <= 360) and -90<=south<north<=90", code="VALIDATION_ERROR")
        return (w, s, e, n), None
    lon = _float(qp, "longitude", -360, 720) if qp.get("longitude") else _float(qp, "lon", -360, 720, required=True)
    lat = _float(qp, "latitude", -90, 90) if qp.get("latitude") else _float(qp, "lat", -90, 90, required=True)
    radius = _float(qp, "radius_m", 1, 2_000_000)
    if radius:
        return coverage_service.bbox_around(lon, lat, radius, planet), None
    return None, (lon, lat)


def _search(request, planet: str) -> Response:
    qp = request.query_params
    data_type = (qp.get("data_type") or "DEM").upper()
    if data_type not in DATA_TYPES:
        raise ApiError(f"data_type must be one of {', '.join(sorted(DATA_TYPES))}", code="VALIDATION_ERROR")
    bbox, point = _area(qp, planet)
    max_res = _float(qp, "max_resolution", 0.01, 1e7)
    min_q = (qp.get("minimum_quality") or "").upper()
    if min_q and min_q not in QUALITY_RANK:
        raise ApiError(f"minimum_quality must be one of {', '.join(QUALITY_RANK)}", code="VALIDATION_ERROR")
    limit = int(_float(qp, "limit", 1, catalogues.MAX_LIMIT) or 50)
    provider = {"name": catalogues.provider_name(planet), "status": "OK"}
    products: list[dict] = []
    matched, truncated = 0, False
    if not catalogues.collections_for(planet, data_type):
        provider["status"] = "NO_CATALOGUE_FOR_BODY"
    else:
        try:
            found = catalogues.search(planet, bbox=bbox, point=point, data_type=data_type, max_resolution_m=max_res, limit=limit)
        except catalogues.StacError as exc:
            raise ApiError(str(exc), code=exc.code, status_code=504 if exc.code == "PROVIDER_TIMEOUT" else 502) from exc
        products, matched, truncated = found["products"], found["matched"], found["truncated"]
    if min_q:
        products = [p for p in products if QUALITY_RANK.get(p["quality_status"], 1) >= QUALITY_RANK[min_q]]
    registered = {d.product_id: d.id for d in Dataset.objects.filter(planet=planet, access="REMOTE_COG", status=Dataset.Status.VALID)}
    for p in products:
        p["registered_dataset_id"] = registered.get(p["product_id"])
    resp = Response({
        "planet": planet, "data_type": data_type,
        "query": {"bbox": bbox, "point": point, "max_resolution": max_res, "minimum_quality": min_q or None, "limit": limit},
        "count": len(products), "matched_by_provider": matched, "truncated": truncated,
        "provider": provider, "products": products,
        "note": "Footprints are the provider's product outlines. An imagery footprint is not a DEM footprint: only data_type DEM products carry elevations.",
    })
    resp["Cache-Control"] = "private, max-age=300"
    return resp


@api_view(["GET"])
def search(request):
    return _search(request, _planet(request.query_params.get("planet")))


@api_view(["GET"])
def planet_search(request, planet_id: str):
    return _search(request, _planet(planet_id))


@api_view(["GET"])
def point_coverage(request):
    qp = request.query_params
    planet = _planet(qp.get("planet"))
    lon = _float(qp, "longitude", -360, 720) if qp.get("longitude") else _float(qp, "lon", -360, 720, required=True)
    lat = _float(qp, "latitude", -90, 90) if qp.get("latitude") else _float(qp, "lat", -90, 90, required=True)
    from apps.core.coordinates import default_point_crs

    crs, _ = resolve_crs(default_point_crs(planet), planet=planet)
    out = coverage_service.at_point(lon, lat, crs, "PLANETOCENTRIC", planet, include_remote=qp.get("remote", "1") != "0")
    return Response({"planet": planet, "longitude": lon, "latitude": lat, **out})


@api_view(["POST"])
def register_remote(request):
    """Body: {"collection": "...", "product_id": "..."} — the URL always comes from the catalogue."""
    collection = str(request.data.get("collection") or "")
    product_id = str(request.data.get("product_id") or "")
    if not collection or not product_id or len(product_id) > 200:
        raise ApiError("collection and product_id are required", code="VALIDATION_ERROR")
    try:
        product = catalogues.get_product(collection, product_id)
        ds = dataset_discovery.register_remote_dem(product)
    except catalogues.StacError as exc:
        raise ApiError(str(exc), code=exc.code, status_code=404 if exc.code == "NOT_FOUND" else 502) from exc
    except dataset_discovery.DiscoveryError as exc:
        http = {"REMOTE_DEM_DISABLED": 503, "DEM_READ_ERROR": 502}.get(exc.code, 422)
        raise ApiError(str(exc), code=exc.code, status_code=http, details=exc.details) from exc
    return Response(coverage_service.local_record(ds), status=201)


@api_view(["GET"])
def planet_coverage(request, planet_id: str):
    """Coverage categories of a body: registered datasets and searchable catalogues."""
    planet = _planet(planet_id)
    levels: dict[str, list] = {lv: [] for lv in coverage_service.LEVELS}
    for ds in Dataset.objects.filter(planet=planet, status=Dataset.Status.VALID):
        levels[coverage_service.level_for_resolution(ds.resolution_meters)].append(coverage_service.local_record(ds))
    catalogue_list = [
        {"collection": c.id, "instrument": c.instrument, "data_type": c.data_type, "level": c.level,
         "provider": catalogues.provider_name(planet), "vertical_datum": c.vertical_datum, "units": c.units,
         "docs_url": c.docs_url, "notes": c.notes, "coverage": "FOOTPRINTS — search by area",
         "license": "Copernicus DEM licence (free use with attribution)" if planet == "EARTH" else "CC0-1.0"}
        for c in catalogues.collections_for(planet)
    ]
    return Response({
        "planet": planet, "levels": levels, "catalogues": catalogue_list,
        "remote_dem_access": "ENABLED" if remote_raster.remote_enabled() else "DISABLED",
        "note": "Global coverage of an imaging instrument does not imply DEM coverage: DTMs exist only inside listed footprints.",
    })
