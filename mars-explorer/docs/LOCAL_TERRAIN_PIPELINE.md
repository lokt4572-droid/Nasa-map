# Local terrain pipeline (v0.4)

From a click on the map to a 3D model built from real elevation values.

```
click (lon, lat, map CRS)
  -> coverage: registered DEMs + provider catalogue (USGS STAC / Copernicus tile list)
  -> choose: finest DEM first; skip unreadable products and products with a data gap at the point
  -> register (remote): open the COG header, validate CRS body, units, values (no bulk download)
  -> read: one bounded window (nearest DEM cell, never finer than the DEM)
  -> quality: NoData share, provider quality class, accuracy NOT_DOCUMENTED unless stated
  -> encode: float32 little-endian, zlib + base64, NaN = NoData; metadata alongside
  -> mesh (browser): local east/north metric frame, triangles skipped at NoData, normals, UVs
  -> display: colour = elevation, legend in metres, exaggeration 1/1.5/2/5x (visual only)
```

## API

`GET /api/v1/terrain/patch/?planet=&longitude=&latitude=[&radius_m][&max_dimension][&source=auto|local][&dataset][&product=collection/id]`

Response (all values from the dataset or the computation): `dataset_id, source, crs,
vertical_datum, resolution_m, sample_spacing_m, width, height, units, nodata_percentage,
coverage_status (AVAILABLE | PARTIAL), processing_status (READY), center, bbox, grid, dataset{…,
access, quality_status, effective_accuracy}, statistics, elevation (encoded), selection{mode,
reason, skipped_products[]}, alternatives[]`.

- No radius given: the radius that shows the DEM at native resolution (one mesh cell per DEM cell).
- 404 `DEM_NOT_AVAILABLE`: no DEM covers the point ("LOCAL 3D TERRAIN UNAVAILABLE").
- 422 `DEM_NO_VALID_CELLS` with `coverage_status: DATA_GAP`: every covering DEM has a gap there.
- 422 `DEM_TOO_COARSE_FOR_PATCH`: the radius covers fewer than 4 DEM cells.

Other terrain endpoints: `coverage/` (`remote=1` adds catalogue products), `profile/` (geodesic,
nearest cell, null for NoData), `sample/`, `slope/`, `roughness/`, `render/` (PNG; `range=` fixes the
elevation stretch).

## Rules

- Values are never invented: NoData stays NaN, triangles touching it are not drawn, and no lower
  resolution DEM is blended in.
- One DEM per patch: datums are never mixed.
- Remote reads only from allow-listed HTTPS hosts; decoded windows cached in memory (bounded).
- The 3D mesh is visual geometry. Elevation analysis and routing read the DEM grid on the backend.

## Browser workspace

Point panel → **OPEN LOCAL 3D** opens the 3D view beside the map (**2D | 3D**); the patch footprint
is outlined on the 2D map and framed outside the 3D panel. Controls: radius (native or 250 m–500 km),
DEM selector, exaggeration, reset view, north reference, legend, source/resolution/datum/accuracy/
access/NoData details. Mesh size follows the device (`terrainMeshService.ts`).
