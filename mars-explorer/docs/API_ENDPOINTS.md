# API endpoints — `/api/v1/`

Base URL (local): `http://127.0.0.1:8000/api/v1`. JSON only. No authentication in this
first version (local single-user tool — add auth before exposing it on a network).

## Error format

Every error has the same envelope:

```json
{"error": {"code": "DEM_NOT_AVAILABLE", "message": "…", "details": {}}}
```

| HTTP | code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | invalid input; `details` holds field errors |
| 404 | `NOT_FOUND` | unknown object id |
| 404 | `DEM_NOT_AVAILABLE` | no validated DEM covers the point (`details.elevation = "DATA NOT AVAILABLE"`) |
| 405 | `METHOD_NOT_ALLOWED` | e.g. PUT (use PATCH) |
| 422 | `DATASET_INVALID`, `RASTER_UNREADABLE`, `TERRAIN_ANALYSIS_ERROR` | bad raster / not analysable |
| 500 | `DEM_READ_ERROR`, `INTERNAL_ERROR` | read failure |
| 501 | `NOT_IMPLEMENTED` | route planning |
| 503 | `DEM_BACKEND_UNAVAILABLE` | rasterio/GDAL not installed |

## Coordinates

Point fields: `lon_east_deg` (−180…360 accepted, stored −180…180, east-positive),
`lat_deg` (−90…90), `crs` (default `urn:ogc:def:crs:EPSG::104905`; must resolve to a Mars
CRS), `latitude_convention` (`PLANETOCENTRIC` | `PLANETOGRAPHIC` |
`AS_DECLARED_BY_SOURCE` (default) | `UNKNOWN`). See [COORDINATE_SYSTEM.md](COORDINATE_SYSTEM.md).

---

## Health

`GET /health/` → 200

```json
{"status": "ok", "service": "mars-explorer-backend", "version": "0.1.0", "time_utc": "…",
 "database": "ok", "data_dir": {"path": "…\\data\\mars", "exists": true},
 "raster_backend": {"available": true, "backend": "rasterio 1.5.2", "gdal_version": "3.12.2",
                    "planetary_drivers": ["COG","GTiff","ISIS2","ISIS3","PDS","PDS4","VICAR"], "error": null}}
```
503 with `status: "degraded"` if the database is not reachable.

## Datasets

| Method | Path | Description |
|---|---|---|
| GET | `/datasets/` | list (paginated `?limit=&offset=`); re-checks that files exist (→ `MISSING`) |
| GET | `/datasets/{id}/` | one dataset |
| GET | `/datasets/{id}/metadata/` | CRS WKT, full GDAL metadata, validation messages, checksum |
| POST | `/datasets/register/` | validate + register a file already inside `MARS_DATA_DIR` |

`Dataset` fields: `id, name, source, instrument, product_id, data_type, file_path,
file_exists, driver, width, height, resolution_meters, pixel_size_x, pixel_size_y,
crs_name, longitude_convention, latitude_convention, vertical_datum, units,
nodata_value, coverage_bbox, observation_date, download_date, file_size, checksum,
is_validated, status (AVAILABLE|DOWNLOADING|PROCESSING|VALID|INVALID|MISSING),
validation_messages, created_at, updated_at`.

`POST /datasets/register/` body:

```json
{"file_path": "raw/mola/<label>.xml", "name": "mola-megdr", "source": "", "instrument": "",
 "product_id": "", "vertical_datum": "", "units": ""}
```
201 `{"dataset": {…}, "warnings": […]}`; 400 path outside data dir (`PATH_OUTSIDE_DATA_DIR`);
422 `DATASET_INVALID` with `details.errors`. Large files: prefer the CLI `import_dem`.

## Missions & waypoints

| Method | Path |
|---|---|
| GET, POST | `/missions/` |
| GET, PATCH, DELETE | `/missions/{id}/` |
| GET, POST | `/waypoints/` (`?mission=<id>` filter) |
| GET, PATCH, DELETE | `/waypoints/{id}/` |

Mission: `name` (required, non-blank), `description`, `status`
(PLANNED|ACTIVE|COMPLETED|ABORTED), `demo_mode` (default true), read-only `waypoints[]`,
`hazard_count`. Waypoint: `mission`, `name`, `kind` (BASE|CHECKPOINT|LANDING_SITE|POI),
`order`, `notes` + point fields. PUT is not allowed (405); use PATCH.

## Hazards

| Method | Path |
|---|---|
| GET, POST | `/hazards/` (filters `?mission=&hazard_type=&severity=&verification=`) |
| GET, PATCH, DELETE | `/hazards/{id}/` |

Fields: `title` (required), `hazard_type` (CRATER|STEEP_SLOPE|CLIFF|BOULDER_FIELD|
SOFT_REGOLITH|DUNE|DUST|OTHER), `severity` (UNKNOWN|LOW|MEDIUM|HIGH), `source`
(FIELD_OBSERVATION|IMAGERY_INTERPRETATION|DEM_DERIVED|OTHER), `verification`
(UNVERIFIED default|CONFIRMED|REJECTED), `radius_m` (0…1e6, optional), `description`,
`reference_layer`, `reported_by`, `observed_at`, `mission` (nullable) + point fields.

## Terrain

Query parameters for all three: `lon`, `lat`, optional `crs`, optional
`lat_convention` (PLANETOCENTRIC | PLANETOGRAPHIC). Without `lat_convention` the
latitude is used unchanged and `latitude_handling.status = NOT_VERIFIED` with a warning.

`GET /terrain/coverage/` → 200

```json
{"query": {…, "crs_resolution": {"resolved_as": "ESRI:104905", "note": "…"}},
 "terrain_analysis_status": "AVAILABLE | NO DATA | ERROR",
 "raster_backend": {…}, "datasets": [{"id": 1, "name": "…", "resolution_meters": …, …}]}
```

`GET /terrain/sample/` → 200

```json
{"status": "AVAILABLE | NODATA", "elevation_m": 1037.0, "elevation_display": null,
 "units": "m", "vertical_datum": "…", "method": "nearest DEM cell, no interpolation",
 "pixel": {"row": 0, "col": 0, "x_dataset": 0, "y_dataset": 0},
 "latitude_handling": {"status": "NONE | CONVERTED_… | NOT_VERIFIED", "lat_query_deg": …, "lat_used_deg": …, "warning": null},
 "dataset": {…}, "query": {…}}
```
NODATA cell → `elevation_m: null`, `elevation_display: "DATA NOT AVAILABLE"`.
404 `DEM_NOT_AVAILABLE` when no DEM covers the point; 503 when GDAL is missing.
(1037.0 is a value from the synthetic test raster in `backend/tests`, not a Mars measurement.)

`GET /terrain/slope/` → 200: `slope_deg`, `aspect_deg` (clockwise from north, downslope
direction; null on flat ground), `terrain_ruggedness_index_m`, `elevation_std_m`,
`nodata_fraction`, `cell_size_m {dx, dy, method}`, `method`, `disclaimer`, `dataset`.
`status: NODATA` (metrics null) if any of the 3×3 cells is nodata.

## Routing

`POST /routes/plan/` body `{"start": {point}, "end": {point}, "max_slope_deg"?, "mission"?}`
→ input validated (400 on error), then **501 `NOT_IMPLEMENTED`**. No route is ever
returned or called safe.
