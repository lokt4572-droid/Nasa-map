# MARS EXPLORER v0.2 — Upgrade plan

Audit date: 2026-11-14. Branch: `feature/v0.2-planetary-upgrade`.
Restore point: Git tag `restore-point-v0.1` (= commit `dd91136 "First comm"`, also on `origin/main`).

## 0. Audit results

### Baseline checks (before any change)

| Check | Result |
|---|---|
| `python manage.py check` | no issues |
| `python manage.py test` | **69 tests, OK** |
| `npm test` (vitest) | **38 tests, OK** (4 files) |
| `tsc -b` | clean |
| Secrets in Git | none: `.env`, `.env.local`, `db.sqlite3`, `node_modules`, `.venv` are ignored |
| Git | `main` clean, pushed to `github.com/lokt4572-droid/Nasa-map`; the folder `mars-explorer-older-version-backup/` (older unrelated version, 61 files) is tracked |

### What really works (v0.1)

| Function | State |
|---|---|
| NASA Trek WMTS for Mars (4 layers, via GetCapabilities) | works, verified in browser |
| Mars CRS registration, point pick, coordinate display | works |
| Hazards CRUD, Missions + Waypoints CRUD | works |
| `import_dem` CLI, `/terrain/sample|slope|coverage` | work on synthetic rasters only |
| Route planning | interface only (501) |
| Offline | JSON export + IndexedDB copy only; no Service Worker, no sync |
| One-click launcher | works |

### Real-data audit of the DEM importer

