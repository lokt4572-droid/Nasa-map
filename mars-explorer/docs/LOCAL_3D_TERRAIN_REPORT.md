# MARS EXPLORER v0.3 — Click-to-explore local 3D terrain report

Date: 2026-11-14 · Commit of the feature: `62a0021` · Notes: `docs/perf/PHASE4_LOCAL_TERRAIN.md`

## 1. Status

| Item | Status |
|---|---|
| `GET /api/v1/terrain/patch/` (validated parameters, real metadata, binary payload) | IMPLEMENTED, TESTED |
| `LocalTerrain3D` viewer (compact preview + expand) | IMPLEMENTED, TESTED (browser, compact view) |
| "3D TERRAIN UNAVAILABLE" without a DEM (no fake terrain) | IMPLEMENTED, TESTED |
| Mars local-scale terrain (≤ 100 m cells) | REQUIRES_USER_CONFIGURATION — only MOLA MEGDR 4 px/deg (≈ 14.8 km cells) is registered; a HiRISE/CTX DTM must be imported via the Data Manager |
| Moon / Mercury / Earth terrain | NO_DATA_COVERAGE (no DEM registered) |
| Expanded view screenshot | not captured (pane in use / hidden during verification) |

## 2. Endpoint

`GET /api/v1/terrain/patch/?planet&longitude|lon&latitude|lat&radius_m&max_dimension[&dataset&crs&lat_convention]`

- radius 100 m – 500 km (default 20 km), max_dimension 16–512 (default 256); invalid → 400.
- Finest validated DEM covering the point is used; none → 404 `DEM_NOT_AVAILABLE`.
- **Never finer than the DEM**: grid side = min(max_dimension, native cells across the patch); nearest
  DEM cell, no interpolation. A unit test asserts every returned value exists in the DEM.
- < 4 native cells across → 422 `DEM_TOO_COARSE_FOR_PATCH` with `native_resolution_m` and
  `min_radius_m`; pole crossing → 422 `PATCH_CROSSES_POLE`.
- NoData stays NaN, reported as `nodata_fraction`; never filled.
- Payload: zlib + base64 float32 little-endian, row-major north→south / west→east; metadata: centre,
  bbox, grid (size, cell size in m, native cells across, resampling), dataset (id, name, instrument,
  product, source, licence, native resolution, CRS, latitude convention, vertical datum, units),
  statistics (min/max/mean/relief/NoData), suitability (REGIONAL_OVERVIEW_ONLY > 100 m,
  SITE_RECONNAISSANCE, DETAILED_STUDY ≤ 2 m), notes. `Cache-Control: private, max-age=300`.

## 3. Viewer

- Opens automatically (compact) in the point panel when a point is selected; **Expand** for a large
  view (Esc closes). Old requests are cancelled when the point or radius changes; patches are cached
  (24, network errors not cached).
- Three.js BufferGeometry from the real grid: x east, z south, y elevation; triangles touching a NoData
  cell are skipped (holes stay holes).
- Controls: rotate / zoom / pan, RESET, NORTH (north up), live north arrow, radius selector,
  **vertical exaggeration 0.5–20×, default 1.0×, labelled "visual only"**; legend "colour = elevation"
  with true min/max and units; dataset, native resolution, grid, radius, relief, datum, NoData %, use
  class, source.
- If the DEM is too coarse for the requested radius, the viewer retries once with 24 native cells across
  and says so ("enlarged from 20 km: the DEM is too coarse for a smaller patch").

## 4. Bugs found and fixed (pre-existing since v0.2)

1. **MEGDR seam at lon 0°**: the MOLA file is a projected equirectangular raster centred on 180° E
   spanning the full circumference; lon 0° lies exactly on its right edge and was reported as outside
   the DEM ("no validated DEM covers this point" at 0° N 0° E). Coverage, point lookup and grid sampling
   now wrap x by the raster width (`dem_reader.x_wrap_period`).
2. **Grids crossing the seam read wrong cells**: one window from min to max column spanned the whole
   raster and was decimated (~18×). Each contiguous column segment is now read separately. Also fixes
   `/terrain/render` near 0°.

## 5. Verified in the browser

- Mars near Jezero: MOLA patch 23 × 23 at native 15 km, radius auto-enlarged 20 → 178 km (stated),
  relief 3 571 m, "Regional overview only — far too coarse for site or traverse planning".
- Moon: "3D TERRAIN UNAVAILABLE — No validated DEM covering this point is loaded"; nothing drawn.
- Patch across lon 0° on Mars: 40 × 40, 0 % NoData (after the seam fix).

Console note: each new Mars point logs one HTTP 422 (the first request at 20 km is too coarse for MOLA;
the viewer then retries). This is expected API behaviour, not an error.

## 6. Tests

Backend `tests/test_terrain_patch_v03.py` (11) and frontend `services/localTerrainService.test.ts` (8):
values only from the DEM, orientation, never finer than the DEM, NoData reported and not filled, partly
outside → NoData edges, too coarse → minimum radius, no DEM → 404, validation, seam coverage and seam
crossing, pole refusal, decoding, NoData triangles skipped, exaggeration affects only heights, retry
with a larger radius, network errors not cached.
