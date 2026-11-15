"""Unified planetary data registry (v0.4): every dataset the application can show or analyse,
from every provider, in one record shape, plus the provider adapters and their protocols.

Record fields (fixed vocabulary): planet_id, dataset_id, provider, product_id, data_type, format,
resolution_m, resolution_text, effective_accuracy, coverage, crs, latitude_type,
longitude_convention, vertical_datum, units, license, attribution, time_range, local_file,
status, source_url.

Rules: resolution is grid spacing and is never reported as accuracy; effective_accuracy is
NOT_DOCUMENTED unless a source states it. Nothing here performs network requests: catalogue
collections are listed at collection level; their individual products are found by search.
"""
from __future__ import annotations

import math
import re

FIELDS = [
    "planet_id", "dataset_id", "provider", "product_id", "data_type", "format", "resolution_m", "resolution_text",
    "effective_accuracy", "coverage", "crs", "latitude_type", "longitude_convention", "vertical_datum", "units",
    "license", "attribution", "time_range", "local_file", "status", "source_url",
]
NOT_DOCUMENTED = "NOT_DOCUMENTED"

# Provider adapters. Each follows its provider's own protocol; not every archive has an API.
ADAPTERS = {
    "NASA_TREK": {"protocol": "OGC WMTS (REST tiles + GetCapabilities); catalogue search JSON", "status": "IMPLEMENTED",
                  "used_for": "2D imagery and colour-hillshade layers, globe textures", "module": "frontend services/marsMapService.ts"},
    "NASA_GIBS": {"protocol": "OGC WMTS (EPSG:3857 'best') with TIME dimension", "status": "IMPLEMENTED",
                  "used_for": "Earth satellite, atmosphere and geostationary imagery", "module": "backend services/gibs.py"},
    "NASA_PDS": {"protocol": "file archive (PDS3/PDS4 labels + images), no query API used", "status": "IMPLEMENTED (manual download + import_dem)",
                 "used_for": "MOLA MEGDR and other downloadable products", "module": "backend services/dataset_manager.py"},
    "USGS_ASTROGEOLOGY": {"protocol": "STAC API search + Cloud-Optimized GeoTIFF range reads", "status": "IMPLEMENTED",
                          "used_for": "CTX, HiRISE and Kaguya DTMs (Mars, Moon)", "module": "backend apps/datasets/services/stac_client.py"},
    "STAC": {"protocol": "STAC API 1.x (items search by bbox/point, collections)", "status": "IMPLEMENTED (USGS Astrogeology endpoint)",
             "used_for": "footprint discovery", "module": "backend apps/datasets/services/stac_client.py"},
    "COPERNICUS": {"protocol": "public tile list + 1x1 degree tile naming, COG range reads (AWS Open Data); no API key", "status": "IMPLEMENTED",
                   "used_for": "Earth elevation (Copernicus DEM GLO-30 Public)", "module": "backend apps/datasets/services/copernicus_client.py"},
    "CESIUM_ION": {"protocol": "Cesium ion REST (browser, user's token) streaming 3D Tiles / quantized-mesh", "status": "REQUIRES_USER_CONFIGURATION",
                   "used_for": "3D visualisation only (Earth terrain, Mars and Moon 3D Tiles); never analysis", "module": "frontend services/planetary/cesiumSceneService.ts"},
    "OPENPLANETARYMAP": {"protocol": "XYZ tiles", "status": "NOT_IMPLEMENTED",
                         "used_for": "—", "module": None, "reason": "Not needed: NASA Trek already provides the verified basemaps used here."},
    "LOCAL": {"protocol": "registered raster files (GDAL)", "status": "IMPLEMENTED", "used_for": "any validated DEM imported by the operator",
              "module": "backend services/dataset_manager.py"},
}

_UNIT = {"m": 1.0, "cm": 0.01, "km": 1000.0}


def resolution_m(text: str | None) -> float | None:
    """Metres from a stated spacing such as '463 m/px', '25 cm/px', '≈30 m'. None if not in metres."""
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(km|cm|m)\b(?!\s*/\s*deg)", text.replace(" ", " ").replace(" ", " "))
    if not m:
        return None
    return round(float(m.group(1).replace(",", ".")) * _UNIT[m.group(2)], 4)


