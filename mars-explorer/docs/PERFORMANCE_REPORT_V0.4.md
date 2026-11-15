# MARS EXPLORER v0.4 — Performance report

Date: 2026-11-15 · Machine: Windows 11 laptop, 16 GB RAM, 16 logical cores (browser reports
`deviceMemory` 16) · Single runs unless stated; provider latency varies between runs.
Raw data: `docs/perf/v04_backend.json` (before the window cache), `docs/perf/v04_backend_cached.json`
(after, fresh server process). v0.3 baseline: `docs/PERFORMANCE_REPORT_V0.3.md`.

External network time and application time are reported separately: NASA Trek, USGS S3 and
Copernicus latency are not under the application's control and were not "eliminated".

## 1. 2D map (browser, in-app diagnostics)

Fresh, never-visited regional view (Acidalia, 52° N), MOLA colour hillshade, 1280 px-class viewport:

| Metric | v0.3 (2026-11-14) | v0.4 |
|---|---|---|
| Time to first visible tile | 1.7 s | 1.9 s |
| Fully loaded viewport | 4.6 s | 5.1 s |
| Tiles requested / loaded / failed / retried | 18 / 18 / 0 / 0 | 18 / 18 / 0 / 0 |
| Average / P95 tile time | 1.66 s / 2.6 s | 1.96 s / 3.1 s |

Unchanged within NASA Trek's run-to-run variation: per-tile latency is the provider's. The v0.3
cancellation, retry and fallback behaviour is unchanged (failure scenarios: v0.3 report §4).

## 2. Terrain data (backend API, `scripts/benchmark_v04.py`)

"Cold" = first request in a freshly started server process; "warm" = median of 3 repeats.

| Request | Cold | Warm before cache | Warm after cache |
|---|---|---|---|
| Patch 256², MOLA 4 px/deg (local file) | 0.46 s | 0.47 s | 0.35 s |
| Patch 256², HiRISE Jezero (remote COG) | 9.7 s | 0.57 s | 0.57 s |
| Patch 256², HiRISE Gusev (remote, new product) | 14.0 s (24.8 s in run 1) | **11.2 s** | **0.55 s** |
| Patch 256², Kaguya TC Moon (remote) | 11.6 s | 0.57 s | 0.49 s |
| Patch 256², Copernicus GLO-30 Alps (remote) | 8.3 s | 0.13 s | 0.09 s |
| Elevation profile, 200 samples, HiRISE | 9.7 s | **10.4 s** | **0.50 s** |
| Catalogue search, USGS STAC (point) | 4.0 s | 0.26 s | 0.25 s |
| Catalogue search, Copernicus tile list (bbox) | 0.03 s | 0.03 s | 0.02 s |
| Route, MOLA regional 740 km | 1.0 s | 1.1 s | 1.0 s |
| Route, MOLA across lon 0° (seam) | 0.9 s | 1.0 s | 0.8 s |
| Route, HiRISE Jezero 380 m + return + alternative (260×300 grid) | 15.5 s | **12.7 s** | **4.0 s** |

Finding: GDAL kept remote file headers between requests but not decoded blocks, so repeated
views, profiles and routes downloaded the same blocks again (11–13 s each). Fix:
`services/window_cache.py`, a bounded (256 MB default) LRU of decoded remote windows. First reads
remain network-bound: about 8–15 s for a new product (header, validation and blocks from S3,
measured 0.3–1 MB/s from this location). A larger GDAL `/vsicurl/` cache or HTTP/2 multiplexing
was tested and did not help (multiplexing was slower).

## 3. 3D

| Metric | Result |
|---|---|
| Mesh creation (`buildTerrainMesh`, browser) | 128²: 4.3 ms · 256²: 5.2 ms · 384²: 11.7 ms · 512²: 18.9 ms (median of 5) |
| Point click → first visible local 3D model | Jezero HiRISE 3.2 s · Gale HiRISE 9.4 s · MOLA-only point 3.1 s (DEM registered; includes catalogue lookup) |
| Mesh budget | 128² on ≤ 2 GB / ≤ 2 cores, 256² default, 384² expanded on ≥ 8 GB / ≥ 8 cores; hard caps 512² / 522 242 triangles |
| WebGL contexts during 6 globe visits | before fix: 1 live while shown, **12 never released**; after fix (`forceContextLoss`): 1 while shown, **0** after leaving |
| Memory over 40 view switches (8 views × 5: Mars/Moon/Mercury/Earth, map/globe/3D Tiles) | JS heap 65–81 MB per round, no growth; always one map viewport; 0 Cesium viewers left |
| GPU rendering FPS | NOT MEASURED: the in-app browser pane renders frames only when visible; a reliable FPS needs a visible window on target hardware |

## 4. Offline and production build

Production build (`vite build`): main bundle 1.5 MB (431 kB gzip), Cesium chunk 4.9 MB (1.36 MB
gzip, loaded only for Cesium views). Service worker on the build: registration, activation, cache
versioning (v3 → v4, old cache deleted), offline start of `/`, `/rover/`, `/map/` with the server
stopped, and recovery after restart — all verified. A cache-fill bug found here was fixed (see
the implementation report).

## 5. Not measured

Bandwidth throttling, a real mobile device, sustained multi-user load, and Cesium ion streaming
(no token configured).
