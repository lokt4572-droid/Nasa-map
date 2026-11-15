# Planetary 3D and elevation data sources (v0.4)

Verified on 2026-11-15 unless stated. "Visualisation" sources are never used for measurements;
analysis (elevations, slopes, profiles, routes) reads only the elevation rasters listed under
"Analysis". Resolution is grid spacing, not accuracy.

## Visualisation (3D scenes)

| Body | Source | Access | Resolution (documented, approximate) | CRS / shape | Licence / terms | Status |
|---|---|---|---|---|---|---|
| Earth | Cesium World Terrain | Cesium ion (browser token) | 0.5–8 m selected regions; ~30 m regional; 30–90 m 60S–60N; ~1 km global | WGS 84 ellipsoid | Cesium ion ToS | REQUIRES_USER_CONFIGURATION (no token here) |
| Mars | Cesium Mars 3D Tiles, ion asset **3644333** | Cesium ion | global 232 m imagery / 200 m terrain; Jezero 6 m / 20 m; Gale 0.25 m / 1 m | IAU_2015:49901, `Ellipsoid.MARS` | Cesium ion ToS; data NASA + USGS Astrogeology | REQUIRES_USER_CONFIGURATION |
| Moon | Cesium Moon 3D Tiles, ion asset **2684829** | Cesium ion | 60N–60S 100 m / 59 m; poles terrain down to 5 m, LROC NAC 1 m imagery at 85.5–90° | `Ellipsoid.MOON` (Cesium does not state a CRS) | Cesium ion ToS | REQUIRES_USER_CONFIGURATION |
| Mercury | MESSENGER MDIS enhanced-colour mosaic (NASA Trek) on a Three.js sphere | WMTS | 665 m/px (globe texture ≈7.5 km/px) | Mercury sphere 2440.5 km | NASA public | IMPLEMENTED (no elevation applied; stated on screen) |
| Mars, Moon, Earth (no token) | Three.js texture globes (Trek / GIBS) | WMTS / WMS | see `PLANETARY_GLOBE_REPORT.md` | body ellipsoid | NASA public | IMPLEMENTED |
| Venus | — | — | — | — | — | NOT_IMPLEMENTED (optional) |

Cesium Mars provenance notice (shown in the app): in Jezero and Gale the high-resolution colour is
estimated — red from the grayscale image, green/blue from low-resolution colour ratios, empty
pixels filled. It is not verified natural colour.

Cesium-hosted data is streamed only: not downloaded, cached offline or redistributed.

## Analysis (elevation rasters)

| Body | Product | Provider / access | Posting | CRS | Vertical reference | Licence | Status |
|---|---|---|---|---|---|---|---|
| Mars | MOLA MEGDR 4 px/deg (`megt90n000cb`) | NASA PDS Geosciences; local file, MD5-checked | 14.8 km | equirectangular, sphere 3 396 000 m, clon 180 | MOLA areoid (GMM3, from the PDS label) | PDS public | IMPLEMENTED (regional planning only) |
| Mars | CTX DTMs (`mro_ctx_controlled_usgs_dtms`) | USGS Astrogeology STAC + COG range reads | ~20 m | IAU 2015 equirectangular per product | aligned to MOLA (provider statement; file tag `GEOID=mola`) | CC0-1.0 | IMPLEMENTED |
| Mars | HiRISE DTMs (`mro_hirise_socet_dtms`) | USGS STAC + COG | ~1–2 m | per product | NOT_DOCUMENTED in the STAC item (see the PDS label) | CC0-1.0 | IMPLEMENTED |
| Moon | Kaguya TC v2 DTMs (`…_v2`, `…_v2_southpolar`, `…_v2_northpolar`) | USGS STAC + COG | ~30 m | equirectangular / polar stereographic | aligned to LOLA; reference surface NOT_DOCUMENTED in the item | CC0-1.0 | IMPLEMENTED (live-checked at 0.7 N, 85 S, 89.2 S) |
| Earth | Copernicus DEM GLO-30 Public | AWS Open Data tile list + COG (no key) | 1″ (~30 m) | EPSG:4326 | EGM2008 geoid (product specification; not in the file) | Copernicus DEM licence, attribution required | IMPLEMENTED (**surface model**, oceans = no data) |
| Earth | GEBCO, GLO-90, regional DEMs | manual download + `import_dem` | — | per product | per product | per product | supported, not bundled |
| Mercury | USGS MESSENGER global DEM 665 m | manual download + `import_dem` | 665 m | per product | per product | USGS/NASA public | REQUIRES_USER_CONFIGURATION |
| Moon | LOLA, SLDEM2015 | manual download + `import_dem` | — | — | — | PDS public | supported, not bundled |

Datasets are never merged: a patch, profile or route uses one DEM, with its datum stated.

## Attribution strings used in the app

- NASA Solar System Treks; NASA GIBS / ESDIS; USGS Astrogeology Science Center (+ mission);
- "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved";
- Cesium (ion assets), data NASA + USGS Astrogeology; © OpenStreetMap contributors.
