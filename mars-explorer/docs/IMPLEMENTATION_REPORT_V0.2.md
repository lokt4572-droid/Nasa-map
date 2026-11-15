# MARS EXPLORER v0.2 — Implementation report

Date: 2026-11-14 · Branch `feature/v0.2-planetary-upgrade` (not pushed) · Restore point: tag `restore-point-v0.1` (= `dd91136`).
Commits: `0f1e420` (import, registry, terrain) · `56e7e83` (A*) · `0cdfa63` (planets) · `4aae2c5` (Earth) · `4b28705` (data, offline) · docs commit.
Totals since the restore point: 129 files changed, +8 504 / −347 lines, no file deleted.

Status vocabulary: **TESTED** (automated tests and/or verified in the running app with real data) · **IMPLEMENTED**
(code complete, unit-tested with mocks but not exercised end-to-end) · **PARTIALLY_IMPLEMENTED** · **NOT_IMPLEMENTED** ·
**BLOCKED_BY_EXTERNAL_SERVICE** · **REQUIRES_USER_DATA**.

## 1. Audit findings
Baseline before changes: backend 69/69, frontend 38/38, `tsc` clean, no secrets in Git (details in UPGRADE_PLAN.md §0).
A real-file audit with NASA's PDS4 MOLA MEGDR exposed bugs that synthetic tests could not:
B1 slope failed on real data (`"Metre"` unit), B2 DEMs accepted without vertical datum, B3 radius products accepted as
elevation, B4 no valid-value / control-point checks, B5 PDS label text ignored, B6/B7 single-planet CRS checks and no
planet on datasets, B8 settings not persisted, B9 no error boundary, B10 large bundle.
Mid-upgrade incident: a forked session edited the same files concurrently; both change sets were backed up to
`Desktop/projects/Nasa-v02-backups/2026-11-14_1247_working-tree/`, reconciled, and one writer kept.

## 2. Bugs fixed
| # | Bug | Fix | Status |
|---|---|---|---|
| B1 | slope/resolution broken on PDS4 MOLA (`"Metre"`) | case-insensitive unit check | TESTED (real MOLA) |
| B2 | DEM valid without vertical datum | datum required; read from PDS label or `--vertical-datum` | TESTED |
| B3 | radius values accepted as heights | radius guard (|median| > 1 000 km rejected) | TESTED |
| B4 | no valid-value / control checks | decimated statistics + 5 control cells | TESTED |
| B5 | PDS label ignored; sentences wrap lines | label parsing with whitespace normalisation | TESTED |
| B6/B7 | Mars-only CRS logic; no dataset planet | planet registry, `resolve_crs(planet=…)`, `Dataset.planet` | TESTED |
| B8 | settings lost on reload | localStorage (non-sensitive prefs only) | TESTED |
| B9 | one crash blanks the app | ErrorBoundary per view | IMPLEMENTED |
| B10 | 730 kB eager bundle | Cesium lazy-loaded as a separate chunk | TESTED (build) |
| — | A* missed detours outside the first window | growing search window (1×, 3×, whole DEM) | TESTED |
| — | CONSERVATIVE route save crashed (∞ in JSON) | `null` + explicit flag | TESTED |
| — | Trek layers not reloaded after switching planet | reset layer state on map mount | TESTED (browser) |
| — | Cesium assets copied to nested path → JSON got HTML | `rename.stripBase: 4` | TESTED (browser, no console errors) |
| — | Earth scale bar applied cos φ twice | fixed conversion | IMPLEMENTED |
| — | Earth point queries sent in EPSG:3857 | send EPSG:4326 | TESTED |
| — | provider cache not git-ignored | `data/cache/` ignored | TESTED |
| — | NUL bytes written into datasets/views.py by a patch | function rewritten | TESTED |

