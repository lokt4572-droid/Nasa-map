"""Terrain visualization layers rendered from a numeric DEM.

These PNGs are VISUAL REPRESENTATIONS for the map. Numeric analysis values come from the
/terrain/* metric endpoints, never from these colours.

Algorithm (memory-bounded, any DEM CRS):
1. build the output grid (≤ 1024×1024 px) in the map's geographic CRS for the bbox;
2. transform every output pixel centre into the DEM CRS (PROJ) — explicit latitude-type
   conversion is applied first when both conventions are known;
3. read ONLY the DEM window that covers those pixels, decimated with ``out_shape`` so it
   is never larger than ~2× the output grid; nearest-neighbour lookup;
4. derive the product on the display grid (slope/aspect/hillshade/roughness use the
   display cell size in metres on the DEM body's radius) and colour it; nodata is transparent.
"""
from __future__ import annotations

import math
import struct
import zlib

import numpy as np

from services import remote_raster, dem_reader
from services.mars_coordinates import planetocentric_to_planetographic, planetographic_to_planetocentric

PRODUCTS = ("elevation", "hillshade", "slope", "aspect", "roughness")
MAX_SIDE = 1024


class RenderError(ValueError):
    pass


# ---------------------------------------------------------------- PNG encoding
def encode_png_rgba(rgba: np.ndarray) -> bytes:
    if rgba.dtype != np.uint8 or rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("expected HxWx4 uint8")
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


# ---------------------------------------------------------------- colour ramps
def _ramp(values: np.ndarray, stops: list[tuple[float, tuple[int, int, int]]]) -> np.ndarray:
    xs = [s[0] for s in stops]
    out = np.zeros(values.shape + (3,), dtype=np.uint8)
    for ch in range(3):
        out[..., ch] = np.interp(values, xs, [s[1][ch] for s in stops]).astype(np.uint8)
    return out


ELEVATION_STOPS = [(0.0, (40, 60, 140)), (0.25, (60, 150, 120)), (0.5, (190, 180, 90)), (0.75, (150, 95, 50)), (1.0, (245, 245, 245))]
SLOPE_STOPS = [(0.0, (60, 160, 90)), (10.0, (200, 210, 80)), (20.0, (240, 170, 60)), (30.0, (230, 90, 40)), (45.0, (150, 20, 30))]
ROUGH_STOPS = [(0.0, (68, 1, 84)), (0.33, (59, 82, 139)), (0.66, (33, 145, 140)), (1.0, (253, 231, 37))]


def _aspect_rgb(aspect_deg: np.ndarray) -> np.ndarray:
    h = (np.nan_to_num(aspect_deg) / 60.0) % 6
    x = (1 - np.abs(h % 2 - 1)) * 200
    c = np.full_like(h, 200.0)
    z = np.zeros_like(h)
    conds = [(h < 1, (c, x, z)), (h < 2, (x, c, z)), (h < 3, (z, c, x)), (h < 4, (z, x, c)), (h < 5, (x, z, c)), (h >= 5, (c, z, x))]
    rgb = np.zeros(h.shape + (3,))
    for i in range(3):
        rgb[..., i] = np.select([cd for cd, _ in conds], [v[i] for _, v in conds])
    return (rgb + 40).clip(0, 255).astype(np.uint8)


# ---------------------------------------------------------------- core
def _adapt_lat_array(lats: np.ndarray, from_conv: str, to_conv: str) -> np.ndarray:
    known = {"PLANETOCENTRIC", "PLANETOGRAPHIC"}
    if from_conv in known and to_conv in known and from_conv != to_conv:
        f = planetocentric_to_planetographic if from_conv == "PLANETOCENTRIC" else planetographic_to_planetocentric
        return np.array([f(float(v)) for v in lats])
    return lats


