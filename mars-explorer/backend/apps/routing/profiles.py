"""Movement profiles for the A* planner.

IMPORTANT: these numbers are ENGINEERING HEURISTICS chosen for this software prototype.
They are NOT scientifically validated parameters of human locomotion in a spacesuit or
of any rover. They only make the planner prefer gentler, smoother, better-known terrain.
Change them here; every route response echoes the profile that was used.

Cost of a step between neighbouring DEM cells (8-connected grid), v0.3:

    cost = d3 * (1                                                  distance
                 + slope_weight * (grade / max_slope_deg)^2          slope
                 + roughness_weight * min(tri / roughness_ref_m, 1)  roughness
                 + hazard_proximity_weight * proximity)             hazard proximity
              * (unknown_multiplier if a cell has no DEM value else 1)   uncertainty

d3 = 3-D step length (horizontal geodesic step + elevation change), grade = step slope
in degrees, tri = Terrain Ruggedness Index of the destination cell (3x3, metres),
proximity = 0..1, rising from 0 at twice the hazard's buffered radius to 1 at its edge.

A step is forbidden when
- the destination cell is inside a hazard disc (hazard radius + hazard_buffer_m);
- grade > max_slope_deg or the destination cell's slope > max_slope_deg;
- a cell has no DEM value and the unknown-data policy is REJECT;
- it is a DIAGONAL step and either of the two orthogonal cells it passes between is not
  passable (no corner cutting between blocked, steep or NoData cells).

Unknown-data policy: REJECT (CONSERVATIVE default — terrain without DEM data is never
entered) or ALLOW_MARKED (STANDARD — allowed at a heavy penalty, up to max_unknown_fraction
of the distance; every such segment is returned as UNVERIFIED and the route is classified
PARTIALLY_UNVERIFIED_ROUTE).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class MovementProfile:
    id: str
    description: str
    max_slope_deg: float
    slope_weight: float
    roughness_weight: float
    roughness_ref_m: float
    allow_unknown_terrain: bool
    unknown_multiplier: float
    hazard_buffer_m: float
    max_unknown_fraction: float  # reject routes with more unknown terrain than this (by distance)
    hazard_proximity_weight: float = 0.0

    @property
    def unknown_policy(self) -> str:
        return "ALLOW_MARKED" if self.allow_unknown_terrain else "REJECT"

    def to_dict(self) -> dict:
        d = asdict(self)
        # JSON has no infinity: "forbidden" is expressed by allow_unknown_terrain=false.
        for k, v in d.items():
            if isinstance(v, float) and not math.isfinite(v):
                d[k] = None
        d["unknown_data_policy"] = self.unknown_policy
        d["disclaimer"] = "Engineering heuristic; not a validated human/rover traversability model."
        return d


PROFILES: dict[str, MovementProfile] = {
    "CONSERVATIVE": MovementProfile(
        id="CONSERVATIVE",
        description="Gentle slopes only, wide hazard buffers, never crosses cells without DEM data.",
        max_slope_deg=15.0,
        slope_weight=4.0,
        roughness_weight=2.0,
        roughness_ref_m=50.0,
        allow_unknown_terrain=False,
        unknown_multiplier=float("inf"),
        hazard_buffer_m=500.0,
        max_unknown_fraction=0.0,
        hazard_proximity_weight=1.0,
    ),
    "STANDARD": MovementProfile(
        id="STANDARD",
        description="Steeper slopes allowed; may cross short gaps in DEM coverage at a heavy penalty, reported explicitly.",
        max_slope_deg=25.0,
        slope_weight=2.0,
        roughness_weight=1.0,
        roughness_ref_m=100.0,
        allow_unknown_terrain=True,
        unknown_multiplier=5.0,
        hazard_buffer_m=100.0,
        max_unknown_fraction=0.2,
        hazard_proximity_weight=0.5,
    ),
}


def get_profile(profile_id: str) -> MovementProfile:
    try:
        return PROFILES[profile_id.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown profile {profile_id!r}; expected one of {', '.join(PROFILES)}") from exc


# ---------------------------------------------------------------------------
# DEM resolution suitability (v0.2 audit).
#
# A DEM cell hides everything smaller than itself: with a 14.8 km MOLA cell, craters,
# boulder fields and scarps hundreds of metres wide are invisible. The classes below say
# what a route on a given grid can be used for. They are engineering limits, not validated
# human-factors criteria. NO class makes a route "safe": astronaut-scale route safety
# needs metre-scale DTMs AND a validated traversability model, which this software does not
# have, so `astronaut_scale_route_safety` is never "SUITABLE".

ASTRONAUT_SCALE_MAX_CELL_M = 1.0  # cell size at which boulder/step-scale relief starts to be resolvable

RESOLUTION_CLASSES = [
    # (max effective cell size in metres, class, what the route may be used for)
    (2.0, "DETAILED_TRAVERSE_STUDY", "metre-scale DTM: detailed traverse studies; still not a validated safety assessment"),
    (100.0, "SITE_RECONNAISSANCE", "site-scale planning (e.g. CTX/HRSC DTM): landforms visible, rocks and small craters are not"),
    (float("inf"), "REGIONAL_PLANNING_ONLY", "regional overview only (e.g. global MOLA): kilometre-scale terrain; unsuitable for astronaut-scale routes"),
]


def assess_resolution(effective_cell_m: float, dataset_resolution_m: float | None) -> dict:
    """Classify a routing grid by its coarsest cell size (after any decimation)."""
    cell = max(effective_cell_m, dataset_resolution_m or 0.0)
    for max_cell, cls, use in RESOLUTION_CLASSES:
        if cell <= max_cell:
            break
    return {
        "effective_cell_m": round(cell, 3),
        "dataset_resolution_m": dataset_resolution_m,
        "class": cls,
        "allowed_use": use,
        # Features narrower than ~2 cells cannot be represented on the grid (sampling limit).
        "smallest_resolvable_feature_m": round(2 * cell, 1),
        "suitable_for_astronaut_scale_route_safety": False,
        "astronaut_scale_route_safety": "NOT_SUITABLE" if cell > ASTRONAUT_SCALE_MAX_CELL_M else "NOT_ASSESSED_NO_VALIDATED_MODEL",
        "reason": (
            f"The routing grid resolves nothing smaller than ~{2 * cell:,.0f} m. "
            + ("Astronaut-scale hazards (rocks, small craters, steps) are invisible at this resolution."
               if cell > ASTRONAUT_SCALE_MAX_CELL_M
               else "Resolution is metre-scale, but no validated traversability model exists in this software.")
        ),
    }
