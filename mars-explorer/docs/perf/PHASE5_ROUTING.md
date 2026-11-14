# Phase 5 — A* routing improvements (2026-11-14)

Raw notes for `docs/ROUTING_VALIDATION_V0.3.md` (Phase 7).

## Changes (`backend/apps/routing/`)

| Requirement | Status | Where |
|---|---|---|
| Documented cost: distance + slope + roughness + hazard proximity + uncertainty | IMPLEMENTED, TESTED | `profiles.py` docstring; `pathfinder.step_cost` (single function used by A* and for reported costs) |
| 8-direction moves, geodesic metric distances, hazard buffers, profile, reversal (return route), waypoints | IMPLEMENTED (v0.2), kept | `pathfinder.py` |
| **No diagonal corner cutting** through blocked / NoData / too-steep cells | IMPLEMENTED, TESTED | `step_cost`: a diagonal needs both orthogonal side cells passable (`cell_passable`) |
| Path simplification that never crosses obstacles or NoData | IMPLEMENTED, TESTED | `simplify_path` + `segment_clear` over `supercover_cells` (every touched cell, both cells at exact corners); metrics stay on the full cell path; `geometry_simplified` returned alongside `geometry` |
| Unknown-data policy input; CONSERVATIVE rejects unknown terrain | IMPLEMENTED, TESTED | `unknown_data_policy` = REJECT / ALLOW_MARKED; ALLOW_MARKED only with STANDARD (400 otherwise); STANDARD + REJECT forbids NoData |
| Classification KNOWN_TERRAIN_ROUTE / PARTIALLY_UNVERIFIED_ROUTE / NO_VALID_ROUTE | IMPLEMENTED, TESTED | `route_classification` (top level + per route); failures (422) → NO_VALID_ROUTE |
| Unverified segments marked explicitly | IMPLEMENTED, TESTED | `unverified_segments: [{from_m, to_m, status: UNVERIFIED_NO_DEM_DATA}]` |
| Per-route DEM source, resolution, cell size, coverage %, NoData %, max slope, elevation gain, distance, suitability class | IMPLEMENTED, TESTED | `route.metrics` (+ `return_route`, `alternative_route`) |
| MOLA = regional planning only | IMPLEMENTED, TESTED | `views.planning_scope`: any MOLA-derived DEM (instrument/name/product) → REGIONAL_PLANNING_ONLY regardless of gridding (track spacing, interpolation between tracks) |
| Route comparison A (lowest cost) / B (alternative) with distance and terrain cost | IMPLEMENTED, TESTED | `comparison`: both evaluated with the same profile cost (no alternative-search penalty); `difference_b_minus_a` |
| No travel time; no safety guarantee | KEPT | no time fields; comparison note "No travel time is estimated"; disclaimers and astronaut-scale NOT_SUITABLE unchanged |
| Route points on the MOLA MEGDR seam (lon 0°) | FIXED | `build_grid` uses `dem_reader.x_wrap_period` (Phase 4 fix applied to routing) |

Hazard proximity: cells between the buffered hazard radius r and 2r get proximity
1 − (d − r)/r; weights CONSERVATIVE 1.0, STANDARD 0.5 (engineering heuristics, documented as such).

## UI (`components/mission/RoutePlanner.tsx`)

Classification chips, "Terrain without DEM data" selector (STANDARD only: allow marked UNVERIFIED /
reject), UNVERIFIED segment list, max cell slope, cost (terrain cost), A/B comparison table,
REGIONAL PLANNING ONLY banner. Old saved routes without v0.3 fields still render (fields optional).
The UI was type-checked and unit-tested but **not exercised in the browser** in this phase.

## Live check (real MOLA MEGDR, CONSERVATIVE, 70°E 15°N → 80°E 22°N)

ROUTE_FOUND, KNOWN_TERRAIN_ROUTE, scope REGIONAL_PLANNING_ONLY (MOLA), 41 cells → 2 simplified
vertices, distance 738.8 km, gain 754 m, max cell slope 2.9°, 100 % known terrain;
Route B 770.5 km (+31.7 km, +64 408 terrain cost).

## Tests

`backend/tests/test_routing_v03.py` (15): corner cutting between two blocked cells / past one
blocked cell / past NoData / past a steep cell, diagonals still used in open terrain, random obstacle
fields (all diagonals have passable sides), supercover at exact corners, simplified line never
crosses an obstacle, never straightened across NoData, hazard proximity, classification +
unverified segments, comparison, API (classification/metrics/comparison/simplified geometry/no
travel time), NO_VALID_ROUTE on failure, unknown policy rules, MOLA → regional only.
All v0.2 routing tests unchanged and passing. Backend 166/166, frontend 138/138.
