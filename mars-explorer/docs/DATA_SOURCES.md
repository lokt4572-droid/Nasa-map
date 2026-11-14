# Data sources

All sources below were checked on 2026-11-12 (HTTP 200).

## Online map layers — NASA Mars Trek WMTS

Documentation: https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars
No API key is required. Each layer is configured in `frontend/src/config/mapLayers.ts`
and its tile grid is always read at runtime from its GetCapabilities document:
`https://trek.nasa.gov/tiles/Mars/EQ/<LayerId>/1.0.0/WMTSCapabilities.xml`

| Layer identifier | Content | Stated resolution | Format | TileMatrix levels* | Bounding box (W, S, E, N)* |
|---|---|---|---|---|---|
| `Mars_MGS_MOLA_ClrShade_merge_global_463m` | MGS MOLA global colour hillshade | 463 m/px | JPEG | 8 (0–7) | −180, −89.9991635, 179.9983271, 90 |
| `Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw` | MOLA + Mars Express HRSC colour hillshade blend | 200 m/px | JPEG | 9 (0–8) | −180, −89.999224, 179.9984479, 90 |
| `JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0` | MRO CTX orthomosaic, Jezero | 6 m/px | PNG | 14 (0–13) | 77.1604655, 18.2110274, 77.6991776, 18.7211945 |
| `JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd` | MRO HiRISE controlled orthomosaic, Jezero | 25 cm/px | PNG | 18 (0–17) | 77.2229331, 18.3067994, 77.583964, 18.669315 |

\* From GetCapabilities on 2026-11-12. All four use TileMatrixSet `default028mm`,
style `default`, `SupportedCRS urn:ogc:def:crs:EPSG::104905`, TopLeftCorner (−180, 90),
256×256 tiles, RESTful encoding, CORS `Access-Control-Allow-Origin: *`.

**These are images.** Colour hillshades and orthomosaics are never used as elevation
values in this application.

### Verified service quirks

1. **Decimal matrix sizes.** Trek writes `<MatrixWidth>2.0</MatrixWidth>`; the OGC schema
   expects an integer. OpenLayers 10.11 then leaves the tile ranges undefined and loads no
   tiles at all. `marsMapService.normalizeTrekCapabilitiesXml` rewrites integral values
   (`2.0` → `2`) and rejects anything non-integral. Covered by a regression test.
2. **ResourceURL double slash.** Templates contain `/1.0.0//{Style}/…`; the service
   answers these URLs with HTTP 200 (verified), so they are used as published.
3. **Scale denominators.** Converting Trek's ScaleDenominator with OpenLayers' metres per
   degree (2π·6 370 997 / 360) gives 0.70312358 °/px at level 0 instead of exactly
   0.703125 — a 2×10⁻⁶ relative difference, < 0.1 px across a whole level-7 matrix.
4. **CRS identifier** — see [COORDINATE_SYSTEM.md](COORDINATE_SYSTEM.md).

## Elevation data (DEMs) — loaded locally

| Product | Source | Notes |
|---|---|---|
| MGS MOLA MEGDR (PDS4, maintained) | https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/ | "MGS MOLA Topography Derived bundle": MEGDR topographic maps and SHADR spherical harmonics. Overview page: https://pds-geosciences.wustl.edu/missions/mgs/mola.html. The PDS page states the final MEGDRs use the IAU 2000 coordinate system. |
| MGS MOLA MEGDR (PDS3, legacy) | https://pds-geosciences.wustl.edu/missions/mgs/megdr.html | Older archive format; GDAL's PDS driver reads the `.lbl` label. |
| HiRISE DTMs | https://www.uahirise.org/dtm/ | Built from stereo pairs; not every pair has a DTM. Background: https://hirise.lpl.arizona.edu/dtm/about.php |

The application does not ship or download DEMs. See `data/mars/README.md`.

## Software

* GDAL (raster I/O; PDS, PDS4, ISIS3 drivers) via the rasterio 1.5.2 wheel (bundles GDAL 3.12.2).
  PDS4 driver docs: https://gdal.org/en/stable/drivers/raster/pds4.html
* PROJ via pyproj 3.8 (Mars CRS definitions ESRI:104905, ESRI:104971, IAU_2015:499xx).
* OpenLayers 10.11, proj4js 2.22 in the browser.
