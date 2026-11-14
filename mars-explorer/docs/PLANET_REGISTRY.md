# Planet registry

One registry, two mirrors: `backend/services/planet_registry.py` and `frontend/src/config/planetRegistry.ts`.
API: `GET /api/v1/planets/`, `/planets/{id}/`, `/planets/{id}/layers/`.

## Fields per body
`id, name, category, status, radius_equatorial_m, radius_polar_m, reference_crs (+ note), latitude_type,
longitude_direction, longitude_range, units, vertical_datum, projections, map_crs, semi_major_range_m,
coverage_note, browser_geolocation_allowed, conflicts` (frontend: `availableViews`, `layers`, `datasets`).

| Body | Status | Map | DEM in the app | Notes |
|---|---|---|---|---|
| MARS (default) | PRIMARY | 4 Trek layers | MOLA MEGDR imported (real); HiRISE DTM: user data | missions, hazards, A* routes |
| EARTH | FULL | OSM + 14 GIBS layers, 3D globe | Copernicus / GEBCO: user data | only body with browser geolocation |
| MOON | SCIENTIFIC_VIEWER | LROC WAC mosaic, LOLA hillshade | GLD100 / LOLA: user data | GLD100 79°S–79°N only |
| MERCURY | SCIENTIFIC_VIEWER | MDIS mosaic, USGS DEM hillshade | USGS 665 m DEM: user data | radius conflict documented |
| VENUS | EXPERIMENTAL | none (no Trek service) | GTDR: user data, radius values | preview screen with warnings |

Bodies NOT included: Pluto and others — no suitable products/parameters were integrated (spec §10.1).

## Radii (from PROJ, pyproj 3.8, verified by tests)
Mars 3 396 190 / 3 376 200 (ESRI:104905) · Moon 1 737 400 (ESRI:104903) · Mercury 2 440 530 (IAU_2015:19900) ·
Venus 6 051 800 (IAU_2015:29900) · Earth 6 378 137 / 6 356 752.314 (EPSG:4326).

## Documented conflicts
* Mercury: PROJ IAU_2015:19900 = 2 440 530 m; ESRI:104974 "Mercury_2015" = 2 439 400 m; Trek declares the IAU 2000
  namespace. DEM CRS checks accept both radii; each product's own label value is used for that product.
* Mars: MEGDR products use a 3 396 000 m sphere; the Trek map uses the 3 396 190 m Mars 2000 ellipsoid.
* Trek identifiers `EPSG::104905` / `EPSG::104903` do not exist in EPSG; they are resolved through explicit, reported aliases.

## Adding a body
1. Add a `PlanetConfig` in both registry files (radii from PROJ or the product label, never guessed).
2. Add its map CRS to `frontend/src/config/planetProjections.ts` and an alias in `services/mars_coordinates.py` if the
   service uses a non-PROJ identifier.
3. Add verified layers to `PLANET_LAYERS` (backend) and `frontend/src/config/mapLayers.ts`.
4. Add catalog entries in `backend/apps/datasets/catalog.py`.
5. Extend `tests/test_planets_v02.py` and `src/planets.test.ts`.
