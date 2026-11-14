# MARS EXPLORER — technical foundation v0.1

Interactive map of Mars for exploring the surface and preparing future crewed-mission
planning tools. It uses real NASA Mars Trek WMTS layers for display and is prepared to
read real DEMs (MOLA MEGDR, HiRISE DTM) for elevation and slope.

**Ground rules built into the code:** no invented data. Imagery is never turned into
elevation. If no validated DEM covers a point, the app shows `Elevation: DATA NOT
AVAILABLE`. Route planning returns `501 NOT_IMPLEMENTED`. Nothing is labelled "safe".

## Layout

```
mars-explorer/
├── frontend/   React 19 + TypeScript (strict) + Vite + OpenLayers 10 + proj4 + Zustand
├── backend/    Django 6 + DRF, SQLite; services/ (coordinates, DEM reader, terrain analysis, dataset manager)
├── data/mars/  local scientific data (git-ignored) — see data/mars/README.md
├── scripts/    check_data.py, inspect_dem.py
└── docs/       DATA_SOURCES, API_ENDPOINTS, COORDINATE_SYSTEM, SETUP
```

## One-click start (Windows)

* **Start:** double-click `START-MARS-EXPLORER.bat` (or the *MARS EXPLORER* shortcut on the
  Desktop). It installs missing dependencies on first run, stops old copies of the servers,
  starts backend + frontend in two minimized windows and opens http://127.0.0.1:5173.
* **Stop:** double-click `STOP-MARS-EXPLORER.bat`.

## Manual start (PowerShell)

```powershell
# backend
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-raster.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py runserver          # http://127.0.0.1:8000/api/v1/health/

# frontend (second terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

Details, environment variables and the Windows GDAL notes: [docs/SETUP.md](docs/SETUP.md).

## What works

* NASA Mars Trek WMTS layers loaded via GetCapabilities (MOLA global hillshade, MOLA+HRSC
  blend, CTX Jezero, HiRISE Jezero), toggles, opacity, retry on failure.
* Mars CRS registered in OpenLayers/proj4; pan/zoom; zoom to global / Jezero; cursor
  coordinates; scale bar computed on the Mars ellipsoid.
* Point selection → coordinates with CRS/conventions, layer source & resolution, DEM
  coverage, elevation and slope **from a registered DEM only**.
* Missions with waypoints (demo mode), hazard reports (CRUD, map symbols).
* Dataset manager: `python manage.py import_dem` (+ `--dry-run`), `check_datasets`,
  REST registration of files inside the data dir, UI Data Manager.
* Terrain API: elevation (nearest cell), slope/aspect (Horn), TRI, nodata fraction,
  explicit planetocentric/planetographic handling.
* Local mission package (JSON export + IndexedDB copy).

## Not implemented yet

Route planning, validated hazard/traversability model, DEM interpolation, slope/
hillshade raster products, DEM tile serving to the map, offline map tiles / service
worker, authentication, astronaut positioning hardware, polar projections.

## Tests

```powershell
cd backend;  python manage.py test     # 69 tests
cd frontend; npm test                  # 38 tests
```
