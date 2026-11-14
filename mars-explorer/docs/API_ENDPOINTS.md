# API endpoints — `/api/v1/` (v0.2)

Base URL (local): `http://127.0.0.1:8000/api/v1`. JSON unless stated. No authentication
(local single-user tool — add auth before exposing it on a network).

## Error format

```json
{"error": {"code": "DEM_NOT_AVAILABLE", "message": "…", "details": {}}}
```

| HTTP | code | When |
|---|---|---|
| 400 | `VALIDATION_ERROR`, `UNSUPPORTED_FILE_TYPE`, `PATH_OUTSIDE_DATA_DIR` | invalid input |
| 404 | `NOT_FOUND`, `DEM_NOT_AVAILABLE` | unknown object / no DEM covers the point |
| 409 | `CONFLICT` | stale `version` on PATCH (details.server = server copy) |
| 413 | `FILE_TOO_LARGE` | register via API above `MAX_REGISTER_FILE_BYTES` |
| 422 | `DATASET_INVALID`, `INSUFFICIENT_TERRAIN_DATA`, `NO_PASSABLE_ROUTE`, `TERRAIN_ANALYSIS_ERROR` | data cannot support the request |
| 429 | `RATE_LIMITED` | geocoding faster than 1 request/s |
| 502 | `PROVIDER_ERROR`, `PROVIDER_HTTP_ERROR`, `PROVIDER_BAD_RESPONSE` | external provider failed |
| 503 | `DEM_BACKEND_UNAVAILABLE` | GDAL/rasterio not installed |
| 504 | `PROVIDER_TIMEOUT` | external provider timeout |

## Coordinates

Point fields: `lon_east_deg` (−180…360 accepted, stored −180…180, east-positive), `lat_deg`,
`crs`, `latitude_convention` (`PLANETOCENTRIC` | `PLANETOGRAPHIC` | `AS_DECLARED_BY_SOURCE` | `UNKNOWN`),
and for queries `planet` (`MARS` default, `EARTH`, `MOON`, `MERCURY`, `VENUS`). A CRS is only
accepted for its own body (e.g. `EPSG:4326` is rejected for Mars). See COORDINATE_SYSTEM.md.

---

## Health

| Method | Path | Description |
|---|---|---|
| GET | `/health/` | backend, database, data dir, GDAL status |
| GET | `/health/sources/` | probes NASA Trek, NASA GIBS, Open-Meteo, NASA POWER (8 s timeout, cached 10 min, `?refresh=1`). Nominatim is `NOT_PROBED` by policy |

## Planets

| Method | Path | Description |
|---|---|---|
| GET | `/planets/` | all bodies with radii, CRS, conventions, datum, projections, conflicts |
| GET | `/planets/{id}/` | one body + its map layers |
| GET | `/planets/{id}/layers/` | verified Trek layers of the body (empty for Venus/Earth) |

## Datasets

| Method | Path | Description |
|---|---|---|
| GET | `/datasets/` | local datasets (paginated); re-checks files (→ `MISSING`) |
| GET | `/datasets/{id}/` | one dataset |
| GET | `/datasets/{id}/metadata/` | CRS WKT, GDAL metadata, statistics, control points, label statements, import steps |
| GET | `/datasets/catalog/?planet=&type=` | unified catalog (`type` ∈ IMAGERY, DEM, TOPOGRAPHY, WEATHER, GEOLOGY, BATHYMETRY) with status ONLINE_SOURCE / NOT_DOWNLOADED / VALID / INVALID / PARTIAL_COVERAGE / UNAVAILABLE |
| POST | `/datasets/register/` | register a file already inside `MARS_DATA_DIR` |

`POST /datasets/register/` body: `{"file_path": "raw/mola/x.xml", "name": "slug", "planet": "MARS", "source": "", "instrument": "", "product_id": "", "vertical_datum": "", "units": ""}`.
Checks: path inside the data dir, extension (`.tif .tiff .img .xml .lbl .cub .vrt`), content
signature, size limit, then the full validation (CRS for the planet, units, vertical datum,
valid values, radius guard, control points). 201 → `{dataset, warnings, steps}`; 422 →
`DATASET_INVALID` with `details.errors` and `details.steps`.

## Terrain

All point endpoints take `lon`, `lat`, optional `crs`, `planet`, `lat_convention`,
`dataset` (force one dataset). Values come only from a validated DEM of that body.

