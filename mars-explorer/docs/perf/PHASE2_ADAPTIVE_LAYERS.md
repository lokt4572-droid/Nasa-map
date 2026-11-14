# Phase 2 — adaptive layer loading (2026-11-14)

Raw notes for `docs/IMPLEMENTATION_REPORT_V0.3.md` (Phase 7).

## What it does

- **View scale** GLOBAL (> 2 km/px) / REGIONAL (50 m – 2 km/px) / LOCAL (< 50 m/px), computed on
  the current body's own equatorial radius (`services/adaptiveLayers.ts: viewScale`).
- **Coverage per layer at the current view** (layer list): coverage in view / no coverage in this
  view / in view — zoom in to display / in view, beyond native resolution.
- **Auto high-resolution layers** (setting, default on, persisted): a regional layer switches on when
  its coverage is in view and spans ≥ 64 px; it switches off when its coverage leaves the view or you
  zoom out 2× past the threshold (hysteresis, no flicker). It works for any regional layer in the
  catalog — Jezero is only the first such entry.
- **The global parent layer is never switched off**: outside a regional mosaic the parent stays
  visible (no gaps, no substitution).
- **User choice wins**: a layer you switch off is never switched back on by auto mode; a layer you
  switch on is never switched off by it. Auto changes never change the active layer.
- **Products are not interchangeable**: the status bar names the instrument drawn at the view centre
  (e.g. "HiRISE 25 cm/px"), says when finer data exists there, and warns when the view is beyond the
  product's native resolution (pixels enlarged).

## New verified Mars layers (filling the gap between MOLA 463 m and CTX 6 m)

Checked against live GetCapabilities on 2026-11-14 (SupportedCRS `urn:ogc:def:crs:EPSG::104905`,
test tile HTTP 200):

| id | Trek layer | resolution | levels | kind |
|---|---|---|---|---|
| `viking-mdim21-color` | `Mars_Viking_MDIM21_ClrMosaic_global_232m` | 232 m/px | 10 | colorized albedo mosaic |
| `themis-day-ir-100m` | `Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12_clon0_ly` | 100 m/px | 11 | daytime thermal IR (new `THERMAL_IR_MOSAIC` kind; legend explains it is temperature, not reflectance or elevation) |

`Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12` (without `_clon0_ly`) returns HTTP 404 — not used.
Both are off by default; added to the frontend catalog and to `backend/services/planet_registry.py`.

## Caching (per provider terms)

- NASA Trek: browser HTTP cache via fetch default mode (Trek sends Last-Modified/ETag, no
  Cache-Control → heuristic freshness). Failed responses are never cached by the app.
- NASA GIBS (Earth): sends `Cache-Control: no-store`; not cached by the app.
- OpenStreetMap standard tiles: never bulk-cached or prefetched (OSMF tile policy) — unchanged.

## Fix found during verification

The layer card's "N tile request(s) failed" counted OpenLayers `tileloaderror` events, which
cancellations must emit to free the tile-queue slot → cancelled requests showed as failures. The
warning now uses the measured diagnostics (`failed`, which excludes cancellations).

## Tests

`frontend/src/services/adaptiveLayers.test.ts` (18 tests). Frontend 120/120, backend 140/140.
Browser: at Jezero (0.0013°/px) CTX + HiRISE switched on automatically ("switched on
automatically"), status "REGIONAL · HiRISE 25 cm/px"; at −120°/−30° they switched off and MOLA
stayed; at the global view no regional requests.
