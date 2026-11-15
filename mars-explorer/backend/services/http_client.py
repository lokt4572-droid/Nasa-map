"""Small, dependency-free HTTP client for external providers (stdlib urllib).

* explicit timeout on every call;
* identifying User-Agent (required by OSM/Nominatim policies);
* typed errors so views can return clear messages instead of 500s.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger("mars.http")


class ProviderError(Exception):
    code = "PROVIDER_ERROR"

    def __init__(self, provider: str, message: str):
        super().__init__(message)
        self.provider = provider


class ProviderTimeout(ProviderError):
    code = "PROVIDER_TIMEOUT"


class ProviderHTTPError(ProviderError):
    code = "PROVIDER_HTTP_ERROR"

    def __init__(self, provider: str, message: str, status: int):
        super().__init__(provider, message)
        self.status = status


class ProviderBadResponse(ProviderError):
    code = "PROVIDER_BAD_RESPONSE"


def user_agent() -> str:
    return getattr(settings, "HTTP_USER_AGENT", "MARS-EXPLORER/0.2 (planetary GIS prototype)")


def get_bytes(provider: str, url: str, params: dict | None = None, timeout: float = 15.0, max_bytes: int = 20_000_000) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - URLs come from settings
            data = resp.read(max_bytes + 1)
    except urllib.error.HTTPError as exc:
        raise ProviderHTTPError(provider, f"{provider} returned HTTP {exc.code}", exc.code) from exc
    except TimeoutError as exc:
        raise ProviderTimeout(provider, f"{provider} did not answer within {timeout:.0f} s") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise ProviderTimeout(provider, f"{provider} did not answer within {timeout:.0f} s") from exc
        raise ProviderError(provider, f"{provider} unreachable: {exc.reason}") from exc
    if len(data) > max_bytes:
        raise ProviderBadResponse(provider, f"{provider} response larger than {max_bytes} bytes")
    return data


def get_json(provider: str, url: str, params: dict | None = None, timeout: float = 15.0) -> Any:
    raw = get_bytes(provider, url, params, timeout, max_bytes=10_000_000)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderBadResponse(provider, f"{provider} returned invalid JSON") from exc
