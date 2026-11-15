"""Route description: geometry, distances, elevation profile, metrics, A/B comparison."""
from __future__ import annotations

import math

import numpy as np

from apps.routing.profiles import MovementProfile
from services.mars_coordinates import adapt_latitude

from .cost_surface import path_cost
from .route_validator import simplify_path
from .spatial_grid import CLASS_KNOWN, CLASS_PARTIAL, TerrainGrid


def wrap_lon_180(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0


def split_at_seam(coords: list[list[float]]) -> list[list[list[float]]]:
    """Split a lon/lat line where it crosses the +/-180 map seam (crossing point interpolated
    on both sides) so a 2D map never draws it across the whole world. Crossing 0/360 is not a
    seam for a -180..180 map and is left alone."""
    parts: list[list[list[float]]] = []
    cur: list[list[float]] = []
    for lon, lat in coords:
        lon = wrap_lon_180(lon)
        if cur and abs(lon - cur[-1][0]) > 180:
            p_lon, p_lat = cur[-1]
            d = 1 if lon < p_lon else -1  # +1: crossing +180 eastwards
            span = lon + d * 360 - p_lon
            t = 0.0 if span == 0 else (d * 180 - p_lon) / span
            lat_x = p_lat + t * (lat - p_lat)
            cur.append([d * 180.0, lat_x])
            parts.append(cur)
            cur = [[-d * 180.0, lat_x]]
        cur.append([lon, lat])
    if cur:
        parts.append(cur)
    return parts


def summarize(grid: TerrainGrid, cells: list[tuple[int, int]], ds_lat_conv: str, query_lat_conv: str) -> dict:
    coords = []
    profile_pts = []
    dist = dist3 = ascent = descent = unknown_dist = 0.0
    max_grade = 0.0
    max_cell_slope = 0.0
    slope_sum = slope_len = 0.0  # distance-weighted mean of the step grades
    rough_vals: list[float] = []
    unverified: list[list[float]] = []  # [from_m, to_m] along the route
    unknown_lines: list[list[list[float]]] = []  # steps touching a cell without DEM data
    prev = None
    for i, j in cells:
        x, y = grid.xy_of(i, j)
        lon, lat = grid.to_query.transform(x, y)
        lat, _ = adapt_latitude(float(lat), ds_lat_conv, query_lat_conv)
        coords.append([wrap_lon_180(float(lon)), float(lat)])
        zc = grid.z[i, j]
        if prev is not None:
            pi, pj = prev
            d = grid.step_length(pi, pj, i, j)
            zp = grid.z[pi, pj]
            if math.isnan(zc) or math.isnan(zp):
                unknown_lines.append([coords[-2], coords[-1]])
                unknown_dist += d
                dist3 += d
                if unverified and abs(unverified[-1][1] - dist) < 1e-6:
                    unverified[-1][1] = dist + d
                else:
                    unverified.append([dist, dist + d])
            else:
                dz = zc - zp
                dist3 += math.hypot(d, dz)
                ascent += max(dz, 0.0)
                descent += max(-dz, 0.0)
                grade = math.degrees(math.atan2(abs(dz), d))
                max_grade = max(max_grade, grade)
                slope_sum += grade * d
                slope_len += d
            dist += d
        profile_pts.append({"distance_m": round(dist, 2), "elevation_m": None if math.isnan(zc) else float(zc)})
        sl = grid.slope_deg[i, j]
        if not math.isnan(sl):
            max_cell_slope = max(max_cell_slope, float(sl))
        tr = grid.tri_m[i, j]
        if not math.isnan(tr):
            rough_vals.append(float(tr))
        prev = (i, j)
    if len(profile_pts) > 500:  # keep responses small
        idx = np.linspace(0, len(profile_pts) - 1, 500).round().astype(int)
        profile_pts = [profile_pts[k] for k in idx]
    return {
        "geometry": {"type": "LineString", "coordinates": coords},
        "cells": len(cells),
        "distance_m": dist,
        "distance_3d_m": dist3,
        "total_ascent_m": ascent,
        "total_descent_m": descent,
        "max_step_grade_deg": max_grade,
        "unknown_terrain_distance_m": unknown_dist,
        "unknown_terrain_fraction": (unknown_dist / dist) if dist > 0 else 0.0,
        "unverified_geometry": {"type": "MultiLineString", "coordinates": unknown_lines},
        "unverified_segments": [{"from_m": round(a, 2), "to_m": round(b, 2), "status": "UNVERIFIED_NO_DEM_DATA"} for a, b in unverified],
        "max_cell_slope_deg": max_cell_slope,
        "average_step_grade_deg": (slope_sum / slope_len) if slope_len > 0 else 0.0,
        "roughness_tri_mean_m": (sum(rough_vals) / len(rough_vals)) if rough_vals else None,
        "roughness_tri_max_m": max(rough_vals) if rough_vals else None,
        "classification": CLASS_PARTIAL if unknown_dist > 0 else CLASS_KNOWN,
        "elevation_profile": profile_pts,
    }


def describe_route(grid: TerrainGrid, cells: list[tuple[int, int]], profile: MovementProfile, ds_lat_conv: str,
                   query_lat_conv: str, endpoints: tuple[list[float], list[float]] | None = None) -> dict:
    """summarize() + cost under the profile + simplified geometry + metrics."""
    r = summarize(grid, cells, ds_lat_conv, query_lat_conv)
    cost = path_cost(grid, cells, profile)
    r["cost"] = cost
    # penalty above pure 3-D distance: slope + roughness + hazard proximity + uncertainty
    r["terrain_cost"] = cost - r["distance_3d_m"]
    simp = simplify_path(grid, cells, profile)
    coords = []
    for i, j in simp:
        lon, lat = grid.to_query.transform(*grid.xy_of(i, j))
        lat, _ = adapt_latitude(float(lat), ds_lat_conv, query_lat_conv)
        coords.append([wrap_lon_180(float(lon)), float(lat)])
    if endpoints:
        r["geometry"]["coordinates"][0] = list(endpoints[0])
        r["geometry"]["coordinates"][-1] = list(endpoints[1])
        coords[0], coords[-1] = list(endpoints[0]), list(endpoints[1])
    r["geometry_simplified"] = {"type": "LineString", "coordinates": coords}
    # For drawing on a -180..180 map: the same line split where it crosses the map seam.
    r["geometry_display"] = {"type": "MultiLineString", "coordinates": split_at_seam(r["geometry"]["coordinates"])}
    r["simplified_cells"] = simp
    r["simplification"] = (
        "line-of-sight; every cell a simplified segment touches is passable with known DEM values; "
        "metrics are computed on the full cell path"
    )
    from .hazard_analysis import hazard_exposure_m

    r["metrics"] = {
        "hazard_exposure_m": hazard_exposure_m(grid, cells),
        "distance_m": r["distance_m"],
        "distance_3d_m": r["distance_3d_m"],
        "elevation_gain_m": r["total_ascent_m"],
        "elevation_loss_m": r["total_descent_m"],
        "max_step_grade_deg": r["max_step_grade_deg"],
        "max_cell_slope_deg": r["max_cell_slope_deg"],
        "total_ascent_m": r["total_ascent_m"],
        "total_descent_m": r["total_descent_m"],
        "maximum_slope_deg": max(r["max_step_grade_deg"], r["max_cell_slope_deg"]),
        "average_slope_deg": r["average_step_grade_deg"],
        "roughness_tri_mean_m": r["roughness_tri_mean_m"],
        "roughness_tri_max_m": r["roughness_tri_max_m"],
        "known_terrain_pct": round(100 * (1 - r["unknown_terrain_fraction"]), 2),
        "nodata_pct_along_route": round(100 * r["unknown_terrain_fraction"], 2),
        "cost": cost,
        "terrain_cost": r["terrain_cost"],
    }
    return r


def _brief(r: dict, label: str) -> dict:
    m = r["metrics"]
    return {"label": label, "classification": r["classification"], "distance_m": m["distance_m"], "cost": m["cost"],
            "terrain_cost": m["terrain_cost"], "elevation_gain_m": m["elevation_gain_m"],
            "max_cell_slope_deg": m["max_cell_slope_deg"], "average_slope_deg": m["average_slope_deg"],
            "roughness_tri_mean_m": m["roughness_tri_mean_m"], "known_terrain_pct": m["known_terrain_pct"]}


def compare_routes(a: dict, b: dict | None) -> dict:
    """Route A = lowest cost under the profile; Route B = the most distinct alternative. Both
    costs are evaluated with the same profile (no alternative-search penalty). No travel time."""
    out = {"route_a": _brief(a, "Route A — lowest cost"), "route_b": _brief(b, "Route B — alternative") if b else None}
    if b:
        out["difference_b_minus_a"] = {
            "distance_m": b["metrics"]["distance_m"] - a["metrics"]["distance_m"],
            "terrain_cost": b["metrics"]["terrain_cost"] - a["metrics"]["terrain_cost"],
            "cost": b["metrics"]["cost"] - a["metrics"]["cost"],
        }
    out["note"] = "Cost is a dimensionless weighted length (profile heuristic). No travel time is estimated."
    return out
