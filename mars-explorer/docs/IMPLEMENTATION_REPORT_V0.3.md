# MARS EXPLORER v0.3 — Implementation report

Date: 2026-11-14 · Branch `feature/v0.3-performance-globes` (from `3c8e20c`, tag `restore-point-v0.2`)
Not pushed, not merged. `main` on origin unchanged.

Status labels: IMPLEMENTED, TESTED, PARTIALLY_IMPLEMENTED, NOT_IMPLEMENTED, NO_DATA_COVERAGE,
BLOCKED_BY_EXTERNAL_SERVICE, REQUIRES_USER_CONFIGURATION.

## 1. Summary

v0.3 fixes slow and incomplete map loading (measured root cause: NASA Trek latency plus obsolete
downloads occupying its ~6 HTTP/1.1 connections), adds adaptive high-resolution layers, textured 3D
globes for Earth/Mars/Moon/Mercury, click-to-explore local 3D terrain from real DEM patches, a stricter
A* planner (no corner cutting, route classes, comparison), and a catalogue-driven high-resolution
coverage explorer replacing the Jezero button. Two pre-existing DEM bugs at the MOLA MEGDR seam were
found and fixed. Nothing scientific is invented: no fake terrain, imagery, DEM values or dates.

## 2. Git and safety (Part 9)

- Phase 0: status reviewed, v0.2 work committed and pushed earlier (`3c8e20c`), restore tag
  `restore-point-v0.2`, new branch, single writer, no destructive commands.
- Commits: `7e9780d` P1 · `4725fa5` P2 · `bdff704` P3 · `62a0021` P4 · `6b18452` P5 · `d19342a` P6 ·
  Phase 7 reports (this commit, when made).
- 57 files changed, +5 817 / −106 lines (P1–P6). No secrets; private user data never sent to services.

## 3. Phase status

| Phase | Status |
|---|---|
| 0 Audit and protect | IMPLEMENTED |
| 1 Diagnose and fix map loading | IMPLEMENTED, TESTED (measured before/after) |
| 2 Adaptive layer loading | IMPLEMENTED, TESTED |
| 3 Three.js globes | IMPLEMENTED, TESTED for Earth/Mars/Moon/Mercury; Venus NOT_IMPLEMENTED; pre-built offline textures NOT_IMPLEMENTED |
| 4 Local 3D terrain | IMPLEMENTED, TESTED; local-scale Mars terrain REQUIRES_USER_CONFIGURATION (only MOLA 15 km registered); Moon/Mercury/Earth NO_DATA_COVERAGE |
| 5 A* improvements | IMPLEMENTED, TESTED |
| 6 Coverage explorer | IMPLEMENTED, TESTED |
| 7 Benchmarks, verification, reports | IMPLEMENTED (see limits in §15) |

## 4. Map loading (Phase 1) — see `docs/PERFORMANCE_REPORT_V0.3.md`

Fetch-based WMTS tile loader (AbortController, HTTP status and timing per request, error categories
NO_COVERAGE / HTTP_ERROR / SERVER_ERROR / RATE_LIMITED / TIMEOUT / CORS_OR_NETWORK / OFFLINE, max 3
retries for 408/429/5xx/timeout with exponential backoff + jitter + Retry-After, failures never cached,
tiles outside the declared bbox never requested), obsolete-request cancellation (view change, hide,
unmount; cancelled tiles go back to IDLE), regional resolution limits, low-resolution-first preload,
`maxTilesLoading` 8, throttled UI counters, diagnostics service + LAYER STATUS panel (health,
success %, avg/P95, export; aborted ≠ failed; path-only logging).

## 5. Adaptive layers (Phase 2)

View scale GLOBAL/REGIONAL/LOCAL on the body's own radius; coverage of each layer at the current view;
auto high-resolution switching for any regional layer (global parent never removed, user choices win,
2× hysteresis); status bar names the instrument drawn at the centre, finer data available and overzoom.
New verified global layers: Viking MDIM 2.1 colorized (232 m), THEMIS Day IR (100 m, thermal — labelled).

## 6. Globes (Phase 3) — see `docs/PLANETARY_GLOBE_REPORT.md`

## 7. Local 3D terrain (Phase 4) — see `docs/LOCAL_3D_TERRAIN_REPORT.md`

## 8. Routing (Phase 5) — see `docs/ROUTING_VALIDATION_V0.3.md`

## 9. Coverage explorer (Phase 6)

JEZERO button removed; COVERAGE button → "HIGH-RESOLUTION COVERAGE" built from the layer catalogue:
6 regions (Jezero, Gale, Gusev, Meridiani, Phoenix site, InSight site), 8 regional mosaics, DEM
availability from the backend, VIEW DATASET / OPEN IMAGERY / OPEN LOCAL 3D / VIEW METADATA, footprints
on the map. The 6 new mosaics were found via the NASA Trek catalogue search and each verified against
live GetCapabilities plus a centre tile; guessed layer names that 404'd were not used.

