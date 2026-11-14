# Data sources (v0.2)

How each fact was established:
- **verified** = this project fetched the live service / GetCapabilities / official page or file on the date given;
- **from specification** = the official page refused automated access (USGS Astrogeology answered HTTP 403 on
  2026-11-14), so the value comes from the project specification and must be confirmed by hand.

Field order per product: official name · publisher · mission · instrument · URL · format · resolution ·
spatial coverage · time range · CRS · vertical datum · licence / terms · limitations.

---

## Mars

### MGS MOLA Mission Experiment Gridded Data Records (MEGDR) — topography, PDS4
- **Publisher:** NASA Planetary Data System, Geosciences Node · **Mission:** Mars Global Surveyor · **Instrument:** MOLA
- **URL:** https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/ (folders meg004 … meg128, polar)
- **Format:** raw 16-bit image (`.img`) + PDS4 label (`.xml`); PDS3 `.lbl` also provided
- **Resolution:** 4, 16, 32, 64, 128 px/deg; `megt90n000cb` = 4 px/deg = 14 817.8 m/px (derived by the importer)
- **Coverage:** global (polar products separate) · **Time:** MGS altimetry 1997–2001
- **CRS:** Simple Cylindrical / Equirectangular on a 3 396 000 m sphere, east-positive, planetocentric (from label; GDAL: "Equirectangular Mars", central meridian 180)
- **Vertical datum:** label: "Topography is the planetary radius minus the areoid radius"; areoid = Goddard Mars potential model GMM3 (mgm1025)
- **Licence:** NASA PDS public data
- **Limitations:** 4 px/deg is coarse (≈14.8 km/cell); radius files (`megr…`) are NOT elevations
- **Status:** `megt90n000cb` downloaded 2026-11-14 with the user's consent, MD5 matches the bundle manifest, imported as `mola-global` (VALID). **verified**

### HiRISE Digital Terrain Models
- **Publisher:** University of Arizona (HiRISE team) · **Mission:** Mars Reconnaissance Orbiter · **Instrument:** HiRISE (stereo)
- **URL:** https://www.uahirise.org/dtm/ · background https://hirise.lpl.arizona.edu/dtm/about.php
- **Format:** per product (GeoTIFF/IMG with labels) · **Resolution:** typically 1–2 m post spacing from 0.25–0.5 m images
- **Coverage:** regional, only where stereo DTMs were produced · **Time:** per product
- **CRS / datum:** per product label · **Licence:** NASA/UA public data
- **Limitations:** not every stereo pair has a DTM; orthoimages are not DTMs · **Status:** REQUIRES_USER_DATA

### NASA Solar System Treks WMTS — Mars layers
- **Publisher:** NASA Solar System Treks (JPL) · **URL:** https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars
- **Format:** OGC WMTS RESTful, JPEG/PNG tiles · **CRS:** declared `urn:ogc:def:crs:EPSG::104905` (see COORDINATE_SYSTEM.md)
- Layers (verified 2026-11-12): `Mars_MGS_MOLA_ClrShade_merge_global_463m` (463 m/px, global, 8 levels),
  `Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw` (200 m/px, global, 9 levels),
  `JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0` (6 m/px, Jezero 77.16–77.70 E, 18.21–18.72 N, 14 levels),
  `JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd` (25 cm/px, Jezero 77.22–77.58 E, 18.31–18.67 N, 18 levels)
- **Vertical datum:** n/a (images) · **Licence:** NASA public data
- **Limitations:** colour hillshades and mosaics are visualizations — never used as elevation. Service quirks: decimal `MatrixWidth` (normalized), ScaleDenominator ≈2·10⁻⁶ relative offset (harmless)

## Moon

### NASA Moon Trek WMTS
- **URL:** https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=moon · **CRS:** declared `urn:ogc:def:crs:EPSG::104903`
- `LRO_WAC_Mosaic_Global_303ppd_v02` — LRO LROC WAC mosaic, 303 px/deg (≈100 m/px), global, JPEG, 9 levels. **verified 2026-11-14**
- `LRO_LOLA_ClrShade_Global_128ppd_v04` — LRO LOLA colour hillshade, 128 px/deg (≈237 m/px), global, PNG, 6 levels. **verified 2026-11-14**

