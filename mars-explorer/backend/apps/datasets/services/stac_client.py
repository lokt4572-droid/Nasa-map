"""Client for the USGS Astrogeology STAC API (https://stac.astrogeology.usgs.gov/).

Only this provider speaks STAC; NASA Trek (WMTS), PDS (file archives) and Cesium ion have
their own adapters and are never queried through this module.

A search returns *footprints with metadata* — which DTM products exist where. It reads no
elevation values. Values are read later, window by window, from the product's
Cloud-Optimized GeoTIFF (see ``services.remote_raster``).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass

from django.core.cache import cache

from services import http_client

logger = logging.getLogger("mars.stac")

PROVIDER = "USGS Astrogeology STAC"
API_ROOT = "https://stac.astrogeology.usgs.gov/api"
DOCS_ROOT = "https://stac.astrogeology.usgs.gov/docs/data"
CACHE_TTL_S = 3600
MAX_LIMIT = 100
REQUEST_TIMEOUT_S = 30.0  # measured 2-40 s for one page on 2026-11-15 (provider latency varies widely)


@dataclass(frozen=True)
class StacCollection:
    id: str
    planet: str
    instrument: str
    data_type: str  # what the "dtm" asset is
    level: str  # GLOBAL | REGIONAL | LOCAL_HIGH_RESOLUTION
    vertical_datum: str  # as documented by the provider; never guessed
    units: str
    units_source: str
    docs_url: str
    notes: str


# Height reference statements are quoted from the collection descriptions (read 2026-11-15).
COLLECTIONS: dict[str, StacCollection] = {
    c.id: c
    for c in [
        StacCollection(
            id="mro_hirise_socet_dtms", planet="MARS", instrument="MRO HiRISE", data_type="DEM",
            level="LOCAL_HIGH_RESOLUTION",
            vertical_datum="NOT_DOCUMENTED in the STAC item (see the PDS HiRISE DTM label of the product)",
            units="m", units_source="PDS HiRISE DTM products store elevations in metres",
            docs_url=f"{DOCS_ROOT}/mars/hirise/",
            notes="Local stereo DTMs (~1-2 m posts) made by several producers; coverage and quality vary per product.",
        ),
        StacCollection(
            id="mro_ctx_controlled_usgs_dtms", planet="MARS", instrument="MRO CTX", data_type="DEM",
            level="REGIONAL",
            vertical_datum="MOLA-aligned (provider: 'absolutely controlled to MOLA' with ASP pc_align; file tag GEOID=mola)",
            units="m", units_source="Ames Stereo Pipeline DTM output is in metres",
            docs_url=f"{DOCS_ROOT}/mars/ctxdtms/",
            notes=("Stereo DTMs at ~20 m posts from ~6 m CTX images. Local coverage only. The provider warns that some "
                   "DTMs are jittery or have large gaps and are then no improvement over MOLA."),
        ),
        StacCollection(
            id="kaguya_terrain_camera_usgs_dtms_v2", planet="MOON", instrument="Kaguya/SELENE Terrain Camera", data_type="DEM",
            level="REGIONAL",
            vertical_datum="LOLA-aligned (provider: 'absolutely aligned to LOLA'); reference surface NOT_DOCUMENTED in the STAC item",
            units="m", units_source="STAC raster band unit 'meters'",
            docs_url=f"{DOCS_ROOT}/moon/kaguyatc_dtms/",
            notes=("Stereo DTMs between about 70N and 70S. Provider: mean vertical precision ~3 m, vertical offsets near "
                   "DTM edges; accuracy is reported per DTM (qa_metrics asset)."),
        ),
    ]
}


def collections_for(planet: str, data_type: str | None = None) -> list[StacCollection]:
    return [c for c in COLLECTIONS.values() if c.planet == planet and (data_type in (None, c.data_type))]


class StacError(Exception):
    def __init__(self, message: str, code: str = "PROVIDER_ERROR"):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ geometry
def normalize_lon(lon: float) -> float:
    """Longitude in -180..180 (the convention of STAC/GeoJSON footprints)."""
    return ((lon + 180.0) % 360.0) - 180.0


def split_bbox(west: float, south: float, east: float, north: float) -> list[tuple[float, float, float, float]]:
    """A lon/lat box in -180..180 terms, split in two where it crosses the antimeridian."""
    if east - west >= 360:
        return [(-180.0, south, 180.0, north)]
    w, e = normalize_lon(west), normalize_lon(east)
    if e == -180.0 and east > west:
        e = 180.0
    if w <= e:
        return [(w, south, e, north)]
    return [(w, south, 180.0, north), (-180.0, south, e, north)]


def _rings(geometry: dict | None) -> list[list[list[float]]]:
    if not geometry:
        return []
    if geometry.get("type") == "Polygon":
        return [geometry["coordinates"][0]]
    if geometry.get("type") == "MultiPolygon":
        return [poly[0] for poly in geometry["coordinates"]]
    return []


def point_in_footprint(geometry: dict | None, lon: float, lat: float) -> bool:
    """Even-odd test against the outer ring(s). Footprints here are small (no pole/seam cases:
    a polygon touching the antimeridian is published as a MultiPolygon by the provider)."""
    lon = normalize_lon(lon)
    for ring in _rings(geometry):
        inside = False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
        if inside:
            return True
    return False


# ------------------------------------------------------------------ items
def normalize_item(item: dict) -> dict | None:
    """One STAC item -> registry record. None when the item has no DTM asset we can read."""
    coll = COLLECTIONS.get(item.get("collection", ""))
    assets = item.get("assets") or {}
    dtm = assets.get("dtm")
    if not coll or not dtm or "geotiff" not in (dtm.get("type") or ""):
        return None
    props = item.get("properties") or {}
    band = (dtm.get("raster:bands") or [{}])[0]
    stats = band.get("statistics") or {}
    valid_pct = stats.get("valid_percent")
    orthos = [
        {"key": k, "href": a["href"]}
        for k, a in assets.items()
        if "ortho" in k.lower() and "geotiff" in (a.get("type") or "")
    ]
    self_link = next((l["href"] for l in item.get("links", []) if l.get("rel") == "self"), None)
    wkt = props.get("proj:wkt2") or ""
    crs_name = wkt.split('"')[1] if wkt.count('"') >= 2 else None
    if valid_pct is None:
        quality = "NOT_DOCUMENTED"
    elif valid_pct >= 90:
        quality = "MOSTLY_COMPLETE"
    elif valid_pct >= 50:
        quality = "PARTIAL_GAPS"
    else:
        quality = "LARGE_GAPS"
    return {
        "planet_id": coll.planet,
        "dataset_id": coll.id,
        "product_id": item["id"],
        "provider": PROVIDER,
        "source": "USGS Astrogeology Analysis Ready Data",
        "instrument": coll.instrument,
        "data_type": coll.data_type,
        "level": coll.level,
        "format": "Cloud-Optimized GeoTIFF",
        "resolution_m": props.get("gsd"),
        "effective_accuracy": "NOT_DOCUMENTED",
        "footprint": item.get("geometry"),
        "bbox": item.get("bbox"),
        "crs": crs_name or "NOT_DOCUMENTED in the STAC item (read from the file on first use)",
        "latitude_type": "PLANETOCENTRIC" if "Ocentric" in wkt else "NOT_DOCUMENTED",
        "longitude_convention": "EAST_POSITIVE",
        "vertical_datum": coll.vertical_datum,
        "units": coll.units,
        "units_source": coll.units_source,
        "license": props.get("license") or "NOT_DOCUMENTED",
        "attribution": "USGS Astrogeology Science Center" + (f"; {', '.join(props['missions'])}" if props.get("missions") else ""),
        "time_range": {"start": props.get("start_datetime"), "end": props.get("end_datetime"), "datetime": props.get("datetime")},
        "title": props.get("title") or item["id"],
        "quality_status": quality,
        "quality": {
            "valid_percent": valid_pct,
            "elevation_min_m": stats.get("minimum"),
            "elevation_max_m": stats.get("maximum"),
            "qa_metrics_url": (assets.get("qa_metrics") or {}).get("href"),
            "provenance_url": (assets.get("provenance") or {}).get("href"),
            "note": coll.notes,
        },
        "dem_available": True,
        "imagery_available": bool(orthos),
        "assets": {
            "dem": dtm["href"],
            "orthoimages": orthos,
            "hillshade": (assets.get("hillshade") or assets.get("image") or {}).get("href"),
            "thumbnail": (assets.get("thumbnail") or {}).get("href"),
        },
        "source_url": self_link,
        "docs_url": coll.docs_url,
        "local_file": None,
        "status": "ONLINE_SOURCE",
    }


def _fetch(params: dict) -> dict:
    key = "stac:" + hashlib.sha1(json.dumps(params, sort_keys=True).encode()).hexdigest()
    hit = cache.get(key)
    if hit is not None:
        return hit
    data = None
    for attempt in (1, 2):  # the provider is occasionally slow: one retry on a timeout, never more
        try:
            data = http_client.get_json(PROVIDER, f"{API_ROOT}/search", params, timeout=REQUEST_TIMEOUT_S)
            break
        except http_client.ProviderTimeout as exc:
            if attempt == 2:
                raise StacError(str(exc), exc.code) from exc
        except http_client.ProviderError as exc:
            raise StacError(str(exc), exc.code) from exc
    if not isinstance(data, dict) or not isinstance(data.get("features"), list):
        raise StacError(f"{PROVIDER} returned an unexpected document", "PROVIDER_BAD_RESPONSE")
    cache.set(key, data, CACHE_TTL_S)
    return data


def search(
    planet: str,
    bbox: tuple[float, float, float, float] | None = None,
    point: tuple[float, float] | None = None,
    data_type: str | None = None,
    max_resolution_m: float | None = None,
    collections: list[str] | None = None,
    limit: int = 50,
) -> dict:
    """Products of ``planet`` intersecting a bbox (west,south,east,north) or containing a point.

    Returns {"products": [...], "matched": n|None, "truncated": bool, "collections": [...]}.
    Coordinates are planetocentric degrees, east-positive, any longitude range."""
    colls = [c for c in collections_for(planet, data_type) if not collections or c.id in collections]
    if not colls:
        return {"products": [], "matched": 0, "truncated": False, "collections": []}
    limit = max(1, min(int(limit), MAX_LIMIT))
    if point is not None:
        lon = normalize_lon(point[0])
        eps = 1e-4
        boxes = [(lon - eps, point[1] - eps, lon + eps, point[1] + eps)]
    elif bbox is not None:
        boxes = split_bbox(*bbox)
    else:
        raise ValueError("bbox or point is required")
    products: dict[tuple[str, str], dict] = {}
    matched, truncated = 0, False
    # One request per collection and box, run concurrently: provider latency dominates.
    jobs = [(coll, {"collections": coll.id, "bbox": ",".join(f"{v:.6f}" for v in box), "limit": limit}) for coll in colls for box in boxes]
    if len(jobs) > 1:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            pages = list(pool.map(lambda j: _fetch(j[1]), jobs))  # the first StacError propagates
    else:
        pages = [_fetch(jobs[0][1])]
    for data in pages:
        n = data.get("numberMatched")
        matched += n if isinstance(n, int) else len(data["features"])
        truncated = truncated or (isinstance(n, int) and n > len(data["features"]))
        for item in data["features"]:
            rec = normalize_item(item)
            if rec is None:
                continue
            if point is not None and not point_in_footprint(rec["footprint"], point[0], point[1]):
                continue
            if max_resolution_m is not None and (rec["resolution_m"] is None or rec["resolution_m"] > max_resolution_m):
                continue
            products[(rec["dataset_id"], rec["product_id"])] = rec
    out = sorted(products.values(), key=lambda r: (r["resolution_m"] is None, r["resolution_m"] or 0.0))
    return {"products": out, "matched": matched, "truncated": truncated, "collections": [c.id for c in colls]}


def get_product(collection: str, product_id: str) -> dict:
    """One product by id (cached). Raises StacError when it does not exist or has no DTM."""
    if collection not in COLLECTIONS:
        raise StacError("Unknown collection", "NOT_FOUND")
    data = _fetch({"collections": collection, "ids": product_id, "limit": 1})
    for item in data["features"]:
        if item.get("id") == product_id:
            rec = normalize_item(item)
            if rec:
                return rec
    raise StacError("Product not found in the catalogue", "NOT_FOUND")