| Method | Path | Result |
|---|---|---|
| GET | `/terrain/coverage/` | `terrain_analysis_status` AVAILABLE / NO DATA / ERROR + covering datasets |
| GET | `/terrain/sample/` | elevation (nearest cell) — v0.1 shape + `results[]` |
| GET | `/terrain/elevation/` | elevation in the uniform result schema |
| GET | `/terrain/slope/` | slope, aspect, TRI, nodata fraction (v0.1 shape + `results[]`) |
| GET | `/terrain/aspect/` | aspect (degrees clockwise from north, downslope direction) |
| GET | `/terrain/roughness/` | Terrain Ruggedness Index (Riley et al. 1999), metres |
| GET | `/terrain/relief/?radius=` | local relief max−min in a (2r+1)² window (r 1–10, default 2) |
| GET | `/terrain/nodata/?radius=` | nodata coverage fraction in the window |
| GET | `/terrain/difference/?lon=&lat=&lon2=&lat2=` | elevation B − A (same dataset) |
| GET | `/terrain/area/?dataset=&bbox=w,s,e,n` | statistics in a bbox (windowed, decimated read) |
| GET | `/terrain/render/?dataset=&product=&bbox=&width=&height=` | **PNG visualization** (`elevation`, `hillshade`, `slope`, `aspect`, `roughness`), max 1024 px; headers `X-Value-Min/Max/Units`, `X-Valid-Fraction`, `X-Visualization` |

Uniform result schema (`result` / `results[]`):

```json
{"metric": "slope", "value": 1.13, "units": "degrees", "dataset_id": 1, "dataset": "mola-global",
 "source": "NASA PDS …", "resolution_m": 14817.8, "crs": "Equirectangular Mars",
 "vertical_datum": "MOLA areoid (GMM3 (mgm1025))", "nodata_status": "OK | PARTIAL_NODATA | NODATA",
 "processing_method": "Horn (1981) …", "window": "3x3 cells"}
```

`value` is `null` (never 0) when the data do not allow the computation.

## Routing

| Method | Path | Description |
|---|---|---|
| POST | `/routes/plan/` | A* route |
| GET | `/routes/` | saved routes (summary; `?mission=`) |
| GET | `/routes/profiles/` | CONSERVATIVE / STANDARD parameters + disclaimer |
| GET / DELETE | `/routes/{id}/` | saved route |

Request: `{"start": point, "end": point, "waypoints": [point…≤20], "profile": "CONSERVATIVE"|"STANDARD", "include_return": true, "include_alternative": true, "max_slope_deg"?, "mission"?, "dataset"?}`.
201 → `{id, status: "ROUTE_FOUND", route, return_route, alternative_route, grid, profile, dataset, hazards_considered, disclaimer}`.
`route` = `{geometry (LineString), distance_m, distance_3d_m, total_ascent_m, total_descent_m, max_step_grade_deg, unknown_terrain_fraction, unknown_terrain_distance_m, elevation_profile[]}`.
Failure 422 → `{"status": "INSUFFICIENT_TERRAIN_DATA" | "NO_PASSABLE_ROUTE", "route": null, "reason": "…"}`.

## Missions, waypoints, hazards (sync-aware)

| Method | Path |
|---|---|
| GET, POST | `/missions/`, `/waypoints/` (`?mission=`), `/hazards/` (`?mission=&hazard_type=&severity=&verification=`) |
| GET, PATCH, DELETE | `/missions/{id}/`, `/waypoints/{id}/`, `/hazards/{id}/` |

Missions and hazards carry `client_id` (UUID) and `version`. A POST with an existing
`client_id` returns the existing record (200, `"replayed": true`). A PATCH with a stale
`version` returns 409 `CONFLICT` with `details.server`; on success `version` increments.
PATCH without `version` keeps v0.1 behaviour. PUT is not allowed.

## Earth

| Method | Path | Description |
|---|---|---|
| GET | `/earth/gibs/layers/` | curated GIBS layers checked against the live EPSG:3857 GetCapabilities (24 h cache, `?refresh=1`): template, TileMatrixSet, max zoom, pixel size, format, TIME intervals, latest date, status |
| GET | `/geocoding/search/?q=` | Nominatim proxy (2–200 chars, 1 req/s, cached 24 h, explicit searches only) |
| GET | `/weather/current/?lat=&lon=` | Open-Meteo current conditions (`data_type: forecast_model`) |
| GET | `/weather/forecast/?lat=&lon=` | hourly (168 h) + daily (7 d) |
| GET | `/weather/historical/?lat=&lon=&start=&end=` | NASA POWER daily T2M, RH2M, PRECTOTCORR, WS10M (1981-01-01 … today, ≤ 366 days) |
| GET | `/weather/status/` | cache counts, last success, endpoints, provider terms |

Weather envelope: `{provider, data_type, coordinates, valid_time, retrieved_at, cache_age_s, from_cache, timezone, units, data, attribution, model_grid_cell?, missing_variables, note}`.