### LRO LROC WAC Global Morphology Mosaic 100 m
- **Publisher:** USGS Astrogeology · **Mission:** LRO · **Instrument:** LROC WAC
- **URL:** https://astrogeology.usgs.gov/search/map/moon_lro_lroc_wac_global_morphology_mosaic_100m
- **Resolution:** ≈100 m/px · **Coverage:** global — **from specification** (page HTTP 403 to automated access)

### LROC WAC GLD100
- **Publisher:** LROC team (Arizona State University) · **Mission:** LRO · **Instrument:** LROC WAC stereo
- **URL:** https://data.lroc.im-ldi.com/lroc/view_rdr/WAC_GLD100 (readme: …/WAC_GLD100_README.TXT)
- **Resolution:** 100 m/px tiles (also 256/128 ppd, simple cylindrical 64–4 ppd); formal resolution ≈300 m; vertical accuracy ≈10–20 m
- **Coverage:** 79°S–79°N, 98.2 % of the surface; poles need LOLA · **Projections:** Equirectangular (±60°), Polar Stereographic (60–90°)
- **Vertical datum / format:** not stated on the product page · **Licence:** NASA PDS public data · **Status:** REQUIRES_USER_DATA. **verified (page) 2026-11-14**

### LOLA
- Global laser-altimetry DEM; shown through the Trek colour hillshade above; DEM download from PDS (LRO LOLA RDR) — REQUIRES_USER_DATA.

## Mercury

### NASA Mercury Trek WMTS
- **URL:** https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mercury · **CRS:** declared `urn:ogc:def:crs:IAU2000::19900`
- `Mercury_MESSENGER_mosaic_global_250m_2013` — MDIS global mosaic, 250 m/px, PNG, 8 levels. **verified 2026-11-14**
- `Mercury_Messenger_USGS_DEM_665m_v2_HillshadeColor` — colour hillshade of the USGS DEM, PNG, 6 levels. **verified 2026-11-14**

### USGS MESSENGER Global DEM 665 m
- **Publisher:** USGS Astrogeology · **Mission:** MESSENGER · **Instrument:** MDIS (stereo)
- **URL:** https://astrogeology.usgs.gov/search/map/mercury_messenger_global_dem_665m
- **Resolution:** ≈665.24 m/px · **Coverage:** lat −90…90, lon 0…360 · **Latitude:** planetocentric · **Longitude:** positive east · **Units:** m — **from specification**
- **Limitations:** low detail; never presented as high-resolution topography · **Status:** REQUIRES_USER_DATA

## Venus (experimental)

### Magellan Global Topographic Data Record (GTDR)
- **Publisher:** NASA PDS · **Mission:** Magellan · **Instrument:** radar altimeter
- **URL:** https://pds.nasa.gov/ds-view/pds/viewDataset.jsp?dsid=MGN-V-RDRS-5-GDR-TOPOGRAPHIC-V1.0 · data: https://pds-geosciences.wustl.edu/missions/magellan/gxdr/
- **Resolution:** ≈5 × 5 km/px · **Projections:** sinusoidal, Mercator, north and south polar stereographic
- **Values:** planetary radius (ranges subtracted from spacecraft radial coordinate) — not heights; the importer rejects radius values
- **Limitations:** no NASA Trek service exists for Venus (checked 2026-11-14) → no interactive map. **verified (page) 2026-11-14**

## Earth

