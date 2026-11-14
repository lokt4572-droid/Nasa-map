"""Weather providers. Three categories are kept separate and labelled:

* Open-Meteo  — forecast_model (numerical weather model output for a grid cell).
* NASA POWER  — historical daily values (reanalysis/satellite-derived; the actual
                sources, e.g. MERRA-2 or GEOS-IT, are reported per response),
                not a forecast and not a local station measurement.
* NASA GIBS IMERG — satellite precipitation imagery (served as a map layer, see services/gibs.py).
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

from django.conf import settings
from django.utils import timezone

from services import http_client

from .models import WeatherSnapshot

logger = logging.getLogger("mars.weather")

OPEN_METEO_URL = getattr(settings, "OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")
POWER_URL = getattr(settings, "NASA_POWER_URL", "https://power.larc.nasa.gov/api/temporal/daily/point")

CURRENT_VARS = [
    "temperature_2m", "relative_humidity_2m", "apparent_temperature", "is_day", "precipitation", "rain",
    "showers", "snowfall", "weather_code", "cloud_cover", "pressure_msl", "surface_pressure",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
]
HOURLY_VARS = ["temperature_2m", "precipitation_probability", "precipitation", "cloud_cover", "wind_speed_10m", "wind_gusts_10m"]
DAILY_VARS = ["temperature_2m_max", "temperature_2m_min", "precipitation_sum", "precipitation_probability_max", "weather_code", "sunrise", "sunset"]
POWER_PARAMS = ["T2M", "RH2M", "PRECTOTCORR", "WS10M"]

FORECAST_TTL = dt.timedelta(minutes=15)
POWER_TTL = dt.timedelta(hours=24)
OPEN_METEO_ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0) — https://open-meteo.com/"
POWER_ATTRIBUTION = "Data: NASA Langley Research Center (LaRC) POWER Project, funded through the NASA Earth Science/Applied Science Program"
POWER_EARLIEST = dt.date(1981, 1, 1)
POWER_MAX_DAYS = 366


def _round(v: float) -> float:
    # 0.01 deg (~1 km) keeps the cache coherent; forecast model grids are much coarser.
    return round(v, 2)


def _cached(key: str):
    snap = WeatherSnapshot.objects.filter(key=key).first()
    if snap and snap.expires_at > timezone.now():
        return snap
    return None


def _store(key, provider, data_type, payload, ttl):
    now = timezone.now()
    snap, _ = WeatherSnapshot.objects.update_or_create(
        key=key, defaults=dict(provider=provider, data_type=data_type, payload=payload, retrieved_at=now, expires_at=now + ttl)
    )
    return snap


def _envelope(snap, lat, lon, data: dict, units: dict, valid_time, timezone_name, extra=None) -> dict:
    age = (timezone.now() - snap.retrieved_at).total_seconds()
    return {
        "provider": snap.provider,
        "data_type": snap.data_type,
        "coordinates": {"latitude": lat, "longitude": lon},
        "valid_time": valid_time,
        "retrieved_at": snap.retrieved_at.isoformat(),
        "cache_age_s": round(age, 1),
        "from_cache": age > 1.0,
        "timezone": timezone_name,
        "units": units,
        "data": data,
        "attribution": OPEN_METEO_ATTRIBUTION if snap.provider == "Open-Meteo" else POWER_ATTRIBUTION,
        **(extra or {}),
    }


def open_meteo_forecast(lat: float, lon: float) -> tuple[Any, float, float]:
    lat, lon = _round(lat), _round(lon)
    key = f"om:{lat}:{lon}"
    snap = _cached(key)
    if not snap:
        payload = http_client.get_json("Open-Meteo", OPEN_METEO_URL, {
            "latitude": lat, "longitude": lon,
            "current": ",".join(CURRENT_VARS), "hourly": ",".join(HOURLY_VARS), "daily": ",".join(DAILY_VARS),
            "forecast_days": 7, "timezone": "auto",
        }, timeout=15.0)
        if not isinstance(payload, dict) or "current" not in payload:
            raise http_client.ProviderBadResponse("Open-Meteo", "Open-Meteo response has no 'current' block")
        snap = _store(key, "Open-Meteo", "forecast_model", payload, FORECAST_TTL)
    return snap, lat, lon


def _missing(block: dict | None, wanted: list[str]) -> list[str]:
    block = block or {}
    return [v for v in wanted if v not in block]


def current(lat: float, lon: float) -> dict:
    snap, lat, lon = open_meteo_forecast(lat, lon)
    p = snap.payload
    cur = {k: v for k, v in (p.get("current") or {}).items() if k not in ("time", "interval")}
    return _envelope(snap, lat, lon, cur, {k: v for k, v in (p.get("current_units") or {}).items() if k not in ("time", "interval")},
                     (p.get("current") or {}).get("time"), p.get("timezone"), {
                         "model_grid_cell": {"latitude": p.get("latitude"), "longitude": p.get("longitude"), "elevation_m": p.get("elevation")},
                         "missing_variables": _missing(p.get("current"), CURRENT_VARS),
                         "today": {k: (p.get("daily") or {}).get(k, [None])[0] for k in ("sunrise", "sunset", "precipitation_probability_max")},
                         "note": "Model forecast for the grid cell, not a measurement at the point.",
                     })


def forecast(lat: float, lon: float) -> dict:
    snap, lat, lon = open_meteo_forecast(lat, lon)
    p = snap.payload
    return _envelope(snap, lat, lon, {"hourly": p.get("hourly"), "daily": p.get("daily")},
                     {"hourly": p.get("hourly_units"), "daily": p.get("daily_units")}, None, p.get("timezone"), {
                         "model_grid_cell": {"latitude": p.get("latitude"), "longitude": p.get("longitude"), "elevation_m": p.get("elevation")},
                         "missing_variables": _missing(p.get("hourly"), HOURLY_VARS) + _missing(p.get("daily"), DAILY_VARS),
                         "forecast_days": 7,
                     })


def parse_date(value: str, name: str) -> dt.date:
    for fmt in ("%Y-%m-%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except (TypeError, ValueError):
            continue
    raise ValueError(f"{name} must be YYYY-MM-DD")


def historical(lat: float, lon: float, start: dt.date, end: dt.date) -> dict:
    if start > end:
        raise ValueError("start must not be after end")
    if start < POWER_EARLIEST:
        raise ValueError(f"NASA POWER daily data start on {POWER_EARLIEST.isoformat()}")
    if end > dt.date.today():
        raise ValueError("end must not be in the future (historical data only)")
    if (end - start).days + 1 > POWER_MAX_DAYS:
        raise ValueError(f"at most {POWER_MAX_DAYS} days per request")
    lat, lon = _round(lat), _round(lon)
    key = f"power:{lat}:{lon}:{start:%Y%m%d}:{end:%Y%m%d}"
    snap = _cached(key)
    if not snap:
        payload = http_client.get_json("NASA POWER", POWER_URL, {
            "parameters": ",".join(POWER_PARAMS), "community": "RE", "longitude": lon, "latitude": lat,
            "start": f"{start:%Y%m%d}", "end": f"{end:%Y%m%d}", "format": "JSON",
        }, timeout=30.0)
        if not isinstance(payload, dict) or "properties" not in payload:
            raise http_client.ProviderBadResponse("NASA POWER", "POWER response has no 'properties' block")
        snap = _store(key, "NASA POWER", "historical_reanalysis", payload, POWER_TTL)
    p = snap.payload
    fill = (p.get("header") or {}).get("fill_value", -999.0)
    params = (p.get("properties") or {}).get("parameter") or {}
    days = sorted({d for series in params.values() for d in series})
    series = {
        name: [None if (params.get(name, {}).get(d) is None or params[name][d] == fill) else params[name][d] for d in days]
        for name in POWER_PARAMS
    }
    meta = p.get("parameters") or {}
    return _envelope(snap, lat, lon, {"dates": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in days], "series": series},
                     {k: (meta.get(k) or {}).get("units") for k in POWER_PARAMS}, None, (p.get("header") or {}).get("time_standard"), {
                         "long_names": {k: (meta.get(k) or {}).get("longname") for k in POWER_PARAMS},
                         "sources": (p.get("header") or {}).get("sources"),
                         "fill_value": fill,
                         "missing_variables": [k for k in POWER_PARAMS if k not in params],
                         "note": "Daily reanalysis/satellite-derived values on a coarse grid; not a forecast and not station data.",
                     })


def status() -> dict:
    now = timezone.now()
    out = {}
    for prov in ("Open-Meteo", "NASA POWER"):
        qs = WeatherSnapshot.objects.filter(provider=prov)
        last = qs.order_by("-retrieved_at").first()
        out[prov] = {
            "cached_responses": qs.count(),
            "fresh_responses": qs.filter(expires_at__gt=now).count(),
            "last_success": last.retrieved_at.isoformat() if last else None,
        }
    return {
        "providers": out,
        "endpoints": {"Open-Meteo": OPEN_METEO_URL, "NASA POWER": POWER_URL},
        "ttl_s": {"forecast": FORECAST_TTL.total_seconds(), "historical": POWER_TTL.total_seconds()},
        "terms": {
            "Open-Meteo": "Free tier: non-commercial use, < 10 000 calls/day, < 5 000/h, < 600/min; CC BY 4.0 attribution required.",
            "NASA POWER": "Public NASA data; cite the POWER project.",
        },
    }
