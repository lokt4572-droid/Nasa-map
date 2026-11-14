# Offline mode — what works and what does not

**Status: OFFLINE READY: NO.** Map tiles (NASA Trek, NASA GIBS, OpenStreetMap) always need the network. The header
says so permanently until real offline maps exist.

## Implemented
| Part | File | Behaviour |
|---|---|---|
| Service Worker | `frontend/public/sw.js`, `src/offline/serviceWorker.ts` | production build only; caches the app shell (index.html, `/assets/*`, `/cesiumStatic/*`) on use; network-first for pages; **never** caches cross-origin requests (Trek, GIBS, OSM) or `/api/*` |
| IndexedDB (v2) | `src/offline/localStore.ts` | stores `missionPackages`, `syncRecords` (+ `pendingHazards`, `routes` reserved) |
| Sync queue | `src/offline/syncQueue.ts` | local records with `client_id, created_at, updated_at, sync_status, version`; statuses PENDING → SYNCING → SYNCED / CONFLICT / FAILED |
| Offline hazard reports | `HazardPanel.tsx` | if the server is unreachable the report is saved on the device (PENDING) |
| Conflict sync | backend `apps/core/sync.py` | `client_id` makes creates idempotent; PATCH with stale `version` → 409 + server copy; the client keeps its change and asks: *Keep mine* / *Keep server* |
| ZIP packages | `src/offline/zipPackage.ts`, `OfflinePanel.tsx` | export/import, see below |

## Mission package (ZIP, format `mars-explorer/mission-package-zip` v1)
```
mission_package/
├── package.json        manifest: format, format_version, planet, crs, created_at, mission_client_id, files[{path, sha256, bytes}], offline_ready:false
├── metadata/app.json
├── imagery/README.txt  (no third-party tiles: their terms do not allow redistribution)
├── dem/datasets.json   (references + checksums of registered DEMs, no rasters)
├── terrain/README.txt
├── hazards/hazards.json
├── routes/routes.json
└── mission/mission.json
```
Import checks, in order: ZIP readable → manifest present/JSON → format & version → planet known and equal to the
current body → CRS equals the body's map CRS → every listed file present, size and SHA-256 match → JSON valid;
unlisted files are reported as warnings. Registration uses `client_id`s (hazards get deterministic ids), so importing
the same package twice creates no duplicates. Max package size accepted in the browser: 50 MB.

## Not implemented (honest list)
* Offline map tiles of any kind, offline DEM rendering in the browser, local DEM files inside packages.
* Waypoint offline queue (missions and hazards only); routes are exported read-only.
* Automatic background sync (sync is a user action: *Missions → Offline data → Sync now*).
* Offline 3D terrain.

## Offline maps and 3D terrain — design for later
* **Own tiles only:** generate tiles from local scientific rasters (e.g. MOLA MEGDR, GLD100, Copernicus DEM tiles) with
  GDAL (`gdal2tiles.py` / COG + a local tile server) and point the layer catalog to that server
  (`VITE_TREK_WMTS_BASE`-style override per body). Never prefetch tile.openstreetmap.org.
* **3D terrain tiles from Copernicus DEM:** candidate open-source tools to evaluate: *cesium-terrain-builder*
  (geo-data/cesium-terrain-builder; heightmap terrain; quantized-mesh only in forks) with a static file server or
  *cesium-terrain-server*. Not evaluated or installed in this version; the 3D globe must keep showing "NO TERRAIN"
  until such tiles are actually generated and served.