def _rec(**kw) -> dict:
    base = {f: None for f in FIELDS}
    base["effective_accuracy"] = NOT_DOCUMENTED
    base.update(kw)
    if base["resolution_m"] is None:
        base["resolution_m"] = resolution_m(base.get("resolution_text"))
    return base


def _trek_records(planet: str) -> list[dict]:
    from services.planet_registry import PLANET_LAYERS

    lat_type = "AS_DECLARED_BY_SOURCE (Trek capabilities do not state it)" if planet == "MARS" else "PLANETOCENTRIC (sphere)"
    return [
        _rec(planet_id=planet, dataset_id=l["id"], provider="NASA_TREK", product_id=l["layer_id"],
             data_type="VISUALIZATION" if l["kind"] == "COLOR_HILLSHADE" else "IMAGERY", format=l["format"],
             resolution_text=l["resolution"], coverage=l["coverage"] + (f" ({l['region']})" if l.get("region") else ""),
             crs=l["crs"], latitude_type=lat_type, longitude_convention="EAST_POSITIVE_180",
             vertical_datum="n/a (image pixels are not elevations)", units="image", license="NASA public data",
             attribution="NASA Solar System Treks", time_range=None, local_file=None, status="ONLINE_SOURCE",
             source_url=l["capabilities_url"])
        for l in PLANET_LAYERS.get(planet, [])
    ]


def _gibs_records() -> list[dict]:
    from services import gibs

    return [
        _rec(planet_id="EARTH", dataset_id=w["id"], provider="NASA_GIBS", product_id=w["id"], data_type="IMAGERY",
             format="image/jpeg or image/png (per layer)", resolution_text="per GetCapabilities TileMatrixSet",
             coverage=w.get("coverage", "global"), crs="EPSG:3857", latitude_type="GEODETIC (WGS 84)",
             longitude_convention="EAST_POSITIVE_180", vertical_datum="n/a (imagery)", units="image",
             license="NASA open data; attribution requested", attribution=gibs.ATTRIBUTION,
             time_range="per layer TIME dimension (daily or 10-minute steps)", local_file=None, status="ONLINE_SOURCE",
             source_url=gibs.CAPS_URL)
        for w in gibs.WANTED
    ]


_PROVIDER_BY_SOURCE = [("PDS", "NASA_PDS"), ("USGS", "USGS_ASTROGEOLOGY"), ("Copernicus", "COPERNICUS"), ("ESA", "COPERNICUS"),
                       ("Treks", "NASA_TREK"), ("GIBS", "NASA_GIBS")]


def _catalog_records(planet: str) -> list[dict]:
    from apps.datasets.catalog import catalog_with_status

    out = []
    for e in catalog_with_status(planet):
        provider = next((p for k, p in _PROVIDER_BY_SOURCE if k in e["source"]), e["source"])
        out.append(_rec(
            planet_id=planet, dataset_id=e["key"], provider=provider, product_id=e["product_id"], data_type=e["data_type"],
            format="per product", resolution_text=e["resolution"], coverage=e["spatial_coverage"], crs=e["crs"],
            latitude_type="per product metadata", longitude_convention="per product metadata", vertical_datum=e["vertical_datum"],
            units=e["units"], license=e["license"], attribution=e["source"], time_range=e.get("temporal_coverage"),
            local_file="REGISTERED" if any(d["status"] == "VALID" for d in e.get("local_datasets", [])) else None,
            status=e["status"], source_url=e["url"],
        ))
    return out


def _collection_records(planet: str) -> list[dict]:
    from apps.datasets.services import catalogues, copernicus_client

    out = []
    for c in catalogues.collections_for(planet):
        earth = c.id == copernicus_client.COLLECTION.id
        out.append(_rec(
            planet_id=planet, dataset_id=c.id, provider="COPERNICUS" if earth else "USGS_ASTROGEOLOGY",
            product_id="per footprint (search by area)", data_type=c.data_type, format="Cloud-Optimized GeoTIFF",
            resolution_m=round(math.radians(1 / 3600) * 6_371_008.8, 2) if earth else None,
            resolution_text="1 arc-second (≈30 m)" if earth else "per product (catalogue gsd)",
            coverage="1x1 degree land tiles (no ocean tiles)" if earth else "local footprints only",
            crs="EPSG:4326" if earth else "per product (IAU 2015 WKT2 in the catalogue)",
            latitude_type="PLANETOGRAPHIC (geodetic WGS 84)" if earth else "PLANETOCENTRIC",
            longitude_convention="EAST_POSITIVE", vertical_datum=c.vertical_datum, units=c.units,
            license=copernicus_client.LICENSE if earth else "CC0-1.0",
            attribution=copernicus_client.ATTRIBUTION if earth else "USGS Astrogeology Science Center",
            time_range="per product", local_file=None, status="ONLINE_SOURCE (remote window reads)", source_url=c.docs_url,
        ))
    return out


