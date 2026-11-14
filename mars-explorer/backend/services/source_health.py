"""Availability probes for external services (cached; never run more often than needed).

Nominatim is deliberately NOT probed: its usage policy forbids non-user-triggered requests.
"""
from __future__ import annotations

import time

from django.core.cache import cache

from services import http_client

PROBES = {
    "NASA Trek WMTS (Mars)": "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/0/0/0.jpg",
    "NASA GIBS WMTS": "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_NextGeneration/default/GoogleMapsCompatible_Level8/0/0/0.jpeg",
    "Open-Meteo": "https://api.open-meteo.com/v1/forecast?latitude=0&longitude=0&current=temperature_2m",
    "USGS Astrogeology STAC": "https://stac.astrogeology.usgs.gov/api/collections/mro_ctx_controlled_usgs_dtms",
    "NASA POWER": "https://power.larc.nasa.gov/api/temporal/daily/point?parameters=T2M&community=RE&longitude=0&latitude=0&start=20240101&end=20240101&format=JSON",
}
TTL_S = 600


def check_sources(force: bool = False) -> dict:
    cached = cache.get("source_health")
    if cached and not force:
        return {**cached, "from_cache": True}
    results = {}
    for name, url in PROBES.items():
        t0 = time.monotonic()
        try:
            http_client.get_bytes(name, url, timeout=8.0, max_bytes=5_000_000)
            results[name] = {"status": "UP", "latency_ms": round((time.monotonic() - t0) * 1000)}
        except http_client.ProviderError as exc:
            results[name] = {"status": "DOWN", "error": str(exc), "code": exc.code}
    results["Cesium ion"] = {"status": "NOT_PROBED", "reason": "used by the browser with the user's own token; the backend never holds it"}
    results["Nominatim"] = {"status": "NOT_PROBED", "reason": "usage policy: only user-triggered searches"}
    out = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sources": results, "cache_ttl_s": TTL_S}
    cache.set("source_health", out, TTL_S)
    return {**out, "from_cache": False}
