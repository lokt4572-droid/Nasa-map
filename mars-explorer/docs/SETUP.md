# Setup on Windows 11 (PowerShell)

Requirements: Python 3.12+ (tested with 3.14), Node.js 20+ (tested with 24), internet
access for NASA Trek tiles.

## 1. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-raster.txt   # GDAL via rasterio, needed for DEMs
Copy-Item .env.example .env              # then edit .env
python manage.py migrate
python manage.py runserver
```

API: http://127.0.0.1:8000/api/v1/health/

If PowerShell refuses to run `Activate.ps1`, allow local scripts for your user once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### backend/.env

| Variable | Meaning |
|---|---|
| `DJANGO_SECRET_KEY` | any long random string; required when `DEBUG=False` |
| `DEBUG` | `True` for local development |
| `ALLOWED_HOSTS` | `127.0.0.1,localhost` |
| `FRONTEND_ORIGIN` | `http://localhost:5173` (CORS) |
| `MARS_DATA_DIR` | `../data/mars` (relative to `backend/`) or an absolute path, e.g. `D:\mars-data` |
| `LOG_LEVEL` | `INFO` / `DEBUG` |
| `NASA_API_KEY` | not needed by NASA Trek WMTS; keep empty. Server-side only. |

## 2. Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local        # optional, defaults work locally
npm run dev
```

App: http://localhost:5173

### frontend/.env.local

| Variable | Default |
|---|---|
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000/api/v1` |
| `VITE_TREK_WMTS_BASE` | `https://trek.nasa.gov/tiles/Mars/EQ` |

Every `VITE_` variable is compiled into the browser bundle and is public. Never put a
secret or API key there. Keys for future APIs belong in `backend/.env`.

## 3. Checks

```powershell
cd frontend; npm run build; npm test
cd ..\backend; python manage.py check; python manage.py test
```

## GDAL on Windows

GDAL is optional for running the app; it is required only for reading DEMs.
The project uses the **rasterio wheel**, which bundles GDAL and PROJ, so no separate
GDAL installation (OSGeo4W/conda) is needed: `pip install -r requirements-raster.txt`.
Without it, `/health/` shows `raster_backend.available = false` and the terrain
endpoints return `503 DEM_BACKEND_UNAVAILABLE`; everything else works.

**Known issue — long paths.** rasterio loads GDAL DLLs from inside `.venv`. If the project
lives in a very deep folder, Windows can fail with
`ImportError: DLL load failed … The filename or extension is too long`. Fixes, in order:

1. Put the project in a short path, e.g. `C:\dev\mars-explorer`.
2. Or enable long paths (admin PowerShell, then reboot):
   `New-ItemProperty -Path HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force`
3. Or create the venv in a short folder (`python -m venv C:\venvs\mars`) and use that interpreter.

If `pip install rasterio` cannot find a wheel for a brand-new Python version, use the
newest Python that rasterio publishes wheels for (check https://pypi.org/project/rasterio/#files)
in a separate venv. The core Django install is independent of this.
