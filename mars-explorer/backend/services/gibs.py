"""NASA GIBS layer discovery from the real WMTS GetCapabilities (EPSG:3857, "best").

We never ship a hard-coded tile configuration: a curated list of WANTED identifiers is
checked against the live capabilities, and only layers that are actually present are
returned, with their TileMatrixSet, format, URL template and TIME domain as published.

The capabilities document is ~5.6 MB, so it is cached on disk for 24 h and parsed once
per process. Time intervals are returned as published ("start/end/period") so the client
can only select dates that exist; "latest" is the end of the last interval — it can lag
behind today (e.g. IMERG daily precipitation lagged 2 days on 2026-11-14).

Docs: https://nasa-gibs.github.io/gibs-api-docs/
"""
from __future__ import annotations

import logging
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from django.conf import settings

from services import http_client

logger = logging.getLogger("mars.gibs")

CAPS_URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi?SERVICE=WMTS&REQUEST=GetCapabilities"
NS = {"w": "http://www.opengis.net/wmts/1.0", "ows": "http://www.opengis.net/ows/1.1"}
CACHE_TTL_S = 24 * 3600
ATTRIBUTION = "Imagery: NASA Global Imagery Browse Services (GIBS), part of NASA EOSDIS"

# Curated selection. instrument/platform are read from the GIBS identifier names.
WANTED: list[dict[str, str]] = [
    {"id": "MODIS_Terra_CorrectedReflectance_TrueColor", "group": "SATELLITE", "title": "MODIS Terra True Color", "instrument": "MODIS", "platform": "Terra"},
    {"id": "MODIS_Aqua_CorrectedReflectance_TrueColor", "group": "SATELLITE", "title": "MODIS Aqua True Color", "instrument": "MODIS", "platform": "Aqua"},
    {"id": "VIIRS_NOAA20_CorrectedReflectance_TrueColor", "group": "SATELLITE", "title": "VIIRS NOAA-20 True Color", "instrument": "VIIRS", "platform": "NOAA-20"},
    {"id": "VIIRS_SNPP_CorrectedReflectance_TrueColor", "group": "SATELLITE", "title": "VIIRS Suomi NPP True Color", "instrument": "VIIRS", "platform": "Suomi NPP"},
    {"id": "BlueMarble_NextGeneration", "group": "SATELLITE", "title": "Blue Marble Next Generation (static composite)", "instrument": "MODIS (composite)", "platform": "Terra/Aqua"},
    {"id": "BlueMarble_ShadedRelief_Bathymetry", "group": "SATELLITE", "title": "Blue Marble Shaded Relief + Bathymetry (static)", "instrument": "composite", "platform": "—"},
    {"id": "MODIS_Terra_Cloud_Fraction_Day", "group": "ATMOSPHERE", "title": "Cloud Fraction (Day), MODIS Terra", "instrument": "MODIS", "platform": "Terra"},
    {"id": "MODIS_Combined_Value_Added_AOD", "group": "ATMOSPHERE", "title": "Aerosol Optical Depth, MODIS combined value-added", "instrument": "MODIS", "platform": "Terra + Aqua"},
    {"id": "OMI_Aerosol_Index", "group": "ATMOSPHERE", "title": "UV Aerosol Index (absorbing aerosols: dust, smoke), OMI", "instrument": "OMI", "platform": "Aura"},
    {"id": "AMSRU2_Columnar_Water_Vapor_Day", "group": "ATMOSPHERE", "title": "Columnar Water Vapor (Day), AMSR2", "instrument": "AMSR2", "platform": "GCOM-W1"},
    {"id": "IMERG_Precipitation_Rate", "group": "PRECIPITATION", "title": "Precipitation Rate (daily), GPM IMERG", "instrument": "GPM IMERG (multi-satellite)", "platform": "GPM constellation"},
    # Sub-daily (published at 10-minute steps). Geostationary: each covers only its satellite's
    # full disc, not the globe. Band 13 (10.3 um) is thermal infrared: day and night, not colour.
    {"id": "GOES-East_ABI_Band13_Clean_Infrared", "group": "GEOSTATIONARY", "title": "Clean infrared, GOES-East ABI band 13 (10-minute)", "instrument": "ABI", "platform": "GOES-East",
     "coverage": "GOES-East full disc (about 75 W): the Americas and the Atlantic"},
    {"id": "GOES-West_ABI_Band13_Clean_Infrared", "group": "GEOSTATIONARY", "title": "Clean infrared, GOES-West ABI band 13 (10-minute)", "instrument": "ABI", "platform": "GOES-West",
     "coverage": "GOES-West full disc (about 137 W): the eastern Pacific and western Americas"},
    {"id": "Himawari_AHI_Band13_Clean_Infrared", "group": "GEOSTATIONARY", "title": "Clean infrared, Himawari AHI band 13 (10-minute)", "instrument": "AHI", "platform": "Himawari",
     "coverage": "Himawari full disc (about 141 E): East Asia, Australia and the western Pacific"},
    {"id": "Reference_Labels_15m", "group": "REFERENCE", "title": "Place labels (reference)", "instrument": "—", "platform": "—"},
    {"id": "Reference_Features_15m", "group": "REFERENCE", "title": "Borders and roads (reference)", "instrument": "—", "platform": "—"},
    {"id": "Coastlines_15m", "group": "REFERENCE", "title": "Coastlines (reference)", "instrument": "—", "platform": "—"},
]

