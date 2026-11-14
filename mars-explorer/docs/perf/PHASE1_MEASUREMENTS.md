# Phase 1 — map loading: measurements (2026-11-14)

Raw inputs for `docs/PERFORMANCE_REPORT_V0.3.md` (Phase 7). All numbers measured, single runs
unless noted; the NASA Trek server's latency varies by ±30 % between runs.

Setup: Vite dev server, in-app browser pane, map 466×212 CSS px (DPR 1.25), Mars, MOLA global
colour hillshade as base. Areas chosen fresh for each run so the browser HTTP cache does not
serve the tiles. Network baseline (no browser): `scripts/benchmark_tiles.py` →
`docs/perf/baseline_network.json`.

## Root cause (measured)

1. **Server latency dominates.** NASA Trek tiles: avg ≈ 3 s, P95 5–17 s, 100 % success inside
   the declared bbox. Trek serves HTTP/1.1 (≈ 6 connections per host for every Trek layer of
   every body) with no `Cache-Control` (browser heuristic caching from `Last-Modified`).
2. **Obsolete downloads were never cancelled.** OpenLayers' default `<img>` loader cannot abort.
   Tiles that left the view kept downloading and kept the 6 connections busy, delaying the tiles of
   the view the user actually looks at.
3. **Regional layers requested tiles at the global view.** CTX/HiRISE (0.5° mosaics) asked for
   coarse, mostly empty tiles at whole-planet zoom, competing with the base map.
4. **Per-tile React updates.** Every tile event wrote to the Zustand store (re-render storm while
   panning).
5. No HTTP status, timing or error category was visible: failures were all "tile error".

## Changes

| Change | File |
|---|---|
| fetch-based `tileLoadFunction`: AbortController, per-request timing + HTTP status, categories (NO_COVERAGE / HTTP_ERROR / SERVER_ERROR / RATE_LIMITED / TIMEOUT / CORS_OR_NETWORK / OFFLINE), max 3 retries for 408/429/5xx/timeout with exponential backoff + jitter, Retry-After honoured, failures never cached, tiles outside the declared bbox never requested, 404 at a coverage edge = NO_COVERAGE vs 404 inside coverage = HTTP_ERROR | `services/tileLoader.ts` |
| Cancel obsolete requests on `moveend` (outside the view buffered 25 %, or > 1 level finer than needed), on layer hide, on unmount; cancelled tiles go back to IDLE so they reload if revisited | `services/tileLoader.ts`, `components/map/MarsMap.tsx` |
| Regional layers render (and request) only when their bbox spans ≥ 64 px | `services/marsMapService.ts` (`regionalMaxResolution`) |
| Global base layers `preload: 1` (coarser level ready first), regional `preload: 0`; map `maxTilesLoading: 8` | `services/marsMapService.ts` |
| Tile counters for the UI throttled to ≤ 4 updates/s | `services/marsMapService.ts` (`attachTileStats`) |
| Diagnostics: events, per-layer health, success %, avg/P95, export JSON; aborted ≠ failure; path-only logging | `services/mapDiagnostics.ts`, `components/map/MapDiagnostics.tsx` |

## Before / after (browser)

| Scenario | Before (v0.2) | After (Phase 1) |
|---|---|---|
| MOLA regional view, uncached | 6 tiles; first 1.4 s; complete 2.6 s; net avg 2.0 s | 10 tiles (6 + 4 preload level); first 2.0 s; complete 4.4 s; avg 3.0 s, P95 3.6 s — server latency of that run, not app time |
| MOLA local view | 2 tiles, 0.7 s | 4 tiles, 1.3 s (avg 0.9 s) |
| Global view with CTX + HiRISE enabled | regional layers requested coarse tiles | **0 regional requests** (2 MOLA tiles, cached) |
| Rapid pan ×5 (300 ms apart), then wait | 18 tiles downloaded, 0 cancelled; final view complete **5.1 s** after last pan | 27 requested, **17 cancelled**, 10 downloaded; final view complete **3.7 s** (−27 %, single run) |
| Return to a cancelled area | n/a | tiles re-requested and loaded (2.8 s); none stuck in ERROR |
| Failed tiles in all runs | 0 | 0 |
| Duplicate requests | 0 | 0 (each tile counted once; retries counted separately) |

Interpretation: on a cold area the time is set by NASA Trek (≈ 2–3 s per tile). What the app
controls — wasted connections — is now removed: obsolete and invisible-layer requests are cancelled
or never sent, so the visible view gets the connections. The +4 preload tiles cost one round-trip at
the coarser level and give a low-resolution image under the detailed one during zoom/pan.

Not yet measured (Phase 7): throttled network profiles (slow 3G / high latency), NASA down
(simulated 503/timeout in the browser), offline mode in the browser.

## Tests

`frontend/src/services/tileLoader.test.ts` (24 tests): 200, 404 inside vs. at coverage edge, never
requesting outside bbox, other 4xx, 500→200 retry, 503 retry limit (3) with backoff 500/1000/2000 ms,
429 with Retry-After, timeout + retry, CORS/network, offline, cancellation on release, abortAll, cancel
during backoff, pruneObsolete (outside view / too fine / wrapped ±360°), path-only logging, no
duplicate counting, reset with in-flight requests, health derivation, regional resolution limit,
throttled UI counters. Frontend total: 102/102.
