# Routing — final validation (v0.5)

Date: 2026-11-15 · Branch `release/v0.5-nova`

**A computed route is not a safety assessment.** No route is ever labelled "safe".

## What changed in v0.5

| Change | Why |
|---|---|
| Every final route (primary, return, alternative) is re-checked on the **original DEM at native spacing** (`route_validator.validate_on_source`) | v0.4 validated on the (possibly decimated) planning grid only |
| A primary route that fails the source check returns `INVALID_ROUTE`; a failing alternative is moved to `<key>_rejected` | a route that does not hold on the real data is never shown as valid |
| Displayed metrics and the elevation profile come from the **displayed line** sampled on the source DEM; grid numbers are kept as `grid_metrics`; `metrics_basis` says which | v0.4 showed grid-cell metrics for a simplified line |
| Steps that touch NoData cells are returned as `unverified_geometry` and drawn dashed red | partially unverified routes must be visible as such |
| STANDARD profile described as "EXPLORATORY (not conservative)" | it allows marked unknown terrain |
| Routes shown on local 3D terrain, with the % of each route inside the patch | phase 3 |

Source check: samples spaced max(native cell, length/20 000), read budget 4096 cells per window;
checks NoData (unless the profile allows unknown terrain), step grade against `max_slope_deg`, and
hazard buffers. Output: `source_validation.status` VALIDATED / INVALID_ROUTE, problems, metrics.

## Evidence

| Test | Result |
|---|---|
| Unit tests `tests/test_v05.py` (flat, cliff, NoData gap, hazard, API metrics equal source metrics, unverified geometry) | PASS |
| Earlier routing tests (A* = Dijkstra on 25 random fields, no corner cutting, seams, polar cells, decimation) | PASS (backend 280/280) |
| Live: MOLA regional route | VALIDATED |
| Live: MOLA route across lon 0 (seam) | VALIDATED |
| Live: HiRISE Jezero, 77.4475E 18.4385N → 77.4525E 18.4425N, CONSERVATIVE + alternative | VALIDATED, 562 source samples at 1.017 m, max step grade 11.5° |
| Live: same route in local 3D ("Route in 3D") | Route A 100 % and Route B 100 % inside the patch, heights from the shown DEM |
| Smoke test `scripts/smoke_test.py` route check (MOLA, regional) | PASS, CALCULATED / VALIDATED |

## Limits

- Anything smaller than about two DEM cells is invisible (MOLA ~30 km, CTX ~40 m, HiRISE ~2–3 m).
- Rocks, regolith, lighting, communications, travel time: not modelled.
- Profiles are engineering assumptions, not validated rover or astronaut limits.