### NASA Global Imagery Browse Services (GIBS)
- **Publisher:** NASA EOSDIS · **URL:** https://nasa-gibs.github.io/gibs-api-docs/ · capabilities https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/wmts.cgi?SERVICE=WMTS&REQUEST=GetCapabilities
- **Format:** WMTS REST tiles (JPEG/PNG) · **CRS:** EPSG:3857 (`GoogleMapsCompatible_LevelN`)
- **Layers used (all present in the live capabilities 2026-11-14):** MODIS Terra/Aqua True Color, VIIRS NOAA-20/SNPP True Color, Blue Marble Next Generation, Blue Marble Shaded Relief + Bathymetry, MODIS Terra Cloud Fraction (Day), MODIS Combined Value-Added AOD, OMI Aerosol Index, AMSR2 Columnar Water Vapor (ended 2025-09-01), GPM IMERG Precipitation Rate (daily; latest 2026-11-12 — lags today), Reference Labels/Features, Coastlines
- **Resolution:** pixel ≈305.7 m (Level 9) … ≈2.4 km (Level 6) at the equator, derived from the TileMatrixSet
- **Time:** per layer, intervals with gaps as published · **Licence:** NASA open data; attribution requested
- **Limitations:** visualizations; recent days may be partial; IMERG is a gridded multi-satellite estimate, not a gauge measurement

### OpenStreetMap standard tiles · Nominatim
- **Publisher:** OpenStreetMap Foundation · **URLs:** https://tile.openstreetmap.org/{z}/{x}/{y}.png, https://nominatim.openstreetmap.org/search
- **Licence:** data ODbL, "© OpenStreetMap contributors" · **Policies:** https://operations.osmfoundation.org/policies/tiles/ , …/nominatim/
- **Limitations:** no bulk/offline tile download; Nominatim ≤ 1 req/s, no autocomplete, cache results, identifying User-Agent

### Open-Meteo forecast API
- **URL:** https://api.open-meteo.com/v1/forecast · docs https://open-meteo.com/en/docs · terms https://open-meteo.com/en/terms
- **Data:** numerical weather model output for a grid cell (`forecast_model`), 7 days, units in each response
- **Licence:** CC BY 4.0; free tier non-commercial, < 10 000 calls/day, 5 000/h, 600/min

### NASA POWER daily point API
- **URL:** https://power.larc.nasa.gov/api/temporal/daily/point · docs https://power.larc.nasa.gov/docs/
- **Parameters:** T2M (C), RH2M (%), PRECTOTCORR (mm/day), WS10M (m/s) — units read from each response; fill value −999
- **Time:** 1981-01-01 → near real time · **Sources:** reported per response (e.g. MERRA-2, GEOS-IT)
- **Limitations:** coarse reanalysis/satellite grid; historical context, not a forecast or station data

### Copernicus DEM GLO-30 / GLO-90
- **Publisher:** ESA / Copernicus (DLR, Airbus) · **Mission:** TanDEM-X · **URL:** https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM
- **Format:** GeoTIFF / DTED, 1°×1° tiles · **Resolution:** 1″ (≈30 m) / 3″ (≈90 m) · **Time:** acquired 2011–2015
- **CRS:** WGS84-G1150 (EPSG:4326) · **Vertical datum:** EGM2008 (EPSG:3855) · **Accuracy:** vertical < 4 m LE90, horizontal < 6 m CE90
- **Licence:** free licence; attribution "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA"
- **Limitations:** Digital SURFACE model (buildings, vegetation), not bare-earth · **Status:** REQUIRES_USER_DATA

### GEBCO_2026 Grid + TID Grid
- **Publisher:** GEBCO / BODC · **URL:** https://www.gebco.net/data-products/gridded-bathymetry-data
- **Format:** netCDF / GeoTIFF / Esri ASCII (≈4 GB global; 8 tiles of 90°×90° available) · **Resolution:** 15 arc-second grid (not equal to accuracy)
- **Coverage:** global land + ocean · **Vertical datum:** mean sea level (with stated exceptions) · **Licence:** public domain, subject to GEBCO conditions of use
- **Limitations:** heterogeneous quality; parts interpolated; not for navigation · **Status:** REQUIRES_USER_DATA

### Cesium World Terrain (3D globe)
- **Publisher:** Cesium · **URL:** https://cesium.com/platform/cesium-ion/content/cesium-world-terrain/
- **Access:** Cesium ion account and access token (`VITE_CESIUM_ION_TOKEN`) · **Terms:** Community plan for personal/non-commercial use, monthly quotas (pricing page read 2026-11-14)

## Software
GDAL 3.12.2 via rasterio 1.5.2 · PROJ via pyproj 3.8 · OpenLayers 10.11 · proj4js 2.22 · CesiumJS 1.147 · fflate (ZIP).