_lock = threading.Lock()
_parsed: dict[str, Any] = {"at": 0.0, "layers": None, "fetched_at": None}


def _cache_file() -> Path:
    d = Path(settings.MARS_DATA_DIR).parent / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / "gibs_epsg3857_capabilities.xml"


def _load_caps_bytes(refresh: bool) -> tuple[bytes, float]:
    f = _cache_file()
    if not refresh and f.is_file() and time.time() - f.stat().st_mtime < CACHE_TTL_S:
        return f.read_bytes(), f.stat().st_mtime
    data = http_client.get_bytes("NASA GIBS", CAPS_URL, timeout=60.0, max_bytes=30_000_000)
    f.write_bytes(data)
    return data, time.time()


def _interval_list(values: list[str]) -> list[dict[str, str]]:
    out = []
    for v in values:
        parts = v.split("/")
        if len(parts) == 3:
            out.append({"start": parts[0], "end": parts[1], "period": parts[2]})
        else:
            out.append({"start": parts[0], "end": parts[0], "period": ""})
    return out


def max_level_resolution_m(tms: str) -> float | None:
    """Ground size of a pixel at the equator for GoogleMapsCompatible_LevelN (Web Mercator)."""
    try:
        level = int(tms.rsplit("Level", 1)[1])
    except (IndexError, ValueError):
        return None
    return round(2 * 3.141592653589793 * 6378137 / (256 * 2 ** level), 1)


def parse_capabilities(xml_bytes: bytes) -> dict[str, dict]:
    root = ET.fromstring(xml_bytes)
    found: dict[str, dict] = {}
    wanted = {w["id"] for w in WANTED}
    for layer in root.iterfind(".//w:Contents/w:Layer", NS):
        ident = layer.findtext("ows:Identifier", namespaces=NS)
        if ident not in wanted:
            continue
        tms = layer.findtext("w:TileMatrixSetLink/w:TileMatrixSet", namespaces=NS) or ""
        res = layer.find("w:ResourceURL", NS)
        dim = layer.find("w:Dimension", NS)
        time_info = None
        if dim is not None and (dim.findtext("ows:Identifier", namespaces=NS) or "").lower() == "time":
            intervals = _interval_list([v.text or "" for v in dim.findall("w:Value", NS)])
            time_info = {
                "default": dim.findtext("w:Default", namespaces=NS),
                "intervals": intervals,
                "first": intervals[0]["start"] if intervals else None,
                "latest": intervals[-1]["end"] if intervals else None,
                "daily": all(i["period"] in ("P1D", "") for i in intervals) and "T" not in (intervals[-1]["end"] if intervals else ""),
            }
        found[ident] = {
            "tile_matrix_set": tms,
            "max_zoom": int(tms.rsplit("Level", 1)[1]) if "Level" in tms else None,
            "pixel_size_at_equator_m": max_level_resolution_m(tms),
            "format": layer.findtext("w:Format", namespaces=NS),
            "template": res.get("template") if res is not None else None,
            "time": time_info,
        }
    return found


def discover(refresh: bool = False) -> dict[str, Any]:
    with _lock:
        if _parsed["layers"] is None or refresh or time.time() - _parsed["at"] > CACHE_TTL_S:
            data, fetched = _load_caps_bytes(refresh)
            _parsed.update(layers=parse_capabilities(data), at=time.time(), fetched_at=fetched)
        caps = _parsed["layers"]
        fetched_at = _parsed["fetched_at"]
    layers = []
    for w in WANTED:
        info = caps.get(w["id"])
        layers.append({
            **w,
            "status": "AVAILABLE" if info else "NOT_IN_CAPABILITIES",
            "crs": "EPSG:3857",
            "source": "NASA GIBS",
            "attribution": ATTRIBUTION,
            **(info or {}),
            "temporal": "static (no TIME dimension)" if info and not info["time"] else ("time-enabled" if info else None),
        })
    return {
        "capabilities_url": CAPS_URL,
        "capabilities_fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(fetched_at)) if fetched_at else None,
        "layers": layers,
        "note": "Most recent dates may have partial coverage; dates outside the published intervals have no imagery.",
    }