CESIUM = {
    "EARTH": ("cesium-world-terrain", "Cesium World Terrain", "≈0.5–8 m in selected regions, ≈30 m regional, ≈30–90 m 60S–60N, ≈1 km global",
              "WGS 84 ellipsoid (heights are ellipsoidal)"),
    "MARS": ("cesium-mars-3644333", "Cesium Mars 3D Tiles (ion asset 3644333)", "global ≈232 m imagery / ≈200 m terrain; Jezero ≈6 / 20 m; Gale ≈0.25 / 1 m",
             "IAU_2015:49901"),
    "MOON": ("cesium-moon-2684829", "Cesium Moon 3D Tiles (ion asset 2684829)", "60N–60S ≈100 m imagery / ≈59 m terrain; poles down to ≈5 m terrain",
             "lunar sphere (CRS not documented by Cesium)"),
}


def _cesium_records(planet: str) -> list[dict]:
    if planet not in CESIUM:
        return []
    did, name, res, crs = CESIUM[planet]
    return [_rec(planet_id=planet, dataset_id=did, provider="CESIUM_ION", product_id=name, data_type="3D_VISUALIZATION",
                 format="3D Tiles" if planet != "EARTH" else "quantized-mesh terrain", resolution_text=res,
                 coverage="global, resolution varies by region", crs=crs, latitude_type="GEODETIC (ellipsoid)",
                 longitude_convention="EAST_POSITIVE_180", vertical_datum=crs, units="m",
                 license="Cesium ion Terms of Service (streaming only; no download or redistribution)",
                 attribution="Cesium; data NASA / USGS Astrogeology" if planet != "EARTH" else "Cesium World Terrain",
                 time_range=None, local_file=None, status="REQUIRES_USER_CONFIGURATION (browser token)",
                 source_url="https://cesium.com/platform/cesium-ion/content/")]


def _registered_records(planet: str) -> list[dict]:
    from apps.datasets.models import Dataset

    out = []
    for ds in Dataset.objects.filter(planet=planet):
        remote = ds.access == "REMOTE_COG"
        out.append(_rec(
            planet_id=planet, dataset_id=ds.name,
            provider="LOCAL" if not remote else next((p for k, p in _PROVIDER_BY_SOURCE if k in (ds.source or "")), "REMOTE"),
            product_id=ds.product_id or ds.name, data_type=ds.data_type, format=ds.driver or None,
            resolution_m=ds.resolution_meters, resolution_text=f"{ds.resolution_meters:.3f} m (from the file)" if ds.resolution_meters else None,
            coverage="registered raster bounds", crs=ds.crs_name or None, latitude_type=ds.latitude_convention,
            longitude_convention=ds.longitude_convention, vertical_datum=ds.vertical_datum, units=ds.units or None,
            license=ds.license or NOT_DOCUMENTED, attribution=ds.source or None,
            time_range=ds.observation_date.isoformat() if ds.observation_date else None,
            local_file=None if remote else "REGISTERED",  # server paths are never exposed
            status=ds.status, source_url=ds.source_url or ds.download_url or None,
        ))
    return out


def registry(planet: str, provider: str | None = None, data_type: str | None = None) -> list[dict]:
    recs = _registered_records(planet) + _collection_records(planet) + _catalog_records(planet) + _cesium_records(planet)
    recs += _trek_records(planet) if planet != "EARTH" else _gibs_records()
    if provider:
        recs = [r for r in recs if r["provider"] == provider]
    if data_type:
        recs = [r for r in recs if r["data_type"] == data_type]
    return recs
