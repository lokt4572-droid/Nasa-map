# Earth 3D — validation (v0.5)

Date: 2026-11-15 · Branch `release/v0.5-nova`

## Why the Earth (and Mars/Moon) Cesium globe shows no relief here

Cesium World Terrain and the Cesium Mars/Moon tiles are streamed from **Cesium ion**, which needs a
browser token (`VITE_CESIUM_ION_TOKEN`). None is configured in this repository (tokens belong to the
project owner). Without it the globe shows the WGS 84 ellipsoid with imagery, and the app says so.
Local 3D terrain (below) does **not** need a token.

## Diagnostics panel (`earth-3d-diagnostics` in `Globe3D.tsx`)

Shows: 3D GLOBE, TERRAIN PROVIDER, ELEVATION DATA, IMAGERY, LAST TERRAIN UPDATE, LOCAL TERRAIN.

ELEVATION DATA is not assumed from the provider loading: after World Terrain is ready the app samples
Mount Everest (86.92527E, 27.98806N) with `sampleTerrainMostDetailed`; a height above 8000 m means
AVAILABLE, otherwise the panel reports that elevation is missing.

| Case | Result |
|---|---|
| No token (checked live) | "NOT CONFIGURED / MISSING — EARTH ELLIPSOID DISPLAYED" |
| With a token | NOT TESTED here (no token available); the Everest check decides AVAILABLE / missing |
| Imagery tile errors | counted via the provider's error and load-progress events and shown |

## Local Earth 3D (Copernicus GLO-30, no token)

From a clicked point, a DEM patch is read from the Copernicus DEM (a **surface model**: buildings and
vegetation included) and meshed in Three.js.

| Place | Elevation range shown | Result |
|---|---|---|
| Alps | 2297–4330 m | PASS (relief matches the area) |
| Kansas | 529–561 m | PASS (flat, as expected) |
| Ocean point | no tiles | by design NO DATA, never zero (catalogue rule; not re-checked live in v0.5) |

Terrain suitability (`terrain_suitability`) is shown with every patch: GLO-30 (~30 m) is
LOCAL_TERRAIN_AVAILABLE; MOLA is REGIONAL OVERVIEW ONLY.