## 3. New functions (status)
### Mars
| Function | Status |
|---|---|
| v0.1 map, layers, point info, hazards, missions | TESTED (all 69 original tests still pass; browser) |
| Real MOLA MEGDR import (`import_dem --name mola-global`), 13-step report, checksum | TESTED (real NASA file) |
| CRS + vertical datum + units + nodata + values + control points validation | TESTED |
| Elevation / slope / aspect / roughness (TRI) / local relief / elevation difference / nodata coverage / area stats, uniform result schema | TESTED (analytic synthetic + real MOLA smoke) |
| Terrain visualization layers (elevation, hillshade, slope, aspect, roughness), windowed reads | TESTED (Mars, browser) |
| A* planner: CONSERVATIVE/STANDARD, waypoints, return, alternative, distance 2D/3D, profile, ascent/descent, unknown-terrain share, hazards | TESTED (synthetic + real MOLA, browser) |
| `INSUFFICIENT_TERRAIN_DATA` / `NO_PASSABLE_ROUTE` with `route: null` | TESTED |
| Saved routes GET/DELETE | TESTED |
| Mars polar products / polar stereographic maps | NOT_IMPLEMENTED |
### Platform
| Function | Status |
|---|---|
| Planet registry (backend + frontend), planets API, switcher, per-body CRS & scale | TESTED |
| Moon: LROC WAC mosaic + LOLA hillshade | TESTED (real tiles) |
| Moon: GLD100 / LOLA DEM | REQUIRES_USER_DATA (importer supports `--planet MOON`, tested with a synthetic lunar raster) |
| Moon: visual mask of GLD100 gaps on the map | NOT_IMPLEMENTED (coverage stated in catalog/registry) |
| Mercury: MDIS mosaic + USGS DEM hillshade, resolution labelled low-detail | TESTED |
| Mercury: MESSENGER DEM 665 m values | REQUIRES_USER_DATA |
| Venus preview screen with limits | TESTED |
| Venus GTDR data / projected maps | REQUIRES_USER_DATA / NOT_IMPLEMENTED |
| Unified Data Manager catalog (5 bodies, 6 types, statuses, licence, provenance) | TESTED |
| Import workflow steps, safe registration (path, extension, signature, size) | TESTED |
### Earth
| Function | Status |
|---|---|
| 2D map with OSM (attribution), click, measure | TESTED (browser; OSM tile 200) |
| NASA GIBS discovery from live GetCapabilities, date control with gaps, metadata | TESTED (live caps; tile URLs return 200) |
| Place search (Nominatim proxy) + coordinate search | TESTED (live) |
| Geolocation service (states, accuracy, tracking, Earth-only) | IMPLEMENTED (unit-tested with a mocked Geolocation API; not tried on a real device) |
| Weather current / hourly / 7 days / historical, charts, status | TESTED (live Open-Meteo + POWER, browser) |
| Point panel: local time, sunrise/sunset, weather | TESTED (browser) |
| 3D globe (CesiumJS) loads, imagery, pick, measure, fly-to | PARTIALLY_IMPLEMENTED (viewer verified; imagery/picking not visually verified — browser pane was hidden) |
| Real 3D terrain (Cesium World Terrain) | REQUIRES_USER_DATA (Cesium ion token) |
| Earth elevation / bathymetry values | REQUIRES_USER_DATA (Copernicus DEM / GEBCO) |
| Earth terrain colour layers (Elevation/Hillshade/Slope/Bathymetry from DEM) | NOT_IMPLEMENTED (legend only) |
| Sub-daily GIBS layers (IMERG 30 min, granules) | NOT_IMPLEMENTED |
| `/health/sources/` probes | TESTED (live: all UP) |
### Offline
| Function | Status |
|---|---|
| IndexedDB sync queue, PENDING/SYNCING/SYNCED/CONFLICT/FAILED | TESTED (fake-indexeddb) |
| Server idempotent creates + 409 conflicts | TESTED |
| Offline hazard fallback | IMPLEMENTED |
| ZIP export/import with manifest, SHA-256, planet/CRS/version checks | TESTED (unit); import → API registration IMPLEMENTED |
| Service worker (app shell, production only) | IMPLEMENTED (registration unit-tested; not run in a production deployment) |
| Offline map tiles, offline DEM, offline 3D terrain | NOT_IMPLEMENTED (app says OFFLINE READY: NO) |

## 4. NASA APIs / services integrated
NASA Solar System Treks WMTS (Mars, Moon, Mercury) · NASA GIBS WMTS (EPSG:3857 "best") · NASA POWER daily point API ·
NASA PDS Geosciences (MOLA MEGDR download). Plus Open-Meteo, OpenStreetMap tiles, Nominatim, CesiumJS.

