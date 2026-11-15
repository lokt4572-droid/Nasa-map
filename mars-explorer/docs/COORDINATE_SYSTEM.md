# Coordinate systems

## Map (frontend)

* View projection: the CRS **exactly as declared by NASA Trek**,
  `urn:ogc:def:crs:EPSG::104905`, registered in proj4/OpenLayers with
  `+proj=longlat +a=3396190 +rf=169.894447223612 +no_defs` (`frontend/src/config/marsProjection.ts`).
* Units: decimal degrees. Extent −180…180, −90…90. Longitude east-positive.
* Every picked point is stored and sent with `crs = urn:ogc:def:crs:EPSG::104905` and
  `latitude_convention = AS_DECLARED_BY_SOURCE`.

### Why the "EPSG::104905" identifier needs care

* PROJ has **no** `EPSG:104905` (verified: `CRSError … crs not found`). The code exists as
  `ESRI:104905` = `GCS_Mars_2000`: `+proj=longlat +a=3396190 +rf=169.894447223612`.
* We do **not** rewrite the namespace silently. The interpretation is an explicit,
  documented alias in `backend/services/mars_coordinates.py` (`CRS_ALIASES`), and every
  terrain API response reports it in `query.crs_resolution`.
* Rationale for the alias: same numeric code and name; the Trek tile matrices and
  bounding boxes are decimal degrees with TopLeftCorner (−180, 90), consistent with a
  geographic Mars 2000 CRS.

### Latitude type is not stated by Trek

ESRI:104905 is an ellipsoid (a = 3 396 190 m, b = 3 376 200 m), which formally implies
planetographic latitude. The GetCapabilities documents, however, do not state whether
the underlying mosaics are planetocentric or planetographic. The UI therefore labels map
latitudes "as declared by source", and the backend reports `NOT_VERIFIED` when it uses
such a latitude against a DEM. At 45° the two latitude types differ by 0.338°
(≈ 20 km on Mars), so this matters.

## Backend

* Point fields are explicit: `lon_east_deg` (stored −180…180, east-positive; −180…360
  accepted on input), `lat_deg`, `crs`, `latitude_convention`.
* CRS resolution: `resolve_crs()` accepts PROJ-known identifiers plus the documented
  alias above and rejects anything that is not a Mars CRS (e.g. EPSG:4326 → 400).
* Latitude conversion: `adapt_latitude()` converts planetocentric ↔ planetographic
  analytically, `tan φg = (a/b)² tan φc`.

### Verified PROJ behaviour (important)

PROJ applies a **null ("ballpark") transformation** between the Mars sphere
(ESRI:104971) and the Mars 2000 ellipsoid (ESRI:104905): 45.0° stays 45.0°. It does not
convert planetocentric to planetographic latitude. The backend therefore converts
latitude types explicitly when both conventions are known, and flags the result as
`NOT_VERIFIED` otherwise. Regression test: `tests/test_coordinates.py`.

## DEM cell size and slope

For geographic DEMs the cell size in metres is computed from the DEM's own ellipsoid at
the sample latitude: `dx = Δλ·N(φ)·cos φ`, `dy = Δφ·M(φ)` (sphere: N = M = R). Slope and
aspect use Horn's 3×3 method with those anisotropic cell sizes.

## Scale bar

OpenLayers' ScaleLine assumes an Earth sphere for degree-based projections, so the app
computes the scale itself on the Mars 2000 ellipsoid (east–west at the view centre latitude).

## Control points used in tests

| Check | Expected |
|---|---|
| b from a and rf | 3 376 200 m |
| φc = 45° → φg | atan((a/b)²) = 45.3382° |
| Quarter of the equator (geodesic) | a·π/2 = 5 334 722.8 m |
| Equator ground resolution, 0.703125 °/px | 0.703125·π/180·a |
| Trek level-0 resolution | 360°/512 px = 0.703125 °/px (±2×10⁻⁶ rel.) |
| 77.45° E | 282.55° W |

---

## v0.2 — other bodies (see also PLANET_REGISTRY.md)

| Body | Map CRS (as declared by the service) | Interpreted with | Radius (m) | Latitude | Longitude |
|---|---|---|---|---|---|
| Mars | `urn:ogc:def:crs:EPSG::104905` | ESRI:104905 ellipsoid | 3 396 190 / 3 376 200 | as declared (map); MEGDR planetocentric | east, −180…180 (map) |
| Moon | `urn:ogc:def:crs:EPSG::104903` | ESRI:104903 sphere | 1 737 400 | planetocentric | east, −180…180 |
| Mercury | `urn:ogc:def:crs:IAU2000::19900` | IAU_2015:19900 sphere | 2 440 530 (conflict: ESRI:104974 = 2 439 400) | planetocentric | east, −180…180 (map); USGS DEM 0…360 |
| Venus | — (no map service) | IAU_2015:29900 sphere | 6 051 800 | planetocentric | GTDR 0…360 |
| Earth | `EPSG:3857` (map), `EPSG:4326` (points) | WGS 84 | 6 378 137 / 6 356 752.314 | geodetic | east, −180…180 |

Rules enforced in code (backend `resolve_crs(identifier, planet=…)`, frontend per-body projections):
* a CRS is accepted only if its ellipsoid belongs to the selected body (semi-major-axis ranges in
  `services/planet_registry.py`): WGS 84 is rejected for Mars, a Mars CRS is rejected for the Moon;
* a WMTS layer is only overlaid when its TileMatrixSet CRS equals its body's map CRS (`UNSUPPORTED_CRS` otherwise);
* DEMs carry a `planet`; terrain queries only consider DEMs of the queried body;
* scale bars use the body's own reference figure (Moon 10.7 km/px vs Mercury 15.0 km/px at the same zoom, checked);
* longitudes are normalised to east-positive −180…180 on input; west-positive values are only converted by explicit functions.

### Earth specifics
* Points picked on the Web-Mercator map are converted to geographic WGS 84 (EPSG:4326) before any API call.
* Copernicus DEM heights refer to EGM2008 (EPSG:3855), GEBCO to mean sea level, Cesium terrain heights shown in the
  3D globe are Cesium `Cartographic` heights (relative to the WGS 84 ellipsoid).
* Map distance measurement in 2D uses `ol/sphere` (sphere R = 6 371 008.8 m, error ≲ 0.5 %); in 3D, Cesium
  `EllipsoidGeodesic` on WGS 84.
