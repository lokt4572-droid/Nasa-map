# MARS EXPLORER v0.2 — Final engineering audit & handoff

Audit date: 2026-11-14 · Auditor: Claude (single writer; no other session running) · Nothing was reset, discarded,
pushed or merged.

## 1. Git state
* **Branch:** `feature/v0.2-planetary-upgrade` (local only — `origin` has only `main` = `dd91136`). Not pushed, not merged.
* **Restore point:** tag `restore-point-v0.1` → `dd91136 First comm` (also `origin/main`).
* **Commits on the branch (newest first):**
  | Commit | Author | Content |
  |---|---|---|
  | `4947847` | Ahmad (the user) | "Adding planets and 3d" — the Phase 7 documentation (11 docs files, no code) |
  | `4b28705` | Claude | phase 6: data catalog, offline sync, ZIP packages, service worker |
  | `4aae2c5` | Claude | phase 5: Earth mode |
  | `0cdfa63` | Claude | phase 4: planet registry, Moon, Mercury, Venus preview |
  | `56e7e83` | Claude | phase 3: A* planner, terrain layers UI |
  | `0f1e420` | Claude | phase 1–2: real DEM import, terrain metrics |
* **Uncommitted (this audit), preserved in the working tree:** 11 modified files + 1 new test file + this report
  (see §11). Awaiting the user's decision to commit.
* `settings.py` showed a new timestamp but its content equals the committed version (no change).
* Repository hygiene notes (not changed): `mars-explorer-older-version-backup/` (61 older files) and
  `frontend/tsconfig.tsbuildinfo` (build artefact) are tracked. Secrets are not tracked (`.env`, `.env.local`,
  `db.sqlite3`, `data/mars/**`, `data/cache/` are ignored).

## 2. Implementation status (from IMPLEMENTATION_REPORT_V0.2.md, re-checked)
**Fully implemented and tested:** Mars Trek map; real MOLA import with full validation; elevation, slope, aspect,
roughness, local relief, elevation difference, nodata coverage, area statistics; Mars terrain visualization layers;
A* planner (profiles, waypoints, return/alternative, profile chart, unknown-terrain share, hazards, saved routes);
planet registry and switching; Moon and Mercury Trek layers; Venus preview screen; unified data catalog; safe
dataset registration; GIBS discovery with date control; place/coordinate search; weather current/hourly/7-day/
historical; sync with conflicts (backend + IndexedDB queue); ZIP packages (unit level); one-click launcher.

**Partially implemented:** Earth 3D globe (viewer, imagery, picking, measuring implemented; picking/imagery not
visually verified because the in-app browser pane was hidden) · ZIP import → API registration (code complete,
not run end-to-end in the browser) · Venus (preview only, no map) · geolocation (unit-tested with a mocked API, not
tried on a real device) · service worker (registration unit-tested, never deployed in production mode) · offline
hazard fallback (implemented, not exercised with the server actually down).

**Not implemented:** offline map tiles / offline DEM / offline 3D terrain · Earth DEM colour layers · sub-daily
GIBS time selection · Moon GLD100 gap mask on the map · polar projections (Mars/Moon) · Venus maps · waypoint offline
queue, background sync · authentication · geology layers.

**Requires user data / configuration:** real 3D terrain (Cesium ion token) · Earth elevation/bathymetry (Copernicus
DEM, GEBCO) · Moon GLD100/LOLA DEM · Mercury USGS DEM · Venus GTDR · HiRISE DTMs · higher-resolution MOLA.

## 3. MOLA DEM metadata (verified against the file)
| Item | Value |
|---|---|
| Dataset | `mola-global`, id 1, planet MARS, status VALID |
| Product | MGS MOLA MEGDR topography `megt90n000cb` (PDS4), meg004 |
| Grid | 1440 × 720 cells, 0.25° per cell = 4 px/deg (360 / 1440 exactly) |
| Resolution | **14 817.85 m per cell** = 0.25° on the label's 3 396 000 m sphere (equator, N–S); E–W ground size 10.48 km at 45°, 5.07 km at 70° |
| CRS | "Equirectangular Mars" (sphere R = 3 396 000 m), planetocentric, east-positive |
| Vertical datum | MOLA areoid GMM3 (mgm1025) — from the PDS label statement "Topography is the planetary radius minus the areoid radius" |
| Units / nodata | metre / none declared (warning recorded; 100 % valid in decimated read) |
| Integrity | label 15 509 B + image 2 073 600 B = 2 089 109 B; per-file SHA-256 stored; `.img` MD5 equals the PDS manifest value `e963c832…` |