## 10. UI modes

2D MAP / 3D GLOBE (+ 3D TERRAIN on Earth = Cesium) in a view switch; modes a body lacks are hidden.
LOCAL 3D TERRAIN opens from a selected point (point panel), DATA LAYERS = layer list, DATA COVERAGE =
coverage explorer. Mars remains the default body. Layout checked at the in-app pane sizes used
(≈ 470–800 px wide); no dedicated tablet pass — PARTIALLY_IMPLEMENTED for responsive verification.

## 11. Data sources verified live (2026-11-14)

NASA Trek WMTS (Mars, Moon, Mercury layers listed in `config/mapLayers.ts` / `planetTextures.ts`),
NASA Trek catalogue search, NASA GIBS WMS EPSG:4326 (Blue Marble NG), backend MOLA MEGDR (PDS).
OpenStreetMap standard tiles are never bulk-cached or prefetched (unchanged).

## 12. Bugs found and fixed during v0.3

1. Hidden layers left unfinished tiles in LOADING, holding OpenLayers queue slots (P1).
2. Layer card counted cancelled tile requests as failures (P2).
3. Globe texture tile range overshoot at the world edge (P3).
4. MOLA MEGDR seam: lon 0° reported as outside the DEM (P4, pre-existing).
5. Grids crossing the MEGDR seam read wrong (decimated) cells, also in `/terrain/render` (P4, pre-existing).
6. Diagnostics reset counted in-flight tiles as loads without requests (P1).
7. Route points on the MEGDR seam (P5).

## 13. Tests (Part 8)

| Suite | Count |
|---|---|
| Backend (Django) | 166 / 166 (v0.2: 140) |
| Frontend (Vitest) | 145 / 145 (v0.2: 78) |
| New map reliability tests | 24 (`tileLoader.test.ts`) |
| New adaptive / coverage / globe / terrain tests | 18 + 7 + 11 + 8 (frontend), 11 (backend) |
| New routing tests | 15 (backend) |

Map reliability list covered: valid caps (existing), wrong matrix / invalid config (existing parse
tests), missing coverage, 404 inside vs at edge, 429, 500, 503, timeout, CORS/network, offline,
duplicates, cancellation (release, abortAll, during backoff, pruning), retry limits, fallback layer
(browser), regional resolution limit.

## 14. Browser verification (in-app browser, 2026-11-14)

| Check | Result |
|---|---|
| Mars 2D map, tiles, LAYER STATUS panel | OK |
| Auto high-res at Jezero and Gale; off when leaving | OK |
| Earth / Mars / Moon / Mercury globes, picking, switching | OK |
| Coverage explorer, 6 regions, footprints, Jezero metadata, Gale OPEN IMAGERY (5/5 HiRISE tiles) | OK |
| Click-to-3D on Mars (MOLA), no-DEM message on the Moon | OK |
| Route Planner UI (classification, A/B table, regional banner) | OK |
| Loading indicators, high latency, NASA down, offline (fetch-level simulation) | OK — see performance report |
| Earth 2D map / weather panel | panel OK; map canvas not re-checked (pane hidden, OL renders only on frames) |
| Console | only expected API statuses (404/422) and simulated failures |

## 15. Known limitations

- Only one DEM (MOLA MEGDR, ≈ 14.8 km) is registered: local terrain and routing are regional-only until
  a HiRISE/CTX DTM is imported (REQUIRES_USER_CONFIGURATION).
- NASA Trek latency dominates first loads (BLOCKED_BY_EXTERNAL_SERVICE for anything faster than its
  ~2–3 s per tile); Trek 404s lack CORS headers, so browsers report them as network errors.
- Globes need the network (no pre-built offline textures); Venus has no globe.
- Failure scenarios were simulated by wrapping `fetch` in the page (not OS-level network shaping).
- Expanded local-terrain view and tablet layout not screenshotted.

## 16. How to run

Unchanged: `START-MARS-EXPLORER.bat` (or `.claude/launch.json`: backend on 127.0.0.1:8000, Vite on
5173). Tests: `backend\.venv\Scripts\python.exe manage.py test` and `npm test` in `frontend/`.
Network benchmark: `backend\.venv\Scripts\python.exe scripts\benchmark_tiles.py --out <file>`.

## 17. Next steps (not done)

Import a HiRISE/CTX DTM for local terrain and route studies; pre-built offline globe textures; a stitched
routing window across the DEM seam; tablet layout pass; push/merge after review (requires your approval).
