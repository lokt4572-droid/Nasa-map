"""Comparison of route candidates on measured quantities only.

Labels describe what was calculated ("lower calculated terrain cost", "shorter distance",
"better data coverage", "more uncertain terrain"). No label says or implies "safe".
"""
from __future__ import annotations

from apps.routing.profiles import MovementProfile

LABEL_LOWER_COST = "LOWER-COST ROUTE"
LABEL_CONSERVATIVE = "CONSERVATIVE ROUTE"
LABEL_PARTIAL = "PARTIALLY UNVERIFIED ROUTE"
LABEL_NONE = "NO VALID ROUTE"

CRITERIA = [
    # key in route["metrics"], title, unit, lower is better?
    ("distance_m", "Distance", "m", True),
    ("total_ascent_m", "Total ascent", "m", True),
    ("maximum_slope_deg", "Maximum slope", "deg", True),
    ("average_slope_deg", "Average slope", "deg", True),
    ("roughness_tri_mean_m", "Roughness (mean TRI)", "m", True),
    ("hazard_exposure_m", "Distance near known hazards", "m", True),
    ("nodata_pct_along_route", "Unknown terrain", "%", True),
    ("terrain_cost", "Calculated terrain cost", "", True),
]


def route_label(route: dict | None, profile: MovementProfile) -> str:
    if not route:
        return LABEL_NONE
    if route.get("unknown_terrain_fraction", 0) > 0:
        return LABEL_PARTIAL
    return LABEL_CONSERVATIVE if not profile.allow_unknown_terrain else LABEL_LOWER_COST


def _descriptors(name: str, m: dict, others: list[dict]) -> list[str]:
    """Plain statements comparing one route with the others (ties produce no statement)."""
    out = []
    def best(key: str) -> bool:
        vals = [o.get(key) for o in others if o.get(key) is not None]
        return m.get(key) is not None and bool(vals) and all(m[key] < v for v in vals)
    def worst(key: str) -> bool:
        vals = [o.get(key) for o in others if o.get(key) is not None]
        return m.get(key) is not None and bool(vals) and all(m[key] > v for v in vals)
    if best("terrain_cost"):
        out.append("Lower calculated terrain cost")
    if best("distance_m"):
        out.append("Shorter distance")
    if best("nodata_pct_along_route"):
        out.append("Better data coverage")
    if worst("nodata_pct_along_route"):
        out.append("More uncertain terrain")
    if best("maximum_slope_deg"):
        out.append("Lower maximum slope")
    if best("hazard_exposure_m"):
        out.append("Less distance near known hazards")
    return out


def compare(candidates: list[tuple[str, dict | None]], data_quality: dict | None, profile: MovementProfile) -> dict:
    """Comparison table for the available candidates. Every number is copied from the route
    metrics computed by the deterministic planner; nothing is estimated here."""
    routes = [(name, r) for name, r in candidates if r]
    columns = []
    for name, r in routes:
        m = r["metrics"]
        others = [o["metrics"] for n2, o in routes if n2 != name]
        columns.append({
            "name": name,
            "label": route_label(r, profile),
            "classification": r.get("classification"),
            "descriptors": _descriptors(name, m, others),
            "values": {key: m.get(key) for key, *_ in CRITERIA},
        })
    dq = data_quality or {}
    return {
        "criteria": [{"key": k, "title": t, "unit": u, "lower_is_better": low} for k, t, u, low in CRITERIA],
        "routes": columns,
        "shared": {
            "dem": dq.get("dataset"),
            "dem_resolution_m": dq.get("resolution_m"),
            "grid_cell_m": dq.get("grid_cell_m"),
            "data_quality": dq.get("quality_status"),
            "planning_scope": (dq.get("planning_scope") or {}).get("scope"),
        },
        "note": ("All candidates were computed on the same DEM with the same profile. Lower numbers are lower "
                 "calculated values, not a statement about safety. No travel time is estimated."),
    }
