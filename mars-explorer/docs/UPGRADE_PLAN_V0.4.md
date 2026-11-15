# MARS EXPLORER v0.4 — Upgrade plan

Date: 2026-11-15 · Branch `feature/v0.4-planetary-3d` (from `1b9d14a`, tag `restore-point-v0.3`).
Written after reading the v0.2/v0.3 reports **and** the source. Nothing is pushed or merged
without approval.

## 1. Audit (Phase 0–1)

| Item | Found |
|---|---|
| Git | clean tree on `feature/v0.3-performance-globes` (pushed); tags `restore-point-v0.1/-v0.2`; new tag `restore-point-v0.3` |
| Running processes | Vite dev server and Django `runserver` (read-only for the code); no other writer |
| Cesium token | `VITE_CESIUM_ION_TOKEN` is **not set** in `frontend/.env.local` → every Cesium ion feature (Mars/Moon 3D Tiles, World Terrain) is REQUIRES_USER_CONFIGURATION and cannot be verified live in this session |
| Local DEMs | only MOLA MEGDR 4 px/deg (`megt90n000cb`, ≈ 14.8 km cells) |
| Rasterio | 1.5.2 / GDAL 3.12.2 with GTiff + COG and HTTP range reads (verified live) |

### Existing feature status

| Feature | Status in v0.3 | v0.4 action |
|---|---|---|
| 2D maps (OpenLayers, Trek WMTS, GIBS) | working, tested | keep |
| Three.js texture globes (Earth/Mars/Moon/Mercury) | working | keep as the no-token fallback; Cesium scene added for Mars/Moon/Earth |
| Cesium Earth globe | works, terrain only with token | add water mask, vertex normals, attribution, terrain-failure fallback, setup doc |
| Local 3D terrain | works, but only from MOLA (regional) | read real CTX / HiRISE / Kaguya DTMs remotely (COG windows) |
| Coverage explorer | imagery mosaics from a hand-kept catalogue; DEM coverage = registered files only | add live DTM footprints from the USGS STAC catalogue |
| A* routing | one 580-line module + logic in the view; routes cannot cross the MEGDR seam | split into services, stitch the seam, new status/metrics schema |
| Hazards | manual reports only | DEM-derived hazard analysis, provenance classes |
| Earth 2D canvas, ZIP import end-to-end, service worker in a production build, real geolocation | not verified in v0.3 | verify in the visible browser, fix what fails |

### Bugs and root causes

1. **Routes do not cross the DEM seam** — `pathfinder.build_grid` reads one contiguous pixel
   window; MEGDR is centred on 180° so lon 0°/360° is its left/right edge.
   Fix: read the window in two column segments (as `raster_render` already does) and build
   the planning grid in a continuous, unwrapped longitude.
2. **Route business logic lives in the API view** (`routing/views.py`) — hard to test without
   Django. Fix: `route_service.py` + smaller modules.
3. **`dem_reader` wraps every path in `Path()`** — blocks remote COGs. Fix: one `open_raster`
   helper that accepts local paths and allow-listed HTTPS URLs.
4. **Coverage explorer says "no DEM"** wherever no file was imported, although public DTMs
   exist. Fix: STAC footprint search.

## 2. Data sources (verified live 2026-11-15 unless stated)

| Body | Source | Use | Access | Licence |
|---|---|---|---|---|
| Mars | USGS STAC `mro_ctx_controlled_usgs_dtms` (≈ 20 m, aligned to MOLA) | local terrain, routing level 2 | STAC search + COG range reads | CC0-1.0 |
| Mars | USGS STAC `mro_hirise_socet_dtms` (≈ 1–2 m) | local terrain, routing level 3 | same | CC0-1.0 |
| Mars | MOLA MEGDR (PDS Geosciences), local file | regional context only | local raster | PDS public |
| Mars | Cesium Mars, ion asset 3644333 (CRS IAU_2015:49901) | 3D globe visualisation | Cesium ion token | Cesium ion ToS — **streaming only, no download/redistribution** |
| Moon | USGS STAC `kaguya_terrain_camera_usgs_dtms_v2` (≈ 33 m at the test site, 70°N–70°S) | local terrain, routing | STAC + COG | CC0-1.0 |
| Moon | Cesium Moon, ion asset 2684829 | 3D globe visualisation | Cesium ion token | Cesium ion ToS |
| Earth | Cesium World Terrain | 3D visualisation | Cesium ion token | Cesium ion ToS |
| Earth | Copernicus DEM GLO-30/90 (DSM) | local terrain | needs a Copernicus Data Space account or a public mirror → REQUIRES_USER_CONFIGURATION unless a keyless COG mirror is verified | Copernicus licence |
| Mercury | MESSENGER MDIS mosaics (Trek WMTS) | globe texture | existing | NASA public |
| Mercury | MESSENGER global DEM (USGS, 665 m) | local terrain | manual import (`import_dem`) | public |

