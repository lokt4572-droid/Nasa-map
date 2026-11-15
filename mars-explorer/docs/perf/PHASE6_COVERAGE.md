# Phase 6 — High-resolution coverage explorer (2026-11-14)

Raw notes for `docs/IMPLEMENTATION_REPORT_V0.3.md` (Phase 7).

## What changed

- The standalone **JEZERO** map button is removed. A **COVERAGE** button (only on bodies that have
  regional datasets) opens `components/map/CoverageExplorer.tsx` — "HIGH-RESOLUTION COVERAGE".
- Regions come from the layer catalogue (`config/mapLayers.ts`: each regional layer carries a
  `region`), via `services/coverageCatalog.ts`. Jezero is one entry; adding a mosaic to the catalogue
  adds it to the explorer, the map outlines and auto high-resolution switching with no UI change.
- Per region: name, context, centre, area, **DEM availability from the backend** (registered DEMs at
  the region centre: LOCAL_DEM ≤ 100 m cells / REGIONAL_ONLY / NONE — never assumed), and per dataset:
  instrument, resolution, IMAGERY availability, actions **VIEW DATASET** (zoom to footprint),
  **OPEN IMAGERY** (switch on as a user choice + zoom), **OPEN LOCAL 3D** (selects the centre → local
  3D terrain panel), **VIEW METADATA** (Trek product id, mission, resolution, bbox, CRS, date,
  levels/verification date, GetCapabilities + Trek links, description).
- Coverage footprints on the map while the explorer is open (HiRISE solid amber, CTX dashed blue,
  region labels).

## New verified regional datasets (NASA Trek catalogue search → live GetCapabilities, 2026-11-14)

Found with `TrekServices/ws/index/eq/searchItems`; each checked for SupportedCRS
`urn:ogc:def:crs:EPSG::104905`, format, bbox, level count, and a tile at the bbox centre (HTTP 200).

| Region | Layer | Instrument | Levels | Finest tile level |
|---|---|---|---|---|
| Gale crater (Curiosity) | `curiosity_ctx_mosaic` | CTX | 11 | ≈ 41 m/px |
| Gale crater (Curiosity) | `curiosity_hirise_mosaic` | HiRISE | 17 | ≈ 64 cm/px |
| Gusev crater (Spirit) | `spirit_hirise_mosaic` | HiRISE | 18 | ≈ 32 cm/px |
| Meridiani Planum (Opportunity) | `opportunity_hirise_mosaic` | HiRISE | 18 | ≈ 32 cm/px |
| Green Valley (Phoenix) | `phoenix_hirise_mosaic` | HiRISE | 17 | ≈ 64 cm/px |
| Elysium Planitia (InSight) | `InSightCTXMosaic_112917` | CTX | 14 | ≈ 5 m/px |

The finest tile level of a Trek pyramid is reported as such — it is not claimed to be the source
product's resolution. Acquisition dates are not stated in GetCapabilities and are shown as
"not stated". Guessed layer names (e.g. `MSL_Gale_Orthophoto_Mosaic_25cm_v3`) returned 404 and
were not used.

## Verified in the browser

Explorer lists 6 regions with backend DEM status ("Only a 14.8 km/cell DEM (mola-global): regional
overview, no local-scale terrain" everywhere — only MOLA is registered); 8 footprints + 6 labels on the
map; no JEZERO button. Gale HiRISE: OPEN IMAGERY switched the layer on; at the Gale view 5/5 HiRISE
tiles loaded (0 failed) and the Gale CTX mosaic was switched on by auto high-resolution mode.

Note for verification: the in-app browser pane was hidden during part of this check; OpenLayers
animations (zoom-to actions) only advance on rendered frames, so they stall while the pane is hidden.
This is not an application bug; the view was set directly to confirm tile loading.

## Tests

`frontend/src/services/coverageCatalog.test.ts` (7): regions built from the catalogue (Jezero one of
≥ 6), every regional layer has a region, empty for bodies without regional data, auto switching for a
non-Jezero region (Gale), geometry helpers, DEM classification, JEZERO button removed.
Frontend 145/145, backend 166/166.
