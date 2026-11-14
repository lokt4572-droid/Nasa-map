# Earth mode

Open with the **EARTH** button (Mars stays the start body). Sidebar: Layers · Satellite · Weather · Location · Terrain · 3D Globe · Data Manager.

## 2D map (OpenLayers, EPSG:3857)
* **Street map:** OpenStreetMap standard tiles, attribution always visible. Viewing only: no prefetch, no offline
  download, browser HTTP cache only (OSMF tile policy).
* **Satellite / atmosphere / precipitation / reference:** NASA GIBS layers discovered from the live GetCapabilities by
  the backend (`/api/v1/earth/gibs/layers/`). The XYZ URL is built from the published ResourceURL template;
  `maxZoom` = the layer's TileMatrixSet level.
* **Dates:** date picker limited to the published intervals; ◀ ▶ skip gaps; **Latest** = last published date (may be
  partial, and may lag today — IMERG was 2 days behind on 2026-11-14). Never labelled LIVE. Dates without imagery hide
  the layer instead of requesting empty tiles. Sub-daily layers: date selection not supported.
* **Metadata per layer:** title, instrument, satellite, source, pixel size at max zoom, time resolution, temporal
  coverage, latest date, attribution, CRS, status.
* **Search:** "Search location, city, country..." → backend Nominatim proxy (explicit search only, no autocomplete,
  1 req/s, cached, attribution shown). Typing `lat, lon` works without Nominatim.
* **Measure:** click points; geodesic length on a sphere (R = 6 371 008.8 m).
* **Point panel:** planet, latitude, longitude, CRS EPSG:4326, DEM/elevation (DATA NOT AVAILABLE without an Earth DEM),
  local time and sunrise/sunset (Open-Meteo, with timezone), current weather.

## Location (browser Geolocation API)
* Never requested on page load. **MY LOCATION** = one fix; **START TRACKING** = separate explicit action; **STOP TRACKING**.
* States: IDLE, REQUESTING_PERMISSION, LOCATING, LOCATED, PERMISSION_DENIED, POSITION_UNAVAILABLE, TIMEOUT
  (+ UNSUPPORTED, INSECURE_CONTEXT — requires HTTPS or localhost).
* Shows latitude, longitude, accuracy (95 % radius circle on the map), last update, speed only if reported, source.
  Accuracy worse than 1 km is flagged (likely Wi-Fi/IP).
* Nothing is stored or sent to the backend; the position is cleared when leaving Earth. Disabled for Mars/Moon/Mercury/Venus.

## Weather
| Category | Provider | Shown as |
|---|---|---|
| Forecast | Open-Meteo | `forecast_model` — model output for a grid cell (grid cell shown), not a measurement |
| Satellite precipitation | NASA GIBS / GPM IMERG | map overlay with its own date |
| Historical | NASA POWER daily | reanalysis / satellite-derived, coarse grid |

WEATHER OVERVIEW tabs: CURRENT · HOURLY (temperature, precipitation, wind/gusts charts) · 7 DAYS (table + chart) ·
HISTORICAL (date range, 4 charts). All charts have a real time axis and units; missing values are gaps, not zeros.
Requests are made only for the selected point and active tab; the backend caches (forecast 15 min, POWER 24 h) and
never labels an expired answer as current.

## Terrain & bathymetry
Elevation legend classes: below sea level · 0–500 m · 500–2000 m · above 2000 m (display only; values shown numerically).
Real values require importing Copernicus DEM (DSM, EGM2008) or GEBCO_2026 tiles:
`python manage.py import_dem --planet EARTH --file … --name … --instrument "TanDEM-X" --vertical-datum "EGM2008"`.
Terrain colour layers from an Earth DEM are not implemented in the Earth map yet (Mars only).

## 3D globe (CesiumJS)
* Lazy-loaded. Rotate, zoom, tilt, pick point (height from terrain), measure (WGS 84 geodesic), fly to my location,
  switch to 2D; imagery = selected base (OSM or GIBS) + overlays, draped on the surface (not a 3D atmosphere).
* **Terrain:** Cesium World Terrain only with `VITE_CESIUM_ION_TOKEN` (frontend/.env.local). Without it the globe is a
  smooth ellipsoid and says **NO TERRAIN** — it is never presented as relief.
* The token is public in the browser: restrict it to your domains, do not commit it, mind Community-plan quotas.
