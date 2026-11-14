# MARS EXPLORER v0.3 — Planetary 3D globe report

Date: 2026-11-14 · Branch `feature/v0.3-performance-globes` · Commit of the feature: `bdff704`
Detailed working notes: `docs/perf/PHASE3_GLOBES.md`.

## 1. Status per body

| Body | Status | Texture source (verified 2026-11-14) | Globe texture |
|---|---|---|---|
| Mars | IMPLEMENTED, TESTED | NASA Mars Trek WMTS `Mars_Viking_MDIM21_ClrMosaic_global_232m` (EPSG::104905, JPEG, 10 levels) | 2048 × 1024, level 1 first |
| Moon | IMPLEMENTED, TESTED | NASA Moon Trek WMTS `LRO_WAC_Mosaic_Global_303ppd_v02` (EPSG::104903) | 2048 × 1024 |
| Mercury | IMPLEMENTED, TESTED | NASA Mercury Trek WMTS `Mercury_MESSENGER_MDIS_Basemap_EnhancedColor_Mosaic_Global_665m` (IAU2000::19900, JPEG — `.png` tiles 404) | 2048 × 1024 |
| Earth | IMPLEMENTED, TESTED | NASA GIBS WMS EPSG:4326 `BlueMarble_NextGeneration` (CORS `*`) | 2048 × 1024 |
| Venus | NOT_IMPLEMENTED | no verified global texture service with CORS (NASA Trek has no Venus body) | Venus preview unchanged |
| Pre-built textures in `data/planet-textures/<planet>/` + backend endpoint | NOT_IMPLEMENTED | textures are built at runtime; browser HTTP cache only | offline globe not available |

Cesium remains the separate Earth "3D TERRAIN" mode (terrain relief needs a Cesium ion token:
REQUIRES_USER_CONFIGURATION, unchanged from v0.2).

## 2. Geometry and projection

- **Real ellipsoid** from the registry radii (Mars 3 396 190 / 3 376 200 m, WGS 84 for Earth,
  spheres for Moon 1 737 400 m and Mercury 2 440 530 m) — not a scaled or stretched sphere.
- All textures are **equirectangular** (lon −180..180, lat −90..90). Vertices are placed at
  (lon, lat) using the texture's latitude convention; UVs are linear in lon/lat, i.e. exactly the
  image layout. **No Web Mercator anywhere** (unit test checks the catalogue).
- Latitude: geodetic on ellipsoid CRSs (Mars 2000, WGS 84), spherical for Moon/Mercury. NASA Trek
  does not state whether Mars latitudes are planetocentric or planetographic; the maximum difference
  on Mars is ≈ 0.34° at 45° (unit-tested) and is stated in the texture notes shown to the user.
- Axes: +X = (0°, 0°), +Y = north pole, −Z = 90° E, so east is to the right seen from outside.
- Picking inverts the same formulas (round-trip error < 1e-9° in tests); a click at the centre of the
  default view returned 0.000° N 0.000° E in the browser.

## 3. Textures

- Trek tile grid, origin, resolution and matrix size are read from GetCapabilities (same parser as the
  2D map). Coarse level (1024 × 512) is shown first, then the 2048 × 1024 level.
- Missing tiles are left transparent and counted on screen ("n/m tiles missing — not filled in").
- Bug fixed during verification: the tile range for the exact −180..180 extent overshot by one column
  and one row (45 instead of 32 tiles at level 2, 13 spurious 404s). Range is now clamped to the
  matrix size from GetCapabilities → 32/32.
- Metadata panel ("TEXTURE SOURCE"): dataset, instrument, projection, native and on-globe resolution,
  date, coverage, attribution link, notes (colorized Viking, enhanced-colour MDIS, cloud-free Blue
  Marble composite).

## 4. Interaction

Drag to rotate (slower close to the surface), wheel zoom, 30° graticule, illustrative lighting
(light fixed to the camera — labelled as not the real Sun position), auto-rotate, reset view, hover →
status-bar cursor, click → coordinates; on Mars/Moon/Mercury the click selects the point (point panel,
local 3D terrain) and offers "Open in 2D map". WebGL unavailable → explicit message. All GPU resources
are disposed on unmount.

## 5. Measurements (in-app browser, cold HTTP cache)

| Body | Full 2048 × 1024 texture |
|---|---|
| Moon | 8.9 s |
| Mercury | 7.6 s |
| Earth | 6.1 s |
| Mars | coarse level after 0.25 s, full after 0.5 s (warm cache; cold not timed) |

The time is dominated by NASA Trek tile latency (≈ 2–3 s per tile, 6 parallel connections).

## 6. Tests

`frontend/src/services/planetTextureService.test.ts` (11 tests): lon/lat round trips (ellipsoid and
sphere), real flattening and axis orientation, Mars geodetic vs planetocentric difference, mesh UVs /
seam / normals, graticule, Trek level-2 tile placement and a non-standard grid origin, catalogue
completeness (no Web Mercator; attribution/date/coverage present; Venus none), view mode across bodies.
The network/canvas texture builder is verified in the browser only (jsdom has no canvas).
