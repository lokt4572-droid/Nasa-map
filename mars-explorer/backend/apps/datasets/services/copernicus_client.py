"""Earth elevation: Copernicus DEM GLO-30 Public, as Cloud-Optimized GeoTIFFs in the AWS Open
Data registry (keyless; https://copernicus-dem-30m.s3.amazonaws.com/readme.html).

It is not a STAC service: tiles are found from the bucket's published tile list and the
1x1 degree tile naming scheme. Properties stated by the provider (read 2026-11-15):
- a Digital SURFACE Model: buildings, infrastructure and vegetation are included, so it is
  not bare-earth elevation;
- 1 arc-second posts (about 30 m), EPSG:4326, 1x1 degree tiles;
- ocean areas have NO tiles. The readme suggests assuming zero there; this application
  reports NO DATA instead and never invents heights;
- some countries are not in the public 30 m release.
Units and vertical datum are not stored in the files; they come from the Copernicus DEM
product specification (metres above the EGM2008 geoid) and are labelled with that source.
"""
from __future__ import annotations

import logging
import math
import time
from pathlib import Path

from django.conf import settings
from django.core.cache import cache

from services import http_client

from .stac_client import StacCollection, StacError, normalize_lon

logger = logging.getLogger("mars.copernicus")

PROVIDER = "Copernicus DEM GLO-30 Public (AWS Open Data)"
BUCKET = "https://copernicus-dem-30m.s3.amazonaws.com"
TILE_LIST_URL = f"{BUCKET}/tileList.txt"
TILE_LIST_TTL_S = 30 * 24 * 3600
MAX_CELLS = 400  # 1x1 degree cells examined per search
LICENSE = "Copernicus DEM licence (GLO-30 Public): free use with attribution"
ATTRIBUTION = ("© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS "
               "by the European Union and ESA; all rights reserved")

COLLECTION = StacCollection(
    id="copernicus_dem_glo30", planet="EARTH", instrument="TanDEM-X (Copernicus DEM)", data_type="DEM",
    level="REGIONAL",
    vertical_datum="EGM2008 geoid (Copernicus DEM product specification; not stated in the file)",
    units="m", units_source="Copernicus DEM product specification (not stated in the file)",
    docs_url=f"{BUCKET}/readme.html",
    notes=("Digital SURFACE model (buildings and vegetation included, not bare earth). 1x1 degree tiles at 1 arc-second. "
           "No tiles over oceans: reported as no data, never as zero. Some countries are not in the public 30 m release."),
)


def tile_id(lon: float, lat: float) -> str | None:
    """Name of the 1x1 degree tile whose south-west corner is (floor lon, floor lat)."""
    if not -90.0 <= lat < 90.0:
        return None
    la = math.floor(lat)
    lo = math.floor(normalize_lon(lon))
    return f"Copernicus_DSM_COG_10_{'N' if la >= 0 else 'S'}{abs(la):02d}_00_{'E' if lo >= 0 else 'W'}{abs(lo):03d}_00_DEM"


def tile_bounds(tid: str) -> tuple[float, float, float, float]:
    parts = tid.split("_")  # Copernicus DSM COG 10 N46 00 E007 00 DEM
    ns, ew = parts[4], parts[6]
    lat = int(ns[1:]) * (1 if ns[0] == "N" else -1)
    lon = int(ew[1:]) * (1 if ew[0] == "E" else -1)
    return (float(lon), float(lat), float(lon + 1), float(lat + 1))


def _cache_file() -> Path:
    d = Path(settings.MARS_DATA_DIR).parent / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / "copernicus_glo30_tilelist.txt"


