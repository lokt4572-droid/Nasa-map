# MARS EXPLORER

Interactive Mars mapping and navigation system for future crewed expeditions.

## Technology Stack

**Frontend**
- React 18 + TypeScript + Vite
- OpenLayers 10 for planetary mapping
- Zustand for state management
- CSS Modules for styling

**Backend**
- Django 5 + Django REST Framework
- SQLite (development) / PostgreSQL (production)
- NumPy, SciPy for terrain analysis
- GDAL/PROJ via pyproj (optional, graceful degradation)

**Data Sources**
- NASA Mars Trek WMTS Services
- MOLA Global Color Hillshade (463m/px)
- HRSC+MOLA Blend (200m/px)
- HiRISE Jezero Orthomosaic (25cm/px)

## Project Structure

```
mars-explorer/
├── frontend/           # React + TypeScript + Vite
├── backend/            # Django + DRF
├── data/mars/          # Scientific data storage
├── scripts/            # Data processing utilities
├── docs/               # Technical documentation
└── README.md
```

## Quick Start

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## NASA WMTS Layers

| Layer | Identifier | Resolution | Description |
|-------|------------|------------|-------------|
| MOLA Global | `Mars_MGS_MOLA_ClrShade_merge_global_463m` | 463 m/px | Global color hillshade |
| HRSC+MOLA Blend | `Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw` | 200 m/px | Regional detail |
| HiRISE Jezero | `JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd` | 25 cm/px | Jezero Crater orthomosaic |

## Documentation

- [Data Sources](docs/DATA_SOURCES.md)
- [API Endpoints](docs/API_ENDPOINTS.md)
- [Coordinate System](docs/COORDINATE_SYSTEM.md)
- [Setup Guide](docs/SETUP.md)
