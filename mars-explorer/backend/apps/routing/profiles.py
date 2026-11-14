"""Movement profiles for the A* planner.

IMPORTANT: these numbers are ENGINEERING HEURISTICS chosen for this software prototype.
They are NOT scientifically validated parameters of human locomotion in a spacesuit or
of any rover. They only make the planner prefer gentler, smoother, better-known terrain.
Change them here; every route response echoes the profile that was used.

Cost of a step between neighbouring DEM cells (8-connected grid):

    cost = d3 * (1 + slope_weight * (grade / max_slope_deg)^2
                   + roughness_weight * min(tri / roughness_ref_m, 1))
         * (unknown_multiplier if a cell has no DEM value else 1)

d3 = 3-D step length (horizontal geodesic step + elevation change), grade = step slope
in degrees, tri = Terrain Ruggedness Index of the destination cell (3x3, metres).
A step is forbidden when grade > max_slope_deg or the destination cell slope >
max_slope_deg, or the cell is inside a hazard buffer.
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

    def to_dict(self) -> dict:
        d = asdict(self)
        # JSON has no infinity: "forbidden" is expressed by allow_unknown_terrain=false.
        for k, v in d.items():
            if isinstance(v, float) and not math.isfinite(v):
                d[k] = None
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
    ),
}


def get_profile(profile_id: str) -> MovementProfile:
    try:
        return PROFILES[profile_id.upper()]
    except KeyError as exc:
        raise ValueError(f"Unknown profile {profile_id!r}; expected one of {', '.join(PROFILES)}") from exc