def tile_list() -> frozenset[str]:
    """Published tile names (cached in memory 1 day and on disk 30 days)."""
    hit = cache.get("copernicus:tiles")
    if hit is not None:
        return hit
    f = _cache_file()
    text = None
    if f.is_file() and time.time() - f.stat().st_mtime < TILE_LIST_TTL_S:
        text = f.read_text(encoding="utf-8")
    else:
        try:
            text = http_client.get_bytes(PROVIDER, TILE_LIST_URL, timeout=30.0, max_bytes=5_000_000).decode("utf-8")
            f.write_text(text, encoding="utf-8")
        except http_client.ProviderError as exc:
            if f.is_file():  # an older list is better than none; the files are checked on read anyway
                text = f.read_text(encoding="utf-8")
                logger.warning("Copernicus tile list refresh failed (%s); using cached copy", exc)
            else:
                raise StacError(str(exc), exc.code) from exc
    tiles = frozenset(line.strip() for line in text.splitlines() if line.strip().startswith("Copernicus_DSM_COG_10_"))
    cache.set("copernicus:tiles", tiles, 24 * 3600)
    return tiles


def record(tid: str) -> dict:
    w, s, e, n = tile_bounds(tid)
    ring = [[w, s], [e, s], [e, n], [w, n], [w, s]]
    url = f"{BUCKET}/{tid}/{tid}.tif"
    return {
        "planet_id": "EARTH", "dataset_id": COLLECTION.id, "product_id": tid, "provider": PROVIDER,
        "source": "Copernicus Programme (ESA / EU), distributed via AWS Open Data", "instrument": COLLECTION.instrument,
        "data_type": "DEM", "level": "REGIONAL", "format": "Cloud-Optimized GeoTIFF",
        "resolution_m": round(math.radians(1 / 3600) * 6_371_008.8, 2),  # 1 arc-second N-S, nominal
        "effective_accuracy": "NOT_DOCUMENTED",
        "footprint": {"type": "Polygon", "coordinates": [ring]}, "bbox": [w, s, e, n],
        "crs": "EPSG:4326 (WGS 84)", "latitude_type": "PLANETOGRAPHIC", "longitude_convention": "EAST_POSITIVE",  # geodetic (WGS 84)
        "vertical_datum": COLLECTION.vertical_datum, "units": COLLECTION.units, "units_source": COLLECTION.units_source,
        "license": LICENSE, "attribution": ATTRIBUTION,
        "time_range": {"start": None, "end": None, "datetime": None},
        "title": f"Copernicus DEM GLO-30 tile {tid.split('_COG_10_')[1].removesuffix('_DEM')}",
        "quality_status": "NOT_DOCUMENTED",
        "quality": {"valid_percent": None, "note": COLLECTION.notes},
        "dem_available": True, "imagery_available": False,
        "assets": {"dem": url, "orthoimages": [], "hillshade": None, "thumbnail": None},
        "source_url": f"{BUCKET}/{tid}/", "docs_url": COLLECTION.docs_url,
        "local_file": None, "status": "ONLINE_SOURCE",
    }


def search(bbox=None, point=None, max_resolution_m=None, limit: int = 50) -> dict:
    tiles = tile_list()
    if point is not None:
        cells = [tile_id(point[0], point[1])]
    else:
        w, s, e, n = bbox
        lats = range(math.floor(max(s, -90)), math.ceil(min(n, 90)))
        lons = range(math.floor(w), math.ceil(e))
        if len(lats) * len(lons) > MAX_CELLS:
            raise StacError(f"Area too large for a tile search (more than {MAX_CELLS} 1x1 degree cells); zoom in", "AREA_TOO_LARGE")
        cells = [tile_id(lo + 0.5, la + 0.5) for la in lats for lo in lons]
    found = [c for c in cells if c and c in tiles]
    products = [record(t) for t in found[:limit]]
    if max_resolution_m is not None:
        products = [p for p in products if p["resolution_m"] <= max_resolution_m]
    return {"products": products, "matched": len(found), "truncated": len(found) > limit, "collections": [COLLECTION.id]}


def get_product(product_id: str) -> dict:
    if product_id not in tile_list():
        raise StacError("Tile not in the published Copernicus GLO-30 tile list", "NOT_FOUND")
    return record(product_id)
