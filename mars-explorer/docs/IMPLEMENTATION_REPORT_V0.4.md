# MARS EXPLORER v0.4 — Implementation report

Date: 2026-11-15 · Branch `feature/v0.4-planetary-3d` (from `1b9d14a`, tag `restore-point-v0.3`),
merged locally into `main` once at the owner's request (Mars site pages connected); **nothing
pushed by this work**. Plan: `docs/UPGRADE_PLAN_V0.4.md`.

Status labels: IMPLEMENTED, TESTED, PARTIALLY_IMPLEMENTED, NOT_IMPLEMENTED, NO_DATA_COVERAGE,
BLOCKED_BY_EXTERNAL_SERVICE, REQUIRES_USER_CONFIGURATION.

## 1. Summary

A user can now go from a global view to real local terrain anywhere a published DTM exists — HiRISE
(~1 m) and CTX (~20 m) on Mars, Kaguya (~30 m, including the poles) on the Moon, Copernicus GLO-30
(~30 m) on Earth — without downloading anything: footprints come from the providers' catalogues and
values are read window by window from Cloud-Optimized GeoTIFFs. The route planner was rebuilt into
testable modules, crosses the DEM seam, decimates conservatively, re-validates every route and
reports data quality in a fixed schema. Cesium scenes for Mars and Moon 3D Tiles are implemented
(not seen streaming: no token). The Mars site pages are connected by URL (`/`, `/rover/`, `/map/`).
An optional AI layer interprets preferences and explains results; it never computes geometry.
Deployment is prepared and tested locally; not published.

## 2. Requirements status

| Part | Status |
|---|---|
| 1 Audit, protection, plan | IMPLEMENTED (`restore-point-v0.3`, plan document) |
| 2 Rendering architecture (OpenLayers 2D; Cesium 3D; Three.js local meshes; one viewer at a time) | IMPLEMENTED |
| 3.1 Earth: World Terrain, water mask, normals, attribution, failure fallback | IMPLEMENTED; streaming REQUIRES_USER_CONFIGURATION |
| 3.2 Mars Cesium 3D Tiles (3644333, `Ellipsoid.MARS`, provenance notice) | IMPLEMENTED; REQUIRES_USER_CONFIGURATION |
| 3.3 Moon Cesium 3D Tiles (2684829) | IMPLEMENTED; REQUIRES_USER_CONFIGURATION |
| 3.4 Mercury globe from verified imagery, no fake elevation | IMPLEMENTED (DEM import REQUIRES_USER_CONFIGURATION) |
| 3.5 Venus | NOT_IMPLEMENTED (optional; preview unchanged) |
| 4 Cesium configuration and licensing | IMPLEMENTED (`SETUP_CESIUM.md`; streaming only) |
| 5 Local 3D terrain from real DEMs (Mars, Moon, Earth) | IMPLEMENTED, TESTED (browser: Jezero, Gale; API: Gusev, Moon 0.7 N / 85 S / 89.2 S, Alps) |
| 5.3 Coverage database / STAC search | IMPLEMENTED, TESTED (USGS STAC + Copernicus tile-list adapter; `Dataset` remote fields) |
| 5.5 Binary elevation data, bounded, cancellable | IMPLEMENTED (float32 zlib; client aborts obsolete requests) |
| 5.7 Exaggeration 1/1.5/2/5x labelled visual only | IMPLEMENTED |
| 6 Coverage explorer with real footprints and metadata; auto source selection | IMPLEMENTED, TESTED |
| 7 Route planning rebuild | IMPLEMENTED, TESTED (see `ROUTE_PLANNING_ARCHITECTURE.md`) |
| 7.14 Zero-longitude bug | FIXED, TESTED (0/360 and ±180, live on MOLA) |
| 8 Hazard detection and provenance | IMPLEMENTED (DEM-derived candidates; provenance classes; model output never blocks unconfirmed) |
| 9.1 Earth 2D verified in the browser | TESTED (OSM + GIBS, pan/zoom, release on leaving) |
| 9.2 Earth 3D | IMPLEMENTED; REQUIRES_USER_CONFIGURATION |
| 9.3 ZIP package end-to-end | FIXED, TESTED (unit round trip + live disposable mission) |
| 9.4 Real geolocation | PARTIALLY_IMPLEMENTED: permission-denied path verified live; device checks pending |
| 9.5 Service worker on a production build | FIXED, TESTED (registration, activation, versioning, offline start, recovery) |
| 9.6 Earth terrain colours | IMPLEMENTED, TESTED (Copernicus hillshade/elevation/slope); bathymetry NO_DATA_COVERAGE |
| 9.7 Sub-daily imagery | IMPLEMENTED, TESTED (GOES-East/West, Himawari band 13, 10-minute steps from capabilities) |
| 9.8 Polar projections | PARTIALLY_IMPLEMENTED: lunar polar local terrain yes; polar 2D maps NOT_IMPLEMENTED |
| 9.9 Authentication | Decision documented: no accounts; public demo read-only (`PUBLIC_READ_ONLY`) |
| 10 Performance and memory | TESTED (`PERFORMANCE_REPORT_V0.4.md`) |
| 11 UI: location panel, 2D|3D workspace | IMPLEMENTED, TESTED |
| 12 Unified registry and adapters | IMPLEMENTED, TESTED (`/api/v1/datasets/registry/`) |
| 13 API | IMPLEMENTED (section 5) |
| A AI layer (A1–A7) | IMPLEMENTED, TESTED with mocks; perception UNAVAILABLE by design |
| B Deployment (B1–B9) | IMPLEMENTED, TESTED locally; NOT DEPLOYED (`DEPLOYMENT_REPORT.md`) |