Cesium community plan: "personal and non-commercial use", unfunded education allowed; 15 GB
streaming / month. Whether a given hackathon qualifies is the account holder's decision — the
app only documents it (`docs/SETUP_CESIUM.md`).

## 3. Architecture

- **2D**: OpenLayers, unchanged.
- **3D globe**: one Cesium `PlanetScene` component for Earth, Mars and Moon (one viewer at a
  time, created once per body, destroyed on unmount). Mars/Moon follow the official pattern
  (`globe: false`, 3D Tiles from ion). `Ellipsoid.default` is set to the body's ellipsoid
  while that scene is mounted and **restored on unmount**; only one Cesium viewer exists at a
  time, so no scene sees another body's ellipsoid. Without a token: the Three.js texture
  globe is shown with an explicit "CESIUM NOT CONFIGURED" status. Mercury: Three.js globe
  (no Cesium asset exists).
- **Local 3D**: Three.js `BufferGeometry` from a height grid served by the backend. The grid
  comes from the finest valid DEM: registered local files, or a remote COG found via STAC.
- **Analysis and routing**: always from the DEM grid on the backend, never from a render mesh.
- **Remote DEMs**: a STAC item is registered as a `Dataset` row whose `file_path` is the HTTPS
  COG URL (hosts allow-listed). All existing endpoints (sample, slope, patch, routes) then
  work on it through one `open_raster` helper. Nothing is downloaded in bulk.

## 4. Files

New backend: `services/remote_raster.py`, `apps/datasets/services/{stac_client,coverage_service,dataset_discovery}.py`,
`apps/routing/services/{route_service,cost_surface,terrain_constraints,route_validator,route_metrics,spatial_grid,hazard_analysis}.py`,
tests `test_stac_v04.py`, `test_routing_v04.py`, `test_terrain_v04.py`, `test_package_v04.py`.

Changed backend: `services/dem_reader.py`, `dataset_manager.py`, `raster_render.py`,
`terrain_patch.py`, `apps/terrain/views.py`, `apps/routing/views.py`, `pathfinder.py`,
`apps/datasets/{models,views,urls}.py`, `apps/hazards/models.py`, `apps/core/{views,urls}.py`.

New frontend: `components/planetary/{PlanetScene,PlanetaryGlobe3D,LocalTerrainViewer,TerrainLoadingOverlay}.tsx`,
`services/planetary/{cesiumSceneService,planetaryCoordinateService}.ts`, `services/terrainMeshService.ts`,
`components/coverage/DatasetCoveragePanel.tsx`.

Changed frontend: `App.tsx`, `ViewModeSwitch.tsx`, `earth/Globe3D.tsx`, `terrain/LocalTerrain3D.tsx`,
`map/CoverageExplorer.tsx`, `mission/RoutePlanner.tsx`, `mission/HazardPanel.tsx`, `services/api.ts`, `types/api.ts`.

## 5. API changes (all under `/api/v1/`, existing routes kept)

- `GET datasets/search/` — planet, data_type, bbox | latitude+longitude(+radius_m), max_resolution
- `GET datasets/coverage/`, `GET coverage/{planet}/`, `GET coverage/{planet}/search/`
- `GET terrain/profile/` — elevation profile between two points
- `GET terrain/patch/` — adds `source=auto|local`, schema fields `coverage_status`, `processing_status`, `sample_spacing_m`
- `POST routes/plan/` — new `status`, `route_class`, `data_quality`, `metrics` (avg slope), `warnings`; `POST routes/alternatives/`
- `GET health/providers/`

## 6. Performance targets

| Metric | Target |
|---|---|
| Local patch from a local DEM | < 1 s |
| Local patch from a remote COG (256²) | < 15 s, bounded by provider latency (reported separately) |
| STAC footprint search | < 5 s, cached 1 h |
| Mesh build 256² | < 100 ms |
| Route on a 300² grid | < 5 s |
| WebGL contexts alive after 10 planet switches | ≤ 2 |

## 7. Testing

Unit (synthetic rasters, labelled as synthetic), mocked integration (STAC responses from
recorded fixtures), live provider checks (separate script, reported with date), manual checks
in the visible browser. All 166 backend and 145 frontend v0.3 tests stay green.

## 8. Known limits before starting

- No Cesium token → Cesium scenes are implemented but cannot be seen working in this session.
- Remote DEM reads depend on USGS S3 latency and need the network.
- Copernicus DEM needs credentials or a verified keyless mirror.
- Vertical datums differ between products (MOLA areoid, sphere radius); patches from
  different DEMs are never merged.

## 9. Order

Phases 0–11 exactly as in the specification; one commit per phase.
