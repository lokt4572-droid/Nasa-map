"""Nominatim search proxy that follows the OSMF usage policy
(https://operations.osmfoundation.org/policies/nominatim/):

* absolute maximum 1 request/second for the whole backend (global lock);
* identifying User-Agent (settings.HTTP_USER_AGENT);
* results cached (24 h) — repeated searches never hit the server;
* only explicit, user-triggered searches: no autocomplete endpoint exists here;
* service URL configurable (NOMINATIM_URL) to switch to an own instance.
"""
from __future__ import annotations

import threading
import time

from django.conf import settings
from django.core.cache import cache

from services import http_client

ATTRIBUTION = "Search © OpenStreetMap contributors (ODbL), Nominatim"
MIN_INTERVAL_S = 1.0
_lock = threading.Lock()
_last = {"t": 0.0}


class RateLimited(Exception):
    pass


def nominatim_url() -> str:
    return getattr(settings, "NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")


def search(q: str, limit: int = 8) -> dict:
    key = f"geocode:{q.strip().lower()}:{limit}"
    hit = cache.get(key)
    if hit is not None:
        return {**hit, "from_cache": True}
    with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last["t"])
        if wait > 0:
            if wait > MIN_INTERVAL_S:  # pragma: no cover - defensive
                raise RateLimited()
            time.sleep(wait)
        _last["t"] = time.monotonic()
        raw = http_client.get_json("Nominatim", nominatim_url(), {"q": q, "format": "jsonv2", "limit": limit, "addressdetails": 0}, timeout=10.0)
    if not isinstance(raw, list):
        raise http_client.ProviderBadResponse("Nominatim", "Unexpected Nominatim response")
    results = []
    for r in raw:
        try:
            bbox = [float(v) for v in r.get("boundingbox", [])]  # south, north, west, east
            results.append({
                "name": r.get("display_name"),
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "category": r.get("category") or r.get("class"),
                "type": r.get("type"),
                "bbox": {"south": bbox[0], "north": bbox[1], "west": bbox[2], "east": bbox[3]} if len(bbox) == 4 else None,
            })
        except (KeyError, TypeError, ValueError):
            continue
    out = {"query": q, "provider": "Nominatim", "endpoint": nominatim_url(), "attribution": ATTRIBUTION, "results": results}
    cache.set(key, out, 24 * 3600)
    return {**out, "from_cache": False}
