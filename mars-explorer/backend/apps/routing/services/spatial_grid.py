"""Routing grid: the DEM window the planner works on, in a continuous metric frame.

* Only the window around the route points (+ margin) is read, decimated to at most
  ``MAX_GRID_SIDE`` cells per side; the effective cell size is reported.
* Ground cell sizes are geodesic distances between neighbouring cell centres on the DEM
  body's ellipsoid — never degrees treated as metres, never Earth's Web Mercator.
* Longitude seam: a raster that spans the full circumference (e.g. MOLA MEGDR, centred on
  180 deg, edges at 0/360) is read in two column segments and stitched, so the grid is
  continuous across the raster edge. Column indices are "unwrapped" (may be < 0 or >= width).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from services import dem_reader, remote_raster, window_cache

MAX_GRID_SIDE = 300
MARGIN_FRACTION = 0.25  # extra area around the points' bounding box
MIN_MARGIN_CELLS = 10
# Decimated grids are built from a native-resolution read when the window has at most this many
# cells (about 16 MB of float32), so that slope/roughness are the MAXIMUM of the native cells in
# each coarse cell: decimation must never erase a steep obstacle. Larger windows fall back to
# nearest-cell sampling and say so in the grid metadata.
NATIVE_READ_BUDGET = 4_000_000
WINDOW_SCALES = (1.0, 3.0, 1e6)  # last = whole DEM

STATUS_FOUND = "ROUTE_FOUND"
STATUS_INSUFFICIENT = "INSUFFICIENT_TERRAIN_DATA"
STATUS_NO_PASSABLE = "NO_PASSABLE_ROUTE"

CLASS_KNOWN = "KNOWN_TERRAIN_ROUTE"
CLASS_PARTIAL = "PARTIALLY_UNVERIFIED_ROUTE"
CLASS_NONE = "NO_VALID_ROUTE"


class RoutePlanningError(Exception):
    def __init__(self, status: str, reason: str, details: dict | None = None):
        super().__init__(reason)
        self.status = status
        self.reason = reason
        self.details = details or {}


@dataclass
class TerrainGrid:
    z: np.ndarray            # (H, W) metres, NaN = no data
    dx_m: np.ndarray         # (H,) east-west ground step of each row
    dy_m: np.ndarray         # (H-1,) north-south ground step between row i and i+1
    slope_deg: np.ndarray    # (H, W)
    tri_m: np.ndarray        # (H, W)
    blocked: np.ndarray      # (H, W) bool (hazards)
    x0: float                # dataset-CRS coordinate of cell (0,0) centre
    y0: float
    px: float                # dataset-CRS step per grid column / row (signed)
    py: float
    decimation: float
    to_query: Any            # Transformer dataset CRS -> query CRS
    meta: dict = field(default_factory=dict)
    proximity: np.ndarray | None = None  # (H, W) 0..1 hazard proximity outside the blocked discs
    x_period: float | None = None        # dataset-CRS x period when the grid may cross the raster seam
    aspect_deg: np.ndarray | None = None  # (H, W) downslope direction, clockwise from north
    relief_m: np.ndarray | None = None    # (H, W) local relief (3x3 max - min)
    std_m: np.ndarray | None = None       # (H, W) 3x3 elevation standard deviation

    @property
    def shape(self) -> tuple[int, int]:
        return self.z.shape

    def cell_of(self, x: float, y: float) -> tuple[int, int] | None:
        i = int(math.floor((y - self.y0) / self.py + 0.5))
        h, w = self.shape
        if not 0 <= i < h:
            return None
        # A grid stitched across the seam uses continuous x: try the point one period either side.
        for shift in ((0.0, self.x_period, -self.x_period) if self.x_period else (0.0,)):
            j = int(math.floor((x + shift - self.x0) / self.px + 0.5))
            if 0 <= j < w:
                return (i, j)
        return None

    def xy_of(self, i: int, j: int) -> tuple[float, float]:
        return self.x0 + j * self.px, self.y0 + i * self.py

    def step_length(self, i: int, j: int, ni: int, nj: int) -> float:
        dx = 0.5 * (self.dx_m[i] + self.dx_m[ni]) * abs(nj - j)
        dy = self.dy_m[min(i, ni)] * abs(ni - i) if ni != i else 0.0
        return math.hypot(dx, dy)


def unwrap_columns(cols: list[int], width: int) -> list[int]:
    """Columns of a full-circumference raster made continuous along the shortest way round:
    each column is shifted by a multiple of ``width`` so that it lies within half a turn of the
    first one. E.g. width 1440: [1438, 2] -> [1438, 1442]."""
    out = [cols[0]]
    for c in cols[1:]:
        d = (c - cols[0] + width // 2) % width - width // 2
        out.append(cols[0] + d)
    return out


def _read_columns(src, c0: int, ww: int, r0: int, wh: int, out_h: int, out_w: int, wrap: bool, fx: int, path=None):
    """Read columns c0 .. c0+ww-1 (unwrapped indices) as one array of shape (out_h, out_w).

    Inside the raster this is one decimated window read. Across the raster's x seam the two
    parts are read separately with the SAME integer column factor ``fx`` and joined, so the
    stitched grid has uniform column spacing and no cell is duplicated or dropped."""
    from rasterio.windows import Window

    if not wrap or (c0 >= 0 and c0 + ww <= src.width):
        return window_cache.read(src, path or src.name, Window(c0, r0, ww, wh), (out_h, out_w))
    parts = []
    start = c0
    remaining = ww
    while remaining > 0:
        col = start % src.width
        n = min(remaining, src.width - col)
        parts.append(window_cache.read(src, path or src.name, Window(col, r0, n, wh), (out_h, max(1, n // fx))))
        start += n
        remaining -= n
    return np.ma.concatenate(parts, axis=1)


def build_grid(ds, points_ds: list[tuple[float, float]], to_query, max_side: int = MAX_GRID_SIDE, margin_scale: float = 1.0) -> TerrainGrid:
    from pyproj import CRS, Geod, Transformer

    ds_crs = CRS.from_wkt(ds.crs)
    with remote_raster.open_raster(ds.file_path) as src:
        t = src.transform
        if t.b != 0 or t.d != 0:
            raise RoutePlanningError(STATUS_INSUFFICIENT, "Rotated DEM grids are not supported")
        rc = []
        period = dem_reader.x_wrap_period(ds_crs, src.bounds.left, src.bounds.right)
        # The raster can be stitched across its own edge only when it spans the whole circumference.
        wrap = bool(period) and abs(abs(t.a) * src.width - period) < abs(t.a)
        for x, y in points_ds:
            if period:
                x = (x - src.bounds.left) % period + src.bounds.left
            col = math.floor((x - t.c) / t.a)
            row = math.floor((y - t.f) / t.e)
            if not (0 <= row < src.height and 0 <= col < src.width):
                raise RoutePlanningError(STATUS_INSUFFICIENT, "A route point lies outside the DEM", {"point_dataset_xy": [x, y]})
            rc.append((row, col))
        rows = [r for r, _ in rc]
        cols = [c for _, c in rc]
        if wrap:
            cols = unwrap_columns(cols, src.width)  # shortest way round, possibly across the seam
        span = max(max(rows) - min(rows), max(cols) - min(cols), 1)
        margin = int(max(MIN_MARGIN_CELLS, span * MARGIN_FRACTION) * margin_scale)
        r0, r1 = max(0, min(rows) - margin), min(src.height - 1, max(rows) + margin)
        if wrap:
            c0, c1 = min(cols) - margin, max(cols) + margin
            if c1 - c0 + 1 > src.width:  # never more than one turn
                mid = (min(cols) + max(cols)) // 2
                c0 = mid - src.width // 2
                c1 = c0 + src.width - 1
        else:
            c0, c1 = max(0, min(cols) - margin), min(src.width - 1, max(cols) + margin)
        wh, ww = r1 - r0 + 1, c1 - c0 + 1
        crosses = wrap and (c0 < 0 or c1 >= src.width)
        factor = max(1.0, max(wh, ww) / max_side)
        fx = 1
        if crosses:
            # Integer column factor and segment widths that are multiples of it (see _read_columns).
            fx = max(1, math.ceil(factor))
            factor = float(fx)
            first = (-c0) % src.width if c0 < 0 else src.width - c0  # columns before the seam
            c0 -= (-first) % fx
            first += (-first) % fx
            ww = c1 - c0 + 1
            ww -= (ww - first) % fx
            ww = min(ww, (src.width // fx) * fx)
            out_w = max(2, ww // fx)
        else:
            out_w = max(2, round(ww / factor))
        out_h = max(2, round(wh / factor))
        native = None
        if factor > 1.0 and wh * ww <= NATIVE_READ_BUDGET:
            native = _read_columns(src, c0, ww, r0, wh, wh, ww, wrap, 1, ds.file_path)
            data = None
        else:
            data = _read_columns(src, c0, ww, r0, wh, out_h, out_w, wrap, fx, ds.file_path)
            out_w = data.shape[1]
        scale = float(src.scales[0]) if src.scales else 1.0
        offset = float(src.offsets[0]) if src.offsets else 0.0
    px = t.a * ww / out_w
    py = t.e * wh / out_h
    x0 = t.c + c0 * t.a + 0.5 * px  # continuous (unwrapped) x: may lie beyond the raster edge
    y0 = t.f + r0 * t.e + 0.5 * py

    # Geodesic ground distances on the DEM body's ellipsoid.
    ell = ds_crs.ellipsoid
    geod = Geod(a=ell.semi_major_metre, b=ell.semi_minor_metre)
    to_geo = Transformer.from_crs(ds_crs, ds_crs.geodetic_crs, always_xy=True)

    def row_steps(x_first: float, step_x: float, step_y: float, ys: np.ndarray):
        lon_a, lat_a = to_geo.transform(np.full(len(ys), x_first), ys)
        lon_b, lat_b = to_geo.transform(np.full(len(ys), x_first + step_x), ys)
        _, _, ddx = geod.inv(lon_a, lat_a, lon_b, lat_b)
        _, _, ddy = geod.inv(lon_a[:-1], lat_a[:-1], lon_a[1:], lat_a[1:])
        return np.maximum(np.asarray(ddx, dtype="float64"), 1e-6), np.maximum(np.asarray(ddy, dtype="float64"), 1e-6)

    dx, dy = row_steps(x0, px, py, y0 + np.arange(out_h) * py)
    if native is not None:
        zn = np.ma.filled(native.astype("float64"), np.nan) * scale + offset
        zn[~np.isfinite(zn)] = np.nan
        ndx, ndy = row_steps(t.c + (c0 + 0.5) * t.a, t.a, t.e, t.f + (r0 + 0.5 + np.arange(wh)) * t.e)
        nl = terrain_layers(zn, ndx, float(ndy.mean()))
        ri = np.minimum((np.arange(wh) * out_h) // wh, out_h - 1)
        ci = np.minimum((np.arange(ww) * out_w) // ww, out_w - 1)
        z = _block_reduce(zn, ri, ci, out_h, out_w, "mean")
        layers = terrain_layers(z, dx, float(dy.mean()))
        for key in ("slope_deg", "tri_m", "relief_m"):
            layers[key] = np.fmax(layers[key], _block_reduce(nl[key], ri, ci, out_h, out_w, "max"))
        resampling = "native read; elevation = mean of valid native cells; slope, roughness and relief = maximum of the native cells"
    else:
        z = np.ma.filled(data.astype("float64"), np.nan) * scale + offset
        z[~np.isfinite(z)] = np.nan
        layers = terrain_layers(z, dx, float(dy.mean()))
        resampling = ("none (native cells)" if factor <= 1.0 else
                      "nearest cell (window too large for a native read): obstacles narrower than a grid cell can be missed")
    return TerrainGrid(
        z=z, dx_m=dx, dy_m=dy, slope_deg=layers["slope_deg"], tri_m=layers["tri_m"], blocked=np.zeros_like(z, dtype=bool),
        x0=x0, y0=y0, px=px, py=py, decimation=factor, to_query=to_query, x_period=period if wrap else None,
        aspect_deg=layers["aspect_deg"], relief_m=layers["relief_m"], std_m=layers["std_m"],
        meta={
            "rows": out_h, "cols": out_w, "decimation_factor": round(factor, 3),
            "cell_size_m": {"dx_min": float(dx.min()), "dx_max": float(dx.max()), "dy_mean": float(dy.mean())},
            "dem_window": {"row0": r0, "col0": c0, "rows": wh, "cols": ww},
            "nodata_fraction": float(np.isnan(z).mean()),
            "crosses_dem_seam": bool(crosses),
            "resampling": resampling,
        },
    )


def _block_reduce(a: np.ndarray, ri: np.ndarray, ci: np.ndarray, out_h: int, out_w: int, how: str) -> np.ndarray:
    """Reduce a native array onto the coarse grid; native row r goes to coarse row ri[r], native
    column c to ci[c]. NaN is ignored; a coarse cell with no valid native cell is NaN.
    ``mean`` additionally returns NaN when more than half of the native cells are NoData."""
    idx = (ri[:, None] * out_w + ci[None, :]).ravel()
    v = a.ravel()
    ok = np.isfinite(v)
    n_all = np.bincount(idx, minlength=out_h * out_w)
    n_ok = np.bincount(idx[ok], minlength=out_h * out_w)
    if how == "mean":
        sums = np.bincount(idx[ok], weights=v[ok], minlength=out_h * out_w)
        with np.errstate(invalid="ignore", divide="ignore"):
            out = sums / n_ok
        out[(n_ok == 0) | (n_ok * 2 < n_all)] = np.nan
    else:
        out = np.full(out_h * out_w, -np.inf)
        np.maximum.at(out, idx[ok], v[ok])
        out[n_ok == 0] = np.nan
    return out.reshape(out_h, out_w)


def terrain_layers(z: np.ndarray, dx: np.ndarray, dy: float) -> dict[str, np.ndarray]:
    """Analytical layers of the routing grid, all from the elevation grid itself.

    slope_deg  central differences (np.gradient), degrees from horizontal;
    aspect_deg downslope direction, degrees clockwise from north (NaN on flat cells);
    tri_m      Terrain Ruggedness Index (Riley et al. 1999): sqrt(sum of squared differences
               to the 8 neighbours), metres;
    relief_m   local relief: max - min of the 3x3 neighbourhood, metres;
    std_m      standard deviation of the 3x3 neighbourhood, metres.
    A cell whose 3x3 neighbourhood touches NoData gets NaN in every layer (no value is
    invented from partial neighbourhoods)."""
    h, w = z.shape
    gy, gx = np.gradient(z)  # d/drow (southwards), d/dcol (eastwards)
    sx = gx / dx[:, None]
    sy = gy / dy
    slope = np.degrees(np.arctan(np.hypot(sx, sy)))
    # Downslope vector in (east, north): -(dz/dE, dz/dN); rows grow southwards so dz/dN = -sy.
    aspect = (np.degrees(np.arctan2(-sx, sy)) + 360.0) % 360.0
    aspect[np.hypot(sx, sy) < 1e-12] = np.nan
    pad = np.pad(z, 1, mode="edge")
    stack = np.stack([pad[1 + di : 1 + di + h, 1 + dj : 1 + dj + w] for di in (-1, 0, 1) for dj in (-1, 0, 1)])
    tri = np.sqrt(((stack - z) ** 2).sum(axis=0))
    relief = stack.max(axis=0) - stack.min(axis=0)
    std = stack.std(axis=0)
    return {"slope_deg": slope, "aspect_deg": aspect, "tri_m": tri, "relief_m": relief, "std_m": std}
