# Route planning architecture (v0.4)

**A computed route is not a safety assessment.** Profiles are engineering assumptions, not
validated astronaut or rover mobility limits. AI never computes or edits route geometry.

## Modules (`backend/apps/routing/services/`)

| Module | Responsibility |
|---|---|
| `route_service.py` | choose the DEM (registered or catalogue), run the planner, assemble the v0.4 result |
| `spatial_grid.py` | read the DEM window, stitch across a full-circumference raster's 0/360 edge, geodesic cell sizes, analytical layers |
| `terrain_constraints.py` | hard constraints (what may never be entered) and blocked-cell counts |
| `cost_surface.py` | hazard discs and proximity; `step_cost`, the only cost function |
| `pathfinder.py` | A* (Dijkstra with `use_heuristic=False`), 4/8-connectivity, legs, alternatives |
| `route_validator.py` | supercover line of sight, simplification, independent re-validation |
| `route_metrics.py` | geometry, distances, profile, metrics, seam-split display geometry |
| `route_comparison.py` | comparison table with neutral labels |
| `hazard_analysis.py` | DEM-derived hazard candidates, hazard exposure |
| `mission_interpreter.py` | re-export of the optional AI interpreter (`apps/ai`) |

Views (`apps/routing/views.py`) only validate input and call the service.

## Pipeline

1. Validate points (same CRS, latitude convention, body).
2. Find DEMs covering all points (finest first); with `terrain_source=auto` also the catalogue.
   Statuses `START_OUTSIDE_COVERAGE`, `DESTINATION_OUTSIDE_COVERAGE`, `INSUFFICIENT_TERRAIN_DATA`.
3. Read the window around the points (+ margin), at most 300 cells per side. Decimated grids are
   conservative: elevation = mean of valid native cells; slope, roughness, relief = **maximum** of
   the native cells (a one-cell obstacle survives decimation).
4. Layers: slope (central differences), aspect, TRI (Riley 1999), 3×3 relief, 3×3 std.
5. Hazards: confirmed reports and any human report block a disc (radius + profile buffer);
   unverified model detections never block.
6. A* with an admissible geodesic heuristic; windows grow ×3 and to the whole DEM if no route.
7. Re-validate the route and its simplification independently; a failing route is discarded
   (`PROCESSING_ERROR`).
8. Metrics, return route, alternative (Route B penalised near Route A, then scored with the same
   profile), comparison table, warnings.

## Cost function

```
cost(step) = d3 * (1 + w_s*(grade/max_slope)^2 + w_r*min(TRI/roughness_ref, 1) + w_h*proximity)
             * (unknown_multiplier if a cell has no DEM value)
```
d3 = 3-D step length on the body's ellipsoid. Weights are documented in `profiles.py`.

## Hard constraints

Max slope (profile, or lower), max roughness, max local relief, required DEM resolution, hazard
buffer (only larger than the profile's), unknown-data policy (CONSERVATIVE: blocked; STANDARD:
`ALLOW_MARKED` with marked UNVERIFIED segments), 4- or 8-connectivity with no corner cutting.

## Coordinates

Ground distances are geodesic on the DEM body's ellipsoid; never degrees as metres, never
EPSG:3857 for Mars or Moon. A full-circumference raster (MOLA MEGDR, edges at 0/360) is read in two
segments and stitched; routes cross lon 0 the short way. Output longitudes are −180…180;
`geometry_display` splits at ±180 for 2D maps.

## API

`POST /api/v1/routes/plan/`, `POST /api/v1/routes/alternatives/`, `GET /api/v1/routes/{id}/`,
`POST /api/v1/routes/hazards/derive/`; optional AI: `POST /api/v1/ai/plan/` (instruction → validated
constraints → the same planner).

## Validation (automated)

`tests/test_routing_v02.py`, `_v03.py`, `_v04.py` (54 tests): A* cost equals Dijkstra on 25 random
fields, no corner cutting, 4-connectivity, flat cost = distance, mountain detour, crater walls,
roughness/relief limits, NoData policy, validator catches tampered and corner-cut routes,
conservative decimation, seam crossing (0/360 and ±180), seam obstacles, polar geodesic cells,
response schema and statuses, hazard provenance. Live: MOLA routes across 0° and 180°, HiRISE
Jezero route in the browser (planning level 3).