## 3. Bugs found and fixed in v0.4

1. Routes could not cross the MOLA MEGDR 0/360 edge (v0.3 known issue) — stitched grid.
2. Decimated routing grids could erase a one-cell obstacle (nearest sampling) — conservative maxima.
3. Mission package import/export hardcoded to Mars.
4. Package restore left hazards of a deleted mission unlinked; existing records were kept silently — now re-linked and reported.
5. Service worker cache fill never worked (response cloned after the body was read) — offline start had no scripts.
6. WebGL contexts never released after leaving a globe or local 3D view.
7. Earth terrain colours: each tile stretched separately (same colour, different heights) — shared range.
8. Static Earth elevation legend did not match the renderer — real ramp and range.
9. Repeated remote reads re-downloaded the same blocks (11–13 s) — window cache (0.5 s).
10. Hazard analysis reported the capped number (50) as the count — true totals.
11. Comparison table rounded 0.2 m roughness to "0 m".
12. Route points always sent as planet MARS from the planner.
13. Catalogue search timed out on slow provider pages — one bounded retry, concurrent collections.
14. A merge on `main` (Mars pages) conflicted with the v0.4 app shell — resolved with URL routing; Mars page components unchanged.

## 4. Data sources

See `PLANETARY_3D_DATA_SOURCES.md` (verified 2026-11-15): USGS Astrogeology STAC (CTX, HiRISE,
Kaguya incl. polar), Copernicus DEM GLO-30 Public on AWS, NASA PDS (MOLA MEGDR, MD5 verified),
NASA Trek, NASA GIBS (incl. geostationary), Cesium ion assets (documented, not streamed here).

## 5. API added or changed (`/api/v1/`)

`datasets/search/`, `datasets/coverage/`, `datasets/register-remote/`, `datasets/registry/`,
`coverage/{planet}/`, `coverage/{planet}/search/`, `terrain/profile/`, `terrain/patch/`
(`source=auto`, `product=`, schema fields), `terrain/coverage/` (`remote=1`), `terrain/render/`
(`range=`), `routes/alternatives/`, `routes/hazards/derive/`, `routes/plan/` (v0.4 schema, mission
limits), `health/providers/`, `ai/status/`, `ai/interpret/`, `ai/plan/`, `ai/explain/`,
`ai/perception/detections/`. Hazards gained provenance fields. Errors keep the
`{"error": {"code", "message", "details"}}` shape; no server paths are returned.

## 6. Tests

| Suite | v0.3 | v0.4 |
|---|---|---|
| Backend (Django) | 166 | **273** passed |
| Frontend (Vitest) | 145 | **193** passed |
| TypeScript | clean | clean |

New backend suites: routing v0.4 (32), discovery (25), AI (22, models mocked), deployment (9),
Copernicus (7), registry (5), window cache (5), render range (2). Unit, mocked-integration, live
provider checks and manual browser checks are reported separately; mocked tests are not presented
as proof that a provider is up.

## 7. Browser verification (visible app, in-app browser)

| # | Check | Result |
|---|---|---|
| 1 | Earth 3D | Cesium viewer starts; "no terrain" status shown honestly (no token) |
| 2 | Mars 3D Tiles | REQUIRES_USER_CONFIGURATION panel with provenance notice (no token) |
| 3 | Moon 3D Tiles | same component; panel not opened separately |
| 4 | Mercury 3D | texture globe opened during the switching test |
| 5 | Mars global imagery | 18/18 tiles, first 1.9 s, complete 5.1 s |
| 6 | Mars high-resolution coverage | 32 DTM footprints at Jezero from the catalogue, drawn on the map |
| 7 | Jezero and Gale local detail | HiRISE 3D models in 3.2 s / 9.4 s |
| 8 | Moon polar terrain | API live (85 S, 89.2 S); not opened in the browser |
| 9 | Click-to-local-3D | yes, with 2D|3D side by side and footprint outline |
| 10 | No DEM coverage | API live (ocean, data gap); browser message verified in v0.3 |
| 11 | Route planning | HiRISE Jezero, planning level 3, via the assistant |
| 12 | Alternative routes | comparison table and explanation |
| 13 | Dateline crossing | API live on MOLA (0° and 180°); display split unit-tested |
| 14–15 | Layer failures, slow network | v0.3 results stand (loader unchanged) |
| 16 | Offline app startup | production build, `/`, `/rover/`, `/map/` |
| 17 | Repeated planet switching | 40 switches, one map viewport |
| 18 | Memory cleanup | heap flat; WebGL contexts released (after the fix) |

## 8. How to run

Unchanged: `START-MARS-EXPLORER.bat` or `.claude/launch.json` (backend 8000, frontend 5173,
`frontend-prod` preview 4173). Tests: `backend\.venv\Scripts\python.exe manage.py test`,
`npm test` in `frontend/`. Benchmarks: `scripts/benchmark_v04.py`; public check:
`scripts/smoke_test.py`. Deployment: `docs/DEPLOYMENT.md`.

## 9. Known limitations

`docs/KNOWN_LIMITATIONS_V0.4.md`.
