# Nova — final readiness report (v0.5 release candidate)

Date: 2026-11-15 · Branch `release/v0.5-nova` (PR to `main`) · Formerly "MARS EXPLORER"

## Status

| Area | Status | Evidence |
|---|---|---|
| Rename to Nova (`/`, `/rover/`, `/map/` kept; landing and rover pages text-only changes) | DONE | page check, `V05_PHASE5_CHECKS.md` |
| Route planning: A*, source-DEM validation, line-based metrics, unverified segments | DONE, TESTED | `ROUTING_FINAL_VALIDATION.md` |
| Terrain suitability labels (MOLA = overview only) | DONE, TESTED | `tests/test_v05.py` |
| Earth 3D diagnostics; World Terrain elevation check | DONE; token path NOT TESTED | `EARTH_3D_VALIDATION.md` |
| Local 3D terrain for Earth, Mars, Moon (no token) | DONE, live-checked | Alps, Kansas, Jezero |
| Routes on local 3D terrain + "Route in 3D" | DONE, live-checked | Jezero A/B 100 % inside patch |
| Product metadata: DTM vs DSM, source imagery, coverage (CTX, HiRISE, Kaguya v2 + polar, Copernicus, MOLA) | DONE, TESTED | live API on Mars, Moon, Earth |
| Mission ZIP: waypoints, several hazards, planned route, duplicate import | DONE, TESTED | `packageRoundTrip.test.ts` |
| Earth 2D, planet switching, geolocation (denied path) | CHECKED | `V05_PHASE5_CHECKS.md` |
| Smoke test incl. route planner and weather | 15/15 PASS locally | `scripts/smoke_test.py` |
| Public deployment | **NOT DEPLOYED** — prepared | `DEPLOYMENT_REPORT.md` |

## Tests

Backend 280/280 · Frontend 198/198 · TypeScript clean · Smoke test 15/15 (local).

## Needs the project owner

1. Merge the PR into `main`.
2. Render: New → Blueprint → this repository (`render.yaml`), then run the smoke test against the
   public URLs (`docs/DEPLOYMENT.md`).
3. Optional: a Cesium ion token (`VITE_CESIUM_ION_TOKEN`) for Cesium Earth/Mars/Moon relief.

## Not verified

Cesium ion streaming (no token), geolocation with permission granted, real mobile devices,
multi-user load, the public deployment itself.
