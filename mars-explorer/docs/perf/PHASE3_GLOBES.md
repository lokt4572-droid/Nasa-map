# Phase 3 — Three.js planet globes (2026-11-14)

Raw notes for `docs/PLANETARY_GLOBE_REPORT.md` (Phase 7).

## Status

| Body | Status | Texture |
|---|---|---|
| Mars | IMPLEMENTED, TESTED (browser) | Viking MDIM 2.1 colorized, Trek WMTS, 2048×1024 |
| Moon | IMPLEMENTED, TESTED (browser) | LRO WAC v2, Trek WMTS, 2048×1024 |
| Mercury | IMPLEMENTED, TESTED (browser) | MESSENGER MDIS enhanced colour 665 m, Trek WMTS, 2048×1024 |
| Earth | IMPLEMENTED, TESTED (browser) | Blue Marble NG, GIBS WMS EPSG:4326, 2048×1024 (Cesium 3D terrain kept separate) |
| Venus | NOT_IMPLEMENTED | no verified global texture with CORS; preview unchanged |
| Pre-built textures in `data/planet-textures/<planet>/` + backend endpoint (offline globe) | NOT_IMPLEMENTED | textures are built at runtime from the services and cached by the browser's HTTP cache |

## How it works

- `config/planetTextures.ts`: per-body source, instrument, projection, latitude convention, native
  and on-globe resolution, date, coverage, attribution, notes (shown in "TEXTURE SOURCE").
- `services/planetTextureService.ts`:
  - real ellipsoid from registry radii (Mars a = 3 396 190 m, b = 3 376 200 m; Earth WGS 84),
    vertices placed by **geodetic** latitude for ellipsoid CRSs (Mars 2000, WGS 84) and on the
    sphere for Moon/Mercury; UVs linear in lon/lat = exact equirectangular layout (no Web Mercator);
  - picking inverts the same formula (round-trip error < 1e-9°);
  - Trek mosaic: tile grid, origin, resolution and matrix size from GetCapabilities; level 1
    (1024×512) shown first, then level 2 (2048×1024); tiles clamped to the matrix size;
    missing tiles stay blank and are counted in the UI ("n/m tiles missing — not filled in").
- `components/planetary/PlanetGlobe3D.tsx`: drag to rotate (slower near the surface), wheel to zoom,
  30° graticule, illustrative lighting (light fixed to the camera — labelled as not the real Sun),
  auto-rotate, reset view, click → coordinates + selects the point (Mars/Moon/Mercury) and
  "Open in 2D map" (centres the 2D map there); hover → status-bar cursor; WebGL-unavailable message;
  everything disposed on unmount.
- `components/layout/ViewModeSwitch.tsx`: 2D MAP / 3D GLOBE (+ 3D TERRAIN on Earth = Cesium);
  modes a body lacks are hidden; globe mode is kept when switching to another body that has one.

## Measured (in-app browser, cold cache)

Full 2048×1024 texture: Moon 8.9 s, Mercury 7.6 s, Earth 6.1 s (Mars cold run not timed; warm
0.5 s, coarse level after 0.25 s). Picking at the canvas centre of the default view returned
0.000° N 0.000° E.

## Findings

- **Bug found and fixed during verification**: OpenLayers' tile range for the exact −180..180 extent
  includes one column and one row past the edge (45 instead of 32 tiles at level 2); those 13
  requests 404'd and were reported as missing. The range is now shrunk by a quarter pixel and
  clamped to the full tile range from GetCapabilities → 32/32 tiles, 0 missing.
- **NASA Trek 404 responses carry no `Access-Control-Allow-Origin` header**, so a browser sees a
  missing Trek tile as a CORS/network failure, not as HTTP 404. The map's diagnostics therefore
  report such tiles as `CORS_OR_NETWORK`; this is why tiles outside the declared bbox are never
  requested (Phase 1).
- Mars latitude convention: NASA Trek does not state planetocentric vs planetographic. Rows are
  placed with geodetic latitude of the declared Mars 2000 ellipsoid; the maximum difference to
  planetocentric is ≈ 0.34° at 45° (unit-tested), documented in the texture notes.

## Tests

`frontend/src/services/planetTextureService.test.ts` (11 tests): round-trips for both conventions,
real flattening and axes, Mars geodetic vs planetocentric difference, mesh UVs/seam/normals,
graticule, Trek level-2 tile placement, non-standard origin, catalog completeness (no Web
Mercator, attribution/date/coverage present, Venus none), view-mode persistence across bodies.
`buildPlanetTexture` network/canvas path is verified in the browser only (jsdom has no canvas).
Frontend 130/130.
