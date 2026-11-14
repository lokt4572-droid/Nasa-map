# Phase 4 — click-to-explore local 3D terrain (2026-11-14)

Raw notes for `docs/LOCAL_3D_TERRAIN_REPORT.md` (Phase 7).

## Backend: `GET /api/v1/terrain/patch/`

Query: `planet`, `longitude|lon`, `latitude|lat`, `radius_m` (100–500 000, default 20 000),
`max_dimension` (16–512, default 256), optional `dataset`, `crs`, `lat_convention`.

- Uses the finest registered, validated DEM covering the point (`services/terrain_patch.py`).
- **Never finer than the DEM**: grid side = min(max_dimension, native cells across the patch);
  nearest DEM cell, no interpolation. Unit test: every patch value is a value of the DEM.
- Fewer than 4 native cells across → 422 `DEM_TOO_COARSE_FOR_PATCH` with `native_resolution_m` and
  `min_radius_m`. No DEM → 404 `DEM_NOT_AVAILABLE`. Patch crossing a pole → 422 `PATCH_CROSSES_POLE`.
- Response: centre, bbox, grid (size, cell sizes in m, native cells across, resampling), dataset
  (id, name, instrument, product, source, licence, native resolution, CRS, latitude convention,
  vertical datum, units), statistics (min/max/mean/relief/NoData fraction), suitability
  (REGIONAL_OVERVIEW_ONLY > 100 m cells, SITE_RECONNAISSANCE, DETAILED_STUDY ≤ 2 m), elevations as
  zlib+base64 float32 LE (NaN = NoData). `Cache-Control: private, max-age=300`.

## Frontend

- `services/localTerrainService.ts`: request with AbortController (old requests cancelled when the
  point/radius changes), in-memory cache (24 patches; network errors not cached), decoding,
  one automatic retry with a 24-native-cell radius when the DEM is too coarse (shown as
  "enlarged from 20 km"), mesh builder (x east, z south, triangles touching NoData skipped).
- `components/terrain/LocalTerrain3D.tsx` in the point panel: compact preview opens automatically
  when a point is selected; Expand (Esc closes); drag rotate, right-drag pan, wheel zoom; RESET,
  NORTH (north up), live north arrow; legend (colour = elevation, min/max with units); dataset,
  native resolution, grid, radius, relief, datum, NoData %, suitability, source; radius selector;
  vertical exaggeration 0.5–20×, default 1.0×, labelled "visual only".
- No DEM: "3D TERRAIN UNAVAILABLE" + reason; nothing is drawn instead.

## Bugs found and fixed (pre-existing, v0.2)

1. **MOLA MEGDR seam at lon 0°**: the file is a projected equirectangular raster centred on 180°E
   spanning the whole circumference. Lon 0° lies exactly on its right edge and was reported as
   "no validated DEM covers this point" (e.g. the point panel at 0°N 0°E). Coverage check, point
   lookup and grid sampling now wrap x by the raster width when the raster spans the full
   circumference (`dem_reader.x_wrap_period`).
2. **Grids crossing the seam read wrong cells**: `raster_render.sample_grid` read one window from
   the min to the max column; across the seam that is the whole raster width, which was then
   decimated ~18× → wrong values (also affected `/terrain/render` near lon 0°). Each contiguous
   column segment is now read separately. Regression test: patch across the seam contains both the
   first and the last DEM column, 0 % NoData.

## Verified in the browser

- Mars near Jezero: MOLA patch 23×23 at native 15 km, radius enlarged 20 km → 178 km (stated),
  relief 3 571 m, "Regional overview only — far too coarse for site or traverse planning".
- Moon (no DEM registered): "3D TERRAIN UNAVAILABLE".
- The expanded view was not screenshotted (the pane was in use at the time).

## Limits / status

- Only MOLA MEGDR 4 px/deg is registered → every Mars patch is REGIONAL_OVERVIEW_ONLY.
  Local-scale terrain needs a HiRISE/CTX DTM imported via the Data Manager (REQUIRES_USER_CONFIGURATION).
- Moon / Mercury / Earth: NO_DATA_COVERAGE until a DEM is registered.
- "LOCAL 3D TERRAIN" is reached by clicking a point (not a separate top-level mode yet).

## Tests

Backend `tests/test_terrain_patch_v03.py` (11): values only from the DEM, orientation, never finer
than the DEM, NoData reported not filled, partly outside → NoData edges, too coarse → min radius, no
DEM → 404, validation, seam coverage at lon 0, seam-crossing patch, bbox/pole helpers.
Frontend `services/localTerrainService.test.ts` (8). Backend 151/151, frontend 138/138.