**Defect found and fixed in this audit:** `file_size` and `checksum` previously covered only the 15 kB `.xml` label,
not the elevation data. Now every file GDAL reads for the product is sized and hashed (`metadata.product_files`,
combined `checksum`); `mola-global` was re-registered in place (same id).

## 4. Routing: DEM resolution suitability (added in this audit)
Every route response (success **and** failure) now contains `data_quality`:
`dem` (name, instrument, product, resolution, datum, CRS), `grid_cell_size_m` (E–W min/max, N–S),
`grid_decimation_factor`, `window_nodata_fraction`, `route_unknown_terrain_fraction`, `latitude_handling`
(NONE / CONVERTED_… / NOT_VERIFIED) and `resolution_assessment`.

| Effective cell | Class | Meaning |
|---|---|---|
| ≤ 2 m | DETAILED_TRAVERSE_STUDY | metre-scale DTM; still not a safety assessment |
| ≤ 100 m | SITE_RECONNAISSANCE | landforms visible, rocks and small craters not |
| > 100 m | REGIONAL_PLANNING_ONLY | e.g. global MOLA; unsuitable for astronaut-scale routes |

`suitable_for_astronaut_scale_route_safety` is **always false**; `astronaut_scale_route_safety` is `NOT_SUITABLE`
for cells > 1 m and `NOT_ASSESSED_NO_VALIDATED_MODEL` otherwise. The effective cell is the coarsest of the DEM
resolution and the (possibly decimated) routing grid. Real MOLA route: class REGIONAL_PLANNING_ONLY, effective
cell ≥ 14 817.8 m, smallest resolvable feature ≈ 29.6 km. The Route Planner shows a red "NOT SUITABLE FOR
ASTRONAUT-SCALE ROUTE SAFETY" banner and an "Input data quality" card. Thresholds live in
`backend/apps/routing/profiles.py` and are documented as engineering limits.

## 5. A* and unknown terrain (verified by tests)
* **CONSERVATIVE:** cells without DEM data are forbidden; a start/end on such a cell or a path that would need to
  cross them → `INSUFFICIENT_TERRAIN_DATA`, `route: null` (tested: gap band, start on a hole).
* **STANDARD:** by the original specification it may cross gaps at 5× cost **up to 20 % of the route distance**, and
  reports the share (`unknown_terrain_fraction`); above 20 % → `INSUFFICIENT_TERRAIN_DATA`. Unknown cells are never
  treated as safe, but STANDARD does not reject them outright. **Decision for the user:** if STANDARD must also
  reject all unknown terrain, set `allow_unknown_terrain=False` in `profiles.py` (one-line change, tests exist).
* Input resolution and quality are reported in `data_quality` (§4) for every response.

## 6. Earth 3D globe vs 3D terrain
* **3D globe** (CesiumJS viewer, imagery draped on the WGS 84 ellipsoid): AVAILABLE.
* **3D terrain:** `REQUIRES_CESIUM_TERRAIN_CONFIGURATION` without `VITE_CESIUM_ION_TOKEN`; the banner reads
  "3D GLOBE without 3D TERRAIN … smooth WGS 84 ellipsoid: no mountains or valleys". With a token the status is
  `CONFIGURED_NOT_VERIFIED` (never asserted as working by this project). The sidebar shows both statuses separately.
  Picked heights are "DATA NOT AVAILABLE (no terrain)" without terrain. Status: no token configured on this machine.

## 7. Offline independence
Mission records, hazard reports and ZIP packages do not depend on map tiles: the sync queue and ZIP code run in tests
without any map; packages contain only JSON plus README files (test asserts no `.png/.jpg/.webp` and only
`imagery/README.txt`); `sw.js` never caches cross-origin tiles or `/api/*`. Offline map tiles are **not implemented**
and the header permanently shows "OFFLINE READY: NO".

## 8. External integrations — live vs mocked
**Live checks run during this audit (2026-11-14 ≈ 09:59 UTC, real network, no mocks):**
| Service | Result |
|---|---|
| `/health/sources/?refresh=1` | NASA Trek UP, NASA GIBS UP, Open-Meteo UP, NASA POWER UP, Nominatim NOT_PROBED (policy) |
| NASA GIBS GetCapabilities (re-fetched) | 14/14 curated layers available; IMERG latest 2026-11-12 (lags today) |
| Open-Meteo current (Paris) | HTTP 200, live, valid_time 2026-11-14T10:45, model grid cell 48.853/2.355 |
| NASA POWER Sept 2026 (Paris) | 30 days, units C/%/mm/day/m/s, sources MERRA2 + POWER |
| Nominatim "Kathmandu" | 2 results, live (from_cache false) |
| Earlier live checks in this release | Trek Mars/Moon/Mercury tiles 200; GIBS MODIS + IMERG tiles 200; OSM tile 200; GIBS reference-layer tiles intermittently HTTP 500 (server side) |