## 5. Scientific data actually downloaded
Only `megt90n000cb.img/.xml/.lbl` (MGS MOLA MEGDR topography, 4 px/deg, 2.07 MB) from the PDS4 bundle, with the
user's consent; MD5 matches the PDS manifest; registered as `mola-global` (VALID, datum MOLA areoid GMM3).

## 6. Data requiring manual download (REQUIRES_USER_DATA)
Higher-resolution MOLA MEGDR (meg016…meg128), HiRISE DTMs, LROC GLD100, LOLA DEM, USGS MESSENGER DEM 665 m, Magellan
GTDR, Copernicus DEM GLO-30/90 tiles, GEBCO_2026 (+TID). Instructions: data/mars/README.md, DATA_SOURCES.md, EARTH_MODE.md.

## 7. Files created and changed
Created (main): backend `services/{planet_registry,raster_render,gibs,http_client,source_health}.py`,
`apps/{planets,weather,geocoding,earth}/`, `apps/routing/{models,profiles}.py`, `apps/routing/services/pathfinder.py`,
`apps/datasets/catalog.py`, `apps/core/sync.py`, 6 test modules; frontend `config/{planetRegistry,planetProjections}.ts`,
`services/{earthService,geolocationService}.ts`, `components/earth/*` (9), `components/mission/{RoutePlanner,OfflinePanel}.tsx`,
`components/common/{LineChart,ErrorBoundary}.tsx`, `components/map/MapOverlays.tsx`, `components/terrain/TerrainLayers.tsx`,
`components/layout/PlanetSwitcher.tsx`, `components/planets/VenusPreview.tsx`, `offline/{syncQueue,zipPackage,serviceWorker}.ts`,
`public/sw.js`, 4 test files; docs `UPGRADE_PLAN, EARTH_MODE, PLANET_REGISTRY, OFFLINE_MODE, LICENSES_AND_ATTRIBUTION, IMPLEMENTATION_REPORT_V0.2`.
Changed: 55 existing files (full list: `git diff --name-status restore-point-v0.1 HEAD`), migrations for datasets
(planet/licence/url), routing (Route), weather (WeatherSnapshot), missions & hazards (sync fields).

## 8. New backend endpoints
`/health/sources/` · `/planets/`, `/planets/{id}/`, `/planets/{id}/layers/` · `/datasets/catalog/` ·
`/terrain/{elevation,aspect,roughness,relief,nodata,difference,area,render}/` · `/routes/`, `/routes/profiles/`,
`/routes/{id}/` (GET, DELETE), `/routes/plan/` (real A*) · `/weather/{current,forecast,historical,status}/` ·
`/geocoding/search/` · `/earth/gibs/layers/`. Details: API_ENDPOINTS.md.

## 9. New frontend components
PlanetSwitcher, VenusPreview, EarthMap, EarthLayersPanel, PlaceSearch, MeasureTool, LocationPanel, WeatherPanel,
EarthTerrainPanel, EarthPointPanel, Globe3D/GlobeControls, RoutePlanner, OfflinePanel, TerrainLayers, MapOverlays
(TerrainOverlay, RouteOverlay), LineChart, ErrorBoundary; DataManager rewritten.

## 10. Tests passed
* Backend: **130/130** (`python manage.py test`), incl. the opt-in real-MOLA test (runs because the file is present).
* Frontend: **78/78** (`npm test`), `tsc -b` clean, `npm run build` OK.
* Live integration checks (no mocks), 2026-11-14:
  * Mars chain: Frontend → Django → Dataset registry → real MOLA DEM → terrain analysis → A* → map overlay (browser).
  * Weather chain: Earth map → search "Reykjavik" → Django → Open-Meteo / POWER → validated JSON → dashboard (browser).
  * GIBS chain: GetCapabilities → discovery → XYZ template → real tiles (MODIS, IMERG: HTTP 200).
  * Moon/Mercury/Mars Trek tiles generated by the app: HTTP 200. `/health/sources/`: all probed services UP.