Downloaded (with the user's consent) the smallest global PDS4 MOLA MEGDR topography:
`megt90n000cb.img` + `.xml` label (MD5 matches the PDS bundle manifest). Running the
existing inspector on it revealed:

## 1–2. Bugs found and their causes

| # | Bug | Cause |
|---|---|---|
| B1 | Slope / roughness fail on the real MOLA DEM; resolution reported as `None` | GDAL names the axis unit `"Metre"`; code compared case-sensitively with `"metre"` (`terrain_analysis.cell_size_m`) |
| B2 | A DEM without vertical datum becomes `VALID` with `UNSPECIFIED` datum | datum missing was only a warning (`dataset_manager.register_dataset`) |
| B3 | A planetary **radius** product (e.g. `megr…`, values ≈ 3.39·10⁶ m) would be accepted as elevation | no plausibility check of value range |
| B4 | Import never checks that the raster contains any valid value, nor reads control points | not implemented |
| B5 | PDS4 label text (datum, product description) is ignored | importer only used GDAL tags, which are empty for PDS4 |
| B6 | Only Mars CRS accepted everywhere (`is_mars_crs`, `buildWmtsSource` hard-coded to the Trek Mars CRS) | single-planet design |
| B7 | `Dataset` has no planet field — a lunar DEM could be sampled with Mars coordinates | single-planet design |
| B8 | Settings (longitude display) lost on reload | kept only in memory |
| B9 | No React error boundary: a component exception blanks the whole app | not implemented |
| B10 | Main JS chunk > 500 kB | everything bundled eagerly |

## 3. Files to change

Backend: `services/dataset_manager.py`, `services/terrain_analysis.py`, `services/mars_coordinates.py`,
`services/dem_reader.py`, `apps/datasets/{models,serializers,views}.py` + migration,
`apps/datasets/management/commands/import_dem.py`, `apps/terrain/{views,urls}.py`,
`apps/routing/{views,urls}.py`, `apps/core/views.py`, `config/{settings,urls}.py`,
`apps/missions/models.py`, `apps/hazards/models.py` (sync fields), tests.

Frontend: `components/map/MarsMap.tsx` (planet-aware), `services/marsMapService.ts` (CRS per layer),
`store/useAppStore.ts`, `components/layout/*`, `components/data/DataManager.tsx`, `App.tsx`,
`vite.config.ts`, `offline/*`.

## 4. Components to create

Backend: `services/planet_registry.py`, `apps/planets/`, `apps/routing/services/pathfinder.py`,
`apps/routing/profiles.py`, `apps/routing/models.py` (saved routes), `apps/weather/`,
`apps/geocoding/`, `apps/earth/` (GIBS capabilities discovery), `apps/datasets/catalog.py`,
`services/raster_render.py` (PNG terrain layers), `/health/sources/`.

Frontend: `config/planetRegistry.ts`, `config/planetProjections.ts`, `components/layout/PlanetSwitcher.tsx`,
`components/earth/*` (EarthMap, GibsLayerPanel, PlaceSearch, LocationPanel, WeatherPanel, Globe3D, MeasureTool),
`components/mission/RoutePlanner.tsx`, `components/terrain/TerrainLayers.tsx`,
`services/geolocationService.ts`, `services/weatherService.ts`, `components/common/ErrorBoundary.tsx`,
`offline/serviceWorker.ts` + `public/sw.js`, `offline/syncQueue.ts`, `offline/zipPackage.ts`.

## 5. Dependencies

* `cesium` (3D globe; lazy-loaded) + `vite-plugin-static-copy` (Cesium assets).
* `fflate` (ZIP export/import in the browser, small, MIT).
* No new Python packages: HTTP via `urllib` (stdlib), PNG encoding via `zlib` (stdlib), caching via Django cache.

## 6. External sources (all verified 2026-11-14 unless noted)

| Source | Use | Verification |
|---|---|---|
| NASA Trek WMTS — Mars, Moon (`urn:ogc:def:crs:EPSG::104903`), Mercury (`urn:ogc:def:crs:IAU2000::19900`) | planetary imagery | GetCapabilities fetched |
| Trek — Venus | — | **does not exist** (Trek config lists moon, mars, titan, vesta, ceres, mercury) |
| PDS4 MOLA MEGDR | Mars DEM | downloaded, MD5 verified |
| LROC GLD100 | Moon DEM | page read: 79°S–79°N, 98.2 %, formal resolution ≈ 300 m, vertical 10–20 m → REQUIRES_USER_DATA |
| USGS MESSENGER DEM 665 m, LROC WAC 100 m | Mercury / Moon | USGS pages return HTTP 403 to automated clients → values from the user's specification, marked "not machine-verified" |
| Magellan GTDR (PDS) | Venus | page read: ≈ 5×5 km/px, 4 projections, values are planetary radius |
| NASA GIBS WMTS | Earth imagery, time dimension | GetCapabilities (EPSG:3857) parsed on the backend |
| OpenStreetMap tiles, Nominatim | Earth basemap, place search | usage policies read |
| Open-Meteo | forecast | terms read: non-commercial free tier, 10 000 calls/day, CC BY 4.0 |
| NASA POWER daily point API | historical | docs read: 1981-01-01 → near real time |
| Copernicus DEM GLO-30/90 | Earth DEM | page read: DSM, EGM2008, 2011–2015 → REQUIRES_USER_DATA |
| GEBCO_2026 + TID | Earth topo-bathymetry | page read: 15″, ~4 GB → REQUIRES_USER_DATA |
| Cesium ion / World Terrain | 3D | Community plan: personal non-commercial, quotas; token needed by CesiumJS API |

Conflicting values found (kept side by side, never silently merged):
* Mercury radius: PROJ `IAU_2015:19900` = 2 440 530 m; `ESRI:104974` "Mercury_2015" = 2 439 400 m; Trek declares `IAU2000::19900`.
* Mars MEGDR uses a 3 396 000 m sphere; the Trek map uses the 3 396 190 m Mars 2000 ellipsoid.

## 7. Functions to implement

Mars: full DEM import report (B1–B5), terrain metrics (elevation, slope, aspect, roughness,
local relief, elevation difference, nodata coverage) with a uniform result schema, terrain
raster layers (elevation, hillshade, slope, roughness, aspect) rendered by window reading,
A* planner (2 profiles, waypoints, return path, alternative, profile, ascent/descent,
unknown-terrain share), saved routes.
Platform: planet registry (Earth, Mars, Moon, Mercury, Venus preview), planet switcher, per-planet maps.
Earth: OSM + GIBS 2D map with time control, place search, coordinate search, measure,
geolocation, weather (Open-Meteo, POWER), 3D globe (Cesium), elevation legend.
Data: unified catalog with planet/type filters and statuses; import workflow.
Offline: Service Worker (app shell only), IndexedDB sync queue with conflict handling, ZIP packages.

## 8. Limitations that will remain

* No validated traversability model; route costs are engineering heuristics.
* Terrain products at the DEM's own resolution only (the global MOLA file is ≈ 14.8 km/px).
* No offline map tiles (OSM forbids it; Trek/GIBS tiles are not pre-fetched).
* Earth DEM/bathymetry, GLD100, MESSENGER DEM, GTDR require manual download.
* Cesium World Terrain requires the user's own ion token.
* No authentication.

## 9. How changes are verified

After each phase: `manage.py check`, `manage.py test`, `npm test`, `npm run build`, plus
browser checks. External services are mocked in unit tests; separate opt-in live checks
(`manage.py check_sources`, `/api/v1/health/sources/`) prove real availability.

## 10. Order

1. Importer fixes + real MOLA import (B1–B5) → tests.
2. Terrain metrics + terrain layers → tests.
3. A* planner + routes API + UI → tests.
4. Planet registry (backend + frontend), planet-aware map, Moon/Mercury layers, Venus preview → tests.
5. Earth backend (GIBS discovery, geocoding, weather) → tests.
6. Earth frontend (2D, time, search, geolocation, weather, measure) → tests.
7. Cesium 3D globe.
8. Data catalog + offline (SW, sync, ZIP) → tests.
9. Docs, full test run, implementation report.
