# Nova — planetary GIS (formerly MARS EXPLORER)

Planetary GIS: real NASA maps of **Mars** (default), **Earth**, the **Moon**, **Mercury** and an experimental
**Venus** preview; real DEM analysis and A* route planning for Mars; Earth satellite imagery, weather, search,
geolocation and a 3D globe.

**Ground rules in the code:** no invented data. Imagery is never turned into elevation; missing DEM → `DATA NOT
AVAILABLE`; no route is drawn without real terrain data (`INSUFFICIENT_TERRAIN_DATA`); nothing is called "safe";
forecasts are labelled as model output; satellite dates come from GetCapabilities, never "today"; without a Cesium
token the globe says "NO TERRAIN"; the app says "OFFLINE READY: NO" because map tiles need the network.

## Start (Windows)
* **One click:** `START-MARS-EXPLORER.bat` (or the Desktop shortcut) → http://127.0.0.1:5173 · stop: `STOP-MARS-EXPLORER.bat`
* Manual: see [docs/SETUP.md](docs/SETUP.md).

## Layout
```
mars-explorer/
├── frontend/   React 19 + TS strict + Vite · OpenLayers 10 · proj4 · Zustand · CesiumJS (lazy) · fflate
├── backend/    Django 6 + DRF · SQLite · GDAL (rasterio) · PROJ (pyproj) · NumPy/SciPy
│   ├── apps/   core, datasets, missions, hazards, terrain, routing, planets, weather, geocoding, earth
│   └── services/ planet_registry, mars_coordinates, dem_reader, terrain_analysis, raster_render, dataset_manager, gibs, http_client, source_health
├── data/mars/  scientific data (git-ignored) — see data/mars/README.md
├── tools/      one-click start/stop scripts
└── docs/       SETUP, API_ENDPOINTS, DATA_SOURCES, COORDINATE_SYSTEM, PLANET_REGISTRY, EARTH_MODE,
                OFFLINE_MODE, LICENSES_AND_ATTRIBUTION, UPGRADE_PLAN, IMPLEMENTATION_REPORT_V0.2
```

## Highlights
* **Mars:** 4 Trek layers; real PDS4 MOLA MEGDR imported and validated (datum read from the label); elevation, slope,
  aspect, roughness, local relief, elevation difference, area stats; terrain visualization layers; A* planner with two
  documented heuristic profiles, waypoints, return/alternative routes, elevation profile, unknown-terrain share; missions,
  hazards, offline queue with conflict handling, ZIP mission packages.
* **Earth:** OSM + NASA GIBS (date control from capabilities), place/coordinate search, measure, geolocation (user-triggered),
  Open-Meteo forecast + NASA POWER history with charts, CesiumJS globe.
* **Moon / Mercury:** Trek mosaics and hillshades in their own CRS; catalog of DEMs (GLD100, LOLA, MESSENGER 665 m).
* **Venus:** honest preview (no Trek service; GTDR ≈ 5 km/px, radius values).
* **Data Manager:** unified catalog for all bodies with status, licence and provenance; safe import workflow.

Full status per feature: [docs/IMPLEMENTATION_REPORT_V0.2.md](docs/IMPLEMENTATION_REPORT_V0.2.md).

## Tests
`backend: python manage.py test` (130) · `frontend: npm test` (78).