def sample_grid(ds, bbox: tuple[float, float, float, float], width: int, height: int, query_crs, lat_convention: str) -> np.ndarray:
    """DEM values (float64, NaN = nodata/outside) on a regular lon/lat grid over bbox."""
    west, south, east, north = bbox
    lons = west + (np.arange(width) + 0.5) * (east - west) / width
    lats = north - (np.arange(height) + 0.5) * (north - south) / height
    lon_g, lat_g = np.meshgrid(lons, lats)
    return sample_lonlat(ds, lon_g, lat_g, query_crs, lat_convention, max_read=(2 * height, 2 * width))


def sample_lonlat(ds, lon_arr, lat_arr, query_crs, lat_convention: str, max_read: tuple[int, int] = (2048, 2048)) -> np.ndarray:
    """DEM values (float64, NaN = nodata/outside) at arbitrary query-CRS points (nearest cell).

    One bounded window read per contiguous column segment: the read is decimated so that it
    never exceeds ``max_read`` (rows, cols) cells, whatever the distance between the points."""
    from pyproj import CRS, Transformer

    from rasterio.windows import Window

    lon_arr = np.asarray(lon_arr, dtype="float64")
    lat_arr = np.asarray(lat_arr, dtype="float64")
    shape_out = lon_arr.shape
    lats = _adapt_lat_array(lat_arr.ravel(), lat_convention, ds.latitude_convention).reshape(shape_out)
    ds_crs = CRS.from_wkt(ds.crs)
    xs, ys = Transformer.from_crs(query_crs, ds_crs, always_xy=True).transform(lon_arr, lats)
    xs, ys = np.asarray(xs, dtype="float64"), np.asarray(ys, dtype="float64")
    out = np.full(shape_out, np.nan)
    with remote_raster.open_raster(ds.file_path) as src:
        t = src.transform
        if t.b != 0 or t.d != 0:
            raise RenderError("Rotated raster grids are not supported")
        period = dem_reader.x_wrap_period(ds_crs, src.bounds.left, src.bounds.right)
        if period:
            xs = (xs - src.bounds.left) % period + src.bounds.left
        finite = np.isfinite(xs) & np.isfinite(ys)
        cols = np.floor((np.where(finite, xs, 0) - t.c) / t.a).astype(np.int64)
        rows = np.floor((np.where(finite, ys, 0) - t.f) / t.e).astype(np.int64)
        inside = (rows >= 0) & (rows < src.height) & (cols >= 0) & (cols < src.width) & finite
        if not inside.any():
            return out
        scale = float(src.scales[0]) if src.scales else 1.0
        offset = float(src.offsets[0]) if src.offsets else 0.0
        # Points on both sides of the raster's x seam use columns at both ends of the raster.
        # Reading one window from the min to the max column would span the whole raster and
        # decimate it (wrong cells), so each contiguous column segment is read on its own.
        for seg in _column_segments(cols[inside]):
            mask = inside & (cols >= seg[0]) & (cols <= seg[1])
            r0, r1 = int(rows[mask].min()), int(rows[mask].max())
            c0, c1 = seg
            wh, ww = r1 - r0 + 1, c1 - c0 + 1
            fy = max(1, math.ceil(wh / max_read[0]))
            fx = max(1, math.ceil(ww / max_read[1]))
            shape = (max(1, wh // fy), max(1, ww // fx))
            data = src.read(1, window=Window(c0, r0, ww, wh), out_shape=shape, masked=True)
            arr = np.ma.filled(data.astype("float64"), np.nan) * scale + offset
            rr = np.clip(((rows - r0) * shape[0]) // wh, 0, shape[0] - 1)
            cc = np.clip(((cols - c0) * shape[1]) // ww, 0, shape[1] - 1)
            out[mask] = arr[rr[mask], cc[mask]]
    out[~np.isfinite(out)] = np.nan
    return out


def _column_segments(cols: np.ndarray) -> list[tuple[int, int]]:
    """Split the used columns at their largest gap when the grid wraps around the raster seam."""
    u = np.unique(cols)
    if len(u) < 2:
        return [(int(u[0]), int(u[-1]))]
    gaps = np.diff(u)
    i = int(np.argmax(gaps))
    # a "wrapping" grid leaves a gap much larger than its own sampling step
    step = max(1, int(np.median(gaps)))
    if gaps[i] > 4 * step and gaps[i] > (u[-1] - u[0]) / 2:
        return [(int(u[0]), int(u[i])), (int(u[i + 1]), int(u[-1]))]
    return [(int(u[0]), int(u[-1]))]


def _gradients(z: np.ndarray, bbox, radius_m: float) -> tuple[np.ndarray, np.ndarray]:
    west, south, east, north = bbox
    h, w = z.shape
    lats = north - (np.arange(h) + 0.5) * (north - south) / h
    dy = math.radians((north - south) / h) * radius_m
    dx = (math.radians((east - west) / w) * radius_m * np.cos(np.radians(lats)))[:, None]
    dzdy_rows, dzdx = np.gradient(z)
    return dzdx / np.maximum(dx, 1e-9), -dzdy_rows / dy  # +x east, +y north


def render(ds, product: str, bbox, width: int, height: int, query_crs, lat_convention: str) -> tuple[bytes, dict]:
    if product not in PRODUCTS:
        raise RenderError(f"product must be one of {', '.join(PRODUCTS)}")
    if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE):
        raise RenderError(f"width/height must be 1..{MAX_SIDE}")
    from pyproj import CRS

    z = sample_grid(ds, bbox, width, height, query_crs, lat_convention)
    valid = ~np.isnan(z)
    alpha = np.where(valid, 255, 0).astype(np.uint8)
    radius = CRS.from_wkt(ds.crs).ellipsoid.semi_major_metre
    meta: dict = {"product": product, "dataset": ds.name, "valid_fraction": float(valid.mean())}
    if not valid.any():
        rgb = np.zeros(z.shape + (3,), np.uint8)
        meta.update(value_min=None, value_max=None, units=None)
    elif product == "elevation":
        lo, hi = float(np.nanmin(z)), float(np.nanmax(z))
        rgb = _ramp(np.nan_to_num((z - lo) / max(hi - lo, 1e-9)), ELEVATION_STOPS)
        meta.update(value_min=lo, value_max=hi, units="m")
    else:
        gx, gy = _gradients(z, bbox, radius)
        slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        if product == "slope":
            rgb = _ramp(np.nan_to_num(slope), SLOPE_STOPS)
            meta.update(value_min=float(np.nanmin(slope)), value_max=float(np.nanmax(slope)), units="degrees")
        elif product == "aspect":
            asp = (np.degrees(np.arctan2(-gx, -gy)) + 360) % 360
            rgb = _aspect_rgb(asp)
            meta.update(value_min=0.0, value_max=360.0, units="degrees (clockwise from north, downslope)")
        elif product == "hillshade":
            az, alt = math.radians(315), math.radians(45)
            aspect_rad = np.arctan2(-gx, -gy)
            slope_rad = np.radians(slope)
            hs = np.sin(alt) * np.cos(slope_rad) + np.cos(alt) * np.sin(slope_rad) * np.cos(az - aspect_rad)
            g = (np.nan_to_num(hs).clip(0, 1) * 255).astype(np.uint8)
            rgb = np.stack([g, g, g], axis=-1)
            meta.update(value_min=0.0, value_max=1.0, units="relative illumination (sun az 315°, alt 45°)")
        else:  # roughness: TRI on the display grid
            pad = np.pad(z, 1, mode="edge")
            acc = np.zeros_like(z)
            for dyy in (-1, 0, 1):
                for dxx in (-1, 0, 1):
                    acc += (pad[1 + dyy : 1 + dyy + z.shape[0], 1 + dxx : 1 + dxx + z.shape[1]] - z) ** 2
            tri = np.sqrt(acc)
            hi = float(np.nanpercentile(tri, 98)) or 1.0
            rgb = _ramp(np.nan_to_num(tri / hi).clip(0, 1), ROUGH_STOPS)
            meta.update(value_min=0.0, value_max=hi, units="m (TRI on display grid, 98th percentile scale)")
        alpha = np.where(np.isnan(slope), 0, alpha).astype(np.uint8)
    rgba = np.dstack([rgb, alpha])
    return encode_png_rgba(rgba), meta