**Mocked (unit tests, no network):** all of `tests/test_earth_v02.py` (Open-Meteo, POWER, Nominatim, GIBS parsing,
source health) and the frontend tests for geolocation, terrain render fetch, API client, sync queue.
Real-data tests without mocks: real MOLA tests (`test_import_v02`, `test_audit_v02`) and the WMTS fixtures, which are
unmodified NASA capabilities documents.

**Defect found and fixed in this audit:** weather `from_cache` was computed from age > 1 s, so an answer served
from the cache within a second was reported as live. It now means "the provider was not called for this response"
(test added).

## 9. Dependencies, environment, external requirements
**Backend (Python 3.14):** Django 6.0.10, djangorestframework 3.18.3, django-cors-headers 4.9.0, python-dotenv 1.2.4,
numpy 2.5.4, scipy 1.18.1, pyproj 3.8.0; optional `requirements-raster.txt`: rasterio 1.5.2 (bundles GDAL 3.12.2).
`pip check`: no broken requirements. No new Python packages in v0.2 (HTTP via stdlib urllib, PNG via zlib).
**Frontend:** runtime ol 10.11, proj4 2.22, react/react-dom 19.3, zustand 5.1, **new:** cesium 1.147 (lazy, ~40 MB
dependency), fflate 0.8.3; dev: vite 8.3, vitest 5.1, typescript 7.0, jsdom 31, fake-indexeddb 6.2, @vitejs/plugin-react 6.3,
**new:** vite-plugin-static-copy 4.1. `npm audit --omit=dev`: 0 vulnerabilities.
**Environment variables:** backend `DJANGO_SECRET_KEY, DEBUG, ALLOWED_HOSTS, FRONTEND_ORIGIN, MARS_DATA_DIR, LOG_LEVEL,
NASA_API_KEY (unused), HTTP_USER_AGENT, NOMINATIM_URL, OPEN_METEO_URL, NASA_POWER_URL, MAX_REGISTER_FILE_BYTES`
(the user's `.env` lacks the last five → built-in defaults are used); frontend `VITE_API_BASE_URL, VITE_TREK_WMTS_BASE,
VITE_CESIUM_ION_TOKEN` (not set → no 3D terrain).
**External services (internet required):** NASA Trek, NASA GIBS, NASA POWER, Open-Meteo (non-commercial free tier),
OpenStreetMap tiles + Nominatim (usage policies), Cesium ion (optional, token, Community plan non-commercial).
No API keys are required for the current features.

## 10. Verification totals
Backend **140/140** (`manage.py test`; 10 audit tests added), `manage.py check` clean, no missing migrations.
Frontend **78/78** (`npm test`), `tsc -b` clean, `npm run build` OK.

## 11. Changes made during this audit (uncommitted)
| File | Change |
|---|---|
| `backend/services/dataset_manager.py`, `services/dem_reader.py` | integrity over all product files (`product_files`, combined checksum) |
| `backend/apps/routing/profiles.py`, `apps/routing/views.py` | resolution suitability classes, `data_quality` on every plan response |
| `backend/apps/weather/services.py` | correct `from_cache` semantics |
| `backend/tests/test_audit_v02.py` (new), `tests/test_earth_v02.py` | audit tests, cache-flag test |
| `frontend/src/components/mission/RoutePlanner.tsx`, `types/api.ts` | suitability banner + input-quality card |
| `frontend/src/components/earth/Globe3D.tsx`, `earth.test.ts` | separate globe vs terrain statuses |
| `frontend/src/offline/offlineV02.test.ts` | assert packages carry no tiles |
| `docs/HANDOFF_REPORT_V0.2.md` | this report |
Database: `mola-global` re-registered in place (corrected size/checksum); weather cache table cleared for live checks.

## 12. Open decisions for the user
1. Commit this audit to the feature branch.
2. STANDARD profile: keep limited unknown-terrain crossing (≤ 20 %) or reject all unknown terrain.
3. Push / merge `feature/v0.2-planetary-upgrade` into `main` (not done; requires approval).
4. Optional: untrack `frontend/tsconfig.tsbuildinfo` and `mars-explorer-older-version-backup/`.
5. Optional: add a Cesium ion token (restricted to your domain) for real 3D terrain.