* Browser console: no errors after the Cesium asset fix.

## 11. Tests not passed / not run
None failing. Not run: tests on a real phone/GPS; a production deployment of the service worker; Cesium with a real
ion token; visual tile rendering while the in-app browser pane was hidden (state and requests were checked instead).

## 12. Known limitations
* MOLA 4 px/deg ≈ 14.8 km/cell: slopes/routes are regional-scale only; profiles are heuristics, not validated models.
* Trek latitude type for map coordinates is not stated by NASA (marked NOT_VERIFIED in responses).
* GIBS reference layers (labels/borders) returned intermittent HTTP 500 on 2026-11-14 (server side; tiles stay empty).
* USGS Astrogeology pages refuse automated access (403): Mercury DEM / Moon WAC 100 m facts are from the specification.
* Earth DEM colour layers, sub-daily GIBS, Moon gap mask, polar projections, Venus maps: not implemented.
* No authentication; SQLite; single-machine use.
* Open-Meteo free tier and Cesium Community plan are non-commercial.

## 13. Remaining work
Earth DEM visualization layers; GLD100/LOLA import + polar handling; sub-daily GIBS time selection; offline tiles from
own rasters and Cesium terrain tiles (cesium-terrain-builder evaluation); waypoint/route offline queue and background
sync; authentication; PostgreSQL for multi-user; real-device geolocation testing.

## 14. Run commands (PowerShell)
* One click: `START-MARS-EXPLORER.bat` / `STOP-MARS-EXPLORER.bat`.
* Manual backend: `cd backend; .venv\Scripts\Activate.ps1; python manage.py migrate; python manage.py runserver`
* Manual frontend: `cd frontend; npm run dev` → http://127.0.0.1:5173
* Tests: `python manage.py test` · `npm test` · `npm run build`

## 15. Where to put URLs and tokens
`backend/.env` (from `.env.example`): `NOMINATIM_URL`, `OPEN_METEO_URL`, `NASA_POWER_URL`, `HTTP_USER_AGENT`,
`MAX_REGISTER_FILE_BYTES`, `NASA_API_KEY` (unused, server-only). `frontend/.env.local`: `VITE_API_BASE_URL`,
`VITE_TREK_WMTS_BASE`, `VITE_CESIUM_ION_TOKEN` (public in the browser; restrict and never commit).

## 16. Where to place DEMs
`mars-explorer/data/mars/` (= `MARS_DATA_DIR`): Mars `raw/mola/`, `raw/hirise/`; other bodies e.g. `raw/moon/`,
`raw/mercury/`, `raw/earth/`, `raw/venus/`; then `python manage.py import_dem --planet … --file … --name … [--vertical-datum …]`.

## 17. Sources
NASA Trek API https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars (and `?body=moon`, `?body=mercury`) ·
PDS MOLA https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/ ·
HiRISE DTM https://www.uahirise.org/dtm/ , https://hirise.lpl.arizona.edu/dtm/about.php ·
LROC WAC 100 m https://astrogeology.usgs.gov/search/map/moon_lro_lroc_wac_global_morphology_mosaic_100m ·
GLD100 https://data.lroc.im-ldi.com/lroc/view_rdr/WAC_GLD100 ·
Mercury DEM https://astrogeology.usgs.gov/search/map/mercury_messenger_global_dem_665m ·
Magellan GTDR https://pds.nasa.gov/ds-view/pds/viewDataset.jsp?dsid=MGN-V-RDRS-5-GDR-TOPOGRAPHIC-V1.0 ·
NASA GIBS https://nasa-gibs.github.io/gibs-api-docs/ · OSM tiles policy https://operations.osmfoundation.org/policies/tiles/ ·
Nominatim policy https://operations.osmfoundation.org/policies/nominatim/ · Open-Meteo https://open-meteo.com/en/docs ·
NASA POWER https://power.larc.nasa.gov/docs/ · Copernicus DEM https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM ·
GEBCO https://www.gebco.net/data-products/gridded-bathymetry-data · CesiumJS https://cesium.com/learn/cesiumjs-learn/ ·
Cesium World Terrain https://cesium.com/platform/cesium-ion/content/cesium-world-terrain/
