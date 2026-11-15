"""One way to open a raster: a local file or an allow-listed remote Cloud-Optimized GeoTIFF.

Remote rasters are read with HTTP range requests (GDAL /vsicurl/): only the header and the
blocks of the requested window travel over the network. Nothing is downloaded in bulk and
nothing is cached on disk. Only hosts in ``REMOTE_RASTER_HOSTS`` are ever contacted, so a
dataset row cannot make the server fetch an arbitrary URL.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings

# USGS Astrogeology Analysis Ready Data bucket (STAC assets, CC0-1.0).
DEFAULT_HOSTS = ("astrogeo-ard.s3-us-west-2.amazonaws.com",)

GDAL_REMOTE_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",  # no directory listing requests
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.tiff",
    "GDAL_HTTP_TIMEOUT": "30",
    "GDAL_HTTP_CONNECTTIMEOUT": "10",
    "GDAL_HTTP_MAX_RETRY": "2",
    "GDAL_HTTP_RETRY_DELAY": "1",
    "VSI_CACHE": "TRUE",
}


class RemoteRasterError(RuntimeError):
    """The remote raster is not allowed or could not be opened."""


def allowed_hosts() -> tuple[str, ...]:
    return tuple(getattr(settings, "REMOTE_RASTER_HOSTS", DEFAULT_HOSTS))


def remote_enabled() -> bool:
    return bool(getattr(settings, "REMOTE_DEM_ENABLED", True))


def is_remote(path) -> bool:
    return str(path).lower().startswith(("https://", "http://"))


def check_remote_url(url: str) -> str:
    """Return the URL if it is HTTPS on an allow-listed host with a GeoTIFF path, else raise."""
    u = urlparse(str(url))
    if u.scheme != "https" or (u.hostname or "") not in allowed_hosts():
        raise RemoteRasterError("Remote raster host is not allow-listed")
    if u.username or u.password or u.query or u.fragment:
        raise RemoteRasterError("Remote raster URL must not carry credentials or a query string")
    if not u.path.lower().endswith((".tif", ".tiff")):
        raise RemoteRasterError("Remote raster must be a GeoTIFF")
    return str(url)


def file_available(path) -> bool:
    """A local file exists, or a remote URL is allowed (its reachability is checked on read)."""
    if is_remote(path):
        try:
            check_remote_url(str(path))
        except RemoteRasterError:
            return False
        return remote_enabled()
    return Path(str(path)).is_file()


@contextmanager
def open_raster(path):
    """``with open_raster(p) as src`` — rasterio dataset for a local path or allowed COG URL."""
    from services import dem_reader

    rasterio = dem_reader._import_rasterio()
    if is_remote(path):
        if not remote_enabled():
            raise RemoteRasterError("Remote DEM access is disabled (REMOTE_DEM_ENABLED)")
        url = check_remote_url(str(path))
        try:
            with rasterio.Env(**GDAL_REMOTE_ENV):
                with rasterio.open(url, "r") as src:
                    yield src
        except dem_reader.RasterReadError:
            raise
        except rasterio.errors.RasterioIOError as exc:
            # The provider's message can contain the URL only, never credentials or local paths.
            raise dem_reader.RasterReadError(f"Remote raster could not be read: {type(exc).__name__}") from exc
    else:
        with rasterio.open(Path(str(path)), "r") as src:
            yield src
