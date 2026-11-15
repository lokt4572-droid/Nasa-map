# MARS EXPLORER v0.3 — Routing validation report

Date: 2026-11-14 · Commit of the feature: `6b18452` · Notes: `docs/perf/PHASE5_ROUTING.md`

**No route produced by this software is a safety assessment.** Profiles are engineering heuristics;
obstacles smaller than a DEM cell are invisible; no travel time is estimated.

## 1. Requirements

| Requirement | Status | Evidence |
|---|---|---|
| Inputs: start, end, ≤ 20 waypoints, profile, max slope, return, alternative, **unknown-data policy** | IMPLEMENTED, TESTED | `RoutePlanRequestSerializer` |
| Documented cost: distance + slope + roughness + hazard proximity + uncertainty | IMPLEMENTED, TESTED | `profiles.py` docstring; `pathfinder.step_cost` is the only cost function (A* and reported costs) |
| 8 directions, geodesic metric distances on the DEM ellipsoid | IMPLEMENTED (v0.2), TESTED | flat route = geodesic within 1 % |
| Hazard buffers (+ proximity cost up to 2 r) | IMPLEMENTED, TESTED | `block_hazards` |
| Elevation profile, return route (reversal), waypoints | IMPLEMENTED (v0.2), TESTED | |
| **No diagonal corner cutting** through blocked / NoData / too-steep cells | IMPLEMENTED, TESTED | both orthogonal side cells must be passable |
| Path simplification never crossing obstacles or NoData | IMPLEMENTED, TESTED | line of sight over **supercover** cells (both cells at exact corners); segments through NoData never straightened |
| Default CONSERVATIVE rejects unknown terrain | IMPLEMENTED, TESTED | ALLOW_MARKED with CONSERVATIVE → HTTP 400 |
| STANDARD crosses unknown terrain only with explicit marking | IMPLEMENTED, TESTED | `unverified_segments` (from/to m, `UNVERIFIED_NO_DEM_DATA`); `STANDARD + REJECT` forbids it |
| Classification KNOWN_TERRAIN_ROUTE / PARTIALLY_UNVERIFIED_ROUTE / NO_VALID_ROUTE | IMPLEMENTED, TESTED | top level + per route; every 422 failure → NO_VALID_ROUTE |
| Per-route DEM source, resolution, cell size, coverage %, NoData %, max slope, elevation gain, distance, suitability class | IMPLEMENTED, TESTED | `route.metrics` (+ return and alternative) |
| MOLA = regional planning only | IMPLEMENTED, TESTED | any MOLA-derived DEM → `planning_scope: REGIONAL_PLANNING_ONLY` regardless of gridding |
| Route comparison: A = lowest cost, B = alternative, distance and terrain cost | IMPLEMENTED, TESTED | `comparison`, both scored with the same profile |
| No travel time, no safety guarantee | KEPT | no time fields (tested); disclaimers; astronaut-scale safety always NOT_SUITABLE / NOT_ASSESSED |

## 2. Cost function

```
cost(step) = d3 * (1 + slope_weight * (grade / max_slope)^2
                     + roughness_weight * min(TRI / roughness_ref, 1)
                     + hazard_proximity_weight * proximity)
           * (unknown_multiplier if a cell has no DEM value else 1)
```
`terrain_cost` = route cost − 3-D distance (the part caused by terrain). Forbidden: inside a hazard disc
(radius + buffer), grade or cell slope above the limit, NoData under REJECT, diagonal corner cutting.

| Profile | max slope | slope w | rough w (ref) | hazard buffer | proximity w | unknown |
|---|---|---|---|---|---|---|
| CONSERVATIVE | 15° | 4.0 | 2.0 (50 m) | 500 m | 1.0 | REJECT |
| STANDARD | 25° | 2.0 | 1.0 (100 m) | 100 m | 0.5 | ALLOW_MARKED, ×5, ≤ 20 % |

## 3. Validation cases (automated)

`backend/tests/test_routing_v03.py` (15) + all v0.2 routing/audit tests (unchanged, passing):

- 3 × 3 grid, two blocked side cells → no route (v0.2 cut diagonally through); one blocked side →
  `[(0,0), (1,0), (1,1)]`; NoData side cell and too-steep side cell → orthogonal detour.
- Open terrain still uses diagonals (6 × 6 → 5 diagonal steps).
- Random obstacle fields (40 seeds, 30 % blocked): every diagonal step on every found route has both
  side cells passable.
- Supercover includes both cells at an exact corner crossing; simplified segments never touch a blocked
  cell; never straightened across NoData.
- Hazard proximity: proximity > 0 inside 2 r, 0 beyond; route cost lower than the straight line past the
  hazard.
- NoData column: CONSERVATIVE → no route; STANDARD → PARTIALLY_UNVERIFIED_ROUTE with one 200 m
  unverified segment.
- API: classification, metrics incl. DEM fields, comparison, simplified geometry, no travel time;
  failure → NO_VALID_ROUTE; policy rules; MOLA instrument → REGIONAL_PLANNING_ONLY.

## 4. Live run (real MOLA MEGDR 4 px/deg, CONSERVATIVE)

70° E 15° N → 80° E 22° N: ROUTE_FOUND, KNOWN_TERRAIN_ROUTE, REGIONAL PLANNING ONLY (MOLA),
41 cells → 2 simplified vertices, 738.8 km, gain 754 m, loss 3 408 m, max cell slope 2.9°, 100 % known
terrain. Route B: 770.5 km (+31.7 km), terrain cost +64 408. The Route Planner UI showed the same values
(classification chips, A/B table, banner) in the browser.

## 5. Limits

- Grid ≤ 300 cells per side (decimated windows); MOLA cells ≈ 15 km → kilometre-scale relief only.
- Routes do not cross the DEM seam (a window crossing lon 0° on MEGDR is not stitched); points on the
  seam are handled.
- Profile parameters are heuristics, not validated human or rover models.
