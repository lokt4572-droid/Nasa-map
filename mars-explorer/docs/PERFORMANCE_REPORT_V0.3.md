# MARS EXPLORER v0.3 — Map performance report

Date: 2026-11-14 · Raw data: `docs/perf/baseline_network.json`, `docs/perf/after_network.json`,
`docs/perf/PHASE1_MEASUREMENTS.md`. All numbers are single measured runs unless stated; NASA Trek
latency varies by roughly ±30 % between runs.

## 1. Method — network latency vs application rendering are measured separately

- **Network (server side, no browser)**: `scripts/benchmark_tiles.py` reads each layer's real
  GetCapabilities, computes the tiles a 1280 × 800 viewport needs at GLOBAL / REGIONAL / LOCAL levels,
  fetches them with 4 parallel connections and records status, duration, size. Never touches
  OpenStreetMap.
- **Application (in the in-app browser)**: harness on the running app; per-tile timing and status from
  `services/mapDiagnostics.ts` (requested / loaded / failed / aborted / retries, avg / P95), viewport
  complete = no request in flight for 1.5–2 s. Fresh areas per run so the HTTP cache does not serve tiles.
- **Failure scenarios**: simulated by wrapping `window.fetch` for NASA Trek tile URLs only (added latency,
  HTTP 503, network failure + `navigator.onLine = false`). This exercises the app's handling exactly, but
  it is not OS-level network shaping (bandwidth throttling was not simulated).

## 2. Root cause (measured)

| Finding | Evidence |
|---|---|
| NASA Trek is slow per tile | avg 2.2–4.6 s, P95 3.7–17 s across Mars/Moon/Mercury layers (both network runs) |
| Few connections | Trek serves HTTP/1.1 → ≈ 6 connections per host shared by all Trek layers of all bodies |
| App wasted those connections | OpenLayers' `<img>` loader cannot cancel: tiles that left the view kept downloading; regional layers fetched coarse, mostly empty tiles at the global view |
| No visibility | failures were all "tile error": no status, timing or cause |
| Re-render storm | every tile event wrote to the app store |

Server-side numbers did not change between the baseline (14:26 UTC) and the after run (15:46 UTC):
the app cannot make NASA faster; it can stop wasting connections and fail predictably.

### Network benchmark (4 parallel, 1280 × 800 viewport)

| Layer | View | Baseline avg / P95 (ms) | After avg / P95 (ms) | Success |
|---|---|---|---|---|
| MOLA colour hillshade | GLOBAL | 3 516 / 6 835 | 2 994 / 7 434 | 100 % → 87.5 % (1 network failure) |
| MOLA colour hillshade | REGIONAL | 4 011 / 8 219 | 3 632 / 7 488 | 100 % |
| MOLA colour hillshade | LOCAL | 3 106 / 7 406 | 3 111 / 6 114 | 100 % |
| MOLA + HRSC blend | REGIONAL | 3 174 / 5 675 | 3 168 / 5 356 | 100 % |
| CTX Jezero | LOCAL | 2 850 / 5 243 | 3 125 / 7 109 | 100 % |
| HiRISE Jezero | LOCAL | 3 076 / 7 602 | 2 872 / 6 451 | 100 % |
| Moon LRO WAC | REGIONAL | 2 598 / 6 805 | 2 485 / 4 381 | 95.8 % → 100 % |
| Mercury MDIS 250 m | GLOBAL | 4 561 / 17 311 | 3 449 / 9 149 | 100 % |

## 3. Application before / after (browser)

| Scenario | v0.2 (before) | v0.3 (after) |
|---|---|---|
| Rapid pan ×5 (300 ms apart), final view complete | 18 downloads, 0 cancelled, **5.1 s** | 27 requested, **17 cancelled**, 10 downloaded, **3.7 s** (−27 %) |
| Global view with CTX + HiRISE enabled | regional layers request coarse tiles | **0 regional requests** |
| MOLA regional view, uncached | 6 tiles, complete 2.6 s | 10 tiles (6 + 4 coarser preload), complete 4.4 s — that run's server latency (avg 3.0 s) |
| Return to a cancelled area | n/a | tiles re-requested and loaded, none stuck |
| Hidden layer | in-flight tiles left LOADING (blocked queue slots) | cancelled and reset |
| Store writes during panning | one per tile event | ≤ 4 per second |
| Failed / duplicate requests (normal) | 0 / 0 | 0 / 0 |

## 4. Failure scenarios (v0.3, browser, fetch-level simulation)

| Scenario | Result |
|---|---|
| Normal (fresh area, 18 tiles) | first tile 1.7 s, complete 4.6 s, avg 1.66 s, P95 2.6 s, 18/18 loaded |
| High latency (+1.5 s per tile) | complete 8.6 s, avg 3.0 s, P95 5.8 s, 18/18 loaded, 0 failures, no retries |
| NASA Trek down (HTTP 503) | 16 tiles × **exactly 4 attempts** (1 + 3 retries, backoff 0.5/1/2 s + jitter) = 64 requests, settled after 9.5 s, layer **FAILED** with "SERVER_ERROR HTTP 503 …", LAYER STATUS "1 issue"; no endless retry |
| NASA down while zooming into a loaded area | 13 detailed tiles failed (4 attempts each); **lower-resolution imagery stayed on screen** (441/441 canvas samples painted) |
| NASA down in an area never loaded | blank map at that place (no imagery exists at any level) — reported as FAILED, nothing invented |
| Offline | **0 requests**, 8 tiles FAILED as OFFLINE without retries, header "NO NETWORK" |
| Timeout, 429 + Retry-After, CORS/network | covered by unit tests (`tileLoader.test.ts`) |

## 5. Caching (per terms)

NASA Trek: browser HTTP cache only (Trek sends Last-Modified/ETag, no Cache-Control); failures never
cached by the app. NASA GIBS: `Cache-Control: no-store` → not cached. OpenStreetMap: never bulk-cached
or prefetched (OSMF policy). No credentials or headers are logged (paths only).

## 6. Conclusions

- The slowness users see on first load is **NASA Trek's per-tile latency** (BLOCKED_BY_EXTERNAL_SERVICE
  for anything below ≈ 2–3 s per tile on a cold area).
- The app no longer makes it worse: obsolete and invisible requests are cancelled or never sent, coarse
  imagery appears first and stays under failing detail tiles, and every failure is classified, bounded
  and visible in LAYER STATUS.
- Not measured: bandwidth throttling, real OS-level offline, tablet hardware.
