# Known limitations — v0.4

| Area | Limitation | Status |
|---|---|---|
| Cesium | No ion token in this checkout: Earth World Terrain, Mars and Moon 3D Tiles were not seen streaming. Configuration states and error handling were verified | REQUIRES_USER_CONFIGURATION |
| Deployment | Prepared and tested locally; not published (needs the owner's hosting accounts) | NOT_DEPLOYED |
| Free hosting | Render free sleeps after 15 min (~1 min cold start), no persistent disk; free Postgres expires after 30 days | documented |
| Remote DTMs | First read of a product 8–15 s (provider throughput); repeats are fast (window cache) | BLOCKED_BY_EXTERNAL_SERVICE for first reads |
| DEM per request | A patch, profile or route uses one DEM. Earth tiles are 1×1°: a patch beyond the tile edge shows NoData there; routes cannot span two Copernicus tiles or two DTM products | PARTIALLY_IMPLEMENTED |
| Polar footprints | Catalogue footprints around a pole are tested in lon/lat and can match falsely; the data-gap check then skips them, so nothing wrong is shown | documented |
| Polar 2D maps | No verifiable NASA Trek polar stereographic layer was found; polar 2D views not implemented. Lunar polar local terrain works (Kaguya polar DTMs) | NOT_IMPLEMENTED (2D) |
| Mars polar terrain | MOLA polar products not imported; MEGDR covers to ±90 at 14.8 km only | REQUIRES_USER_CONFIGURATION |
| Mercury | Globe has no elevation; the 665 m USGS DEM must be imported manually | REQUIRES_USER_CONFIGURATION |
| Venus | Preview only | NOT_IMPLEMENTED (optional) |
| Bathymetry | No keyless gridded bathymetry; GEBCO import supported | NO_DATA_COVERAGE |
| AI perception | No validated planetary hazard detector; ingest of external detections is off by default | NOT_IMPLEMENTED (by design) |
| AI language models | Tested with mocks only; no Ollama or Anthropic key configured here. Default `rules` parser works | TESTED (mocked) |
| Routing scale | ≤ 300 cells per side; profiles are heuristics; no travel time; no safety claims | documented |
| Geolocation | Permission-denied path verified in the browser; granted/timeout/accuracy/recentering need a real device | PARTIALLY_IMPLEMENTED (manual check pending) |
| GPU FPS | Not measured (browser pane does not render while hidden) | NOT_MEASURED |
| Tablet layout | Not checked on a tablet | PARTIALLY_IMPLEMENTED |
| Authentication | No user accounts; public demo protected by `PUBLIC_READ_ONLY` + operator token | documented decision |
