# Deployment report — MARS EXPLORER v0.4

Date: 2026-11-15 · Branch `feature/v0.4-planetary-3d`

## Status: NOT DEPLOYED (prepared)

The application is **not publicly available yet**. Publishing needs accounts on a static host
and a Python host (and a PostgreSQL database), which belong to the project owner; no account was
created and nothing was published from this work. Everything needed to deploy is in the
repository and was tested locally.

| Item | Status |
|---|---|
| Public frontend URL | none yet |
| Public backend URL | none yet |
| What runs locally | everything: Vite dev server (5173), production preview (4173), Django (8000) |

## Prepared and tested

| Requirement | State | Evidence |
|---|---|---|
| Frontend reads `VITE_API_BASE_URL`; same-origin default in production; localhost only in development | IMPLEMENTED, TESTED | `services/api.ts` `resolveApiBase` + unit test |
| Page paths `/`, `/rover/`, `/map/` and refresh | IMPLEMENTED, TESTED | router `src/routes.ts`; `vercel.json`, `public/_redirects`; smoke test against the production build: all three return the app |
| Production build | TESTED | `npm run build` succeeds; service worker verified on the build (offline start, recovery) |
| Django production settings (DEBUG off, secret/hosts/CSRF/CORS/DATABASE_URL from env, HTTPS proxy, secure cookies, static files) | IMPLEMENTED, TESTED | `config/settings.py`; `tests/test_deploy_v04.py` |
| gunicorn, PostgreSQL driver, whitenoise | PREPARED | `requirements-prod.txt` (installed on the host, not in the local dev venv) |
| Migrations safe to run at each start | PREPARED | start command runs `migrate --noinput` |
| Rasters not stored in the database | IMPLEMENTED | dataset rows hold metadata and a path/URL only |
| Persistent scientific files | PREPARED | `MARS_DATA_DIR` on a disk; `bootstrap_demo_data` restores the demo DEM from NASA PDS with MD5 verification (tested with mocks; live manifest parse checked) |
| Environment examples | IMPLEMENTED | `backend/.env.production.example`, `frontend/.env.production.example` |
| Public demo protection (no sign-in) | IMPLEMENTED, TESTED | `PUBLIC_READ_ONLY` + operator `X-Api-Token`; computations stay open |
| Smoke test | IMPLEMENTED, TESTED | `scripts/smoke_test.py`: 13/13 against the local stack; against the production preview the CORS check correctly failed because that origin was not configured |
| Deployment guide | WRITTEN | `docs/DEPLOYMENT.md` |

## External dependencies at runtime

NASA Trek (tiles), NASA GIBS (Earth imagery), OpenStreetMap (Earth street map), USGS Astrogeology
STAC + S3 (Mars/Moon DTMs), Copernicus DEM on AWS Open Data (Earth elevation), NASA PDS (demo DEM
bootstrap), Open-Meteo and NASA POWER (Earth weather), optional Cesium ion (3D Tiles, browser token),
optional AI provider. None needs a key except Cesium ion and a remote AI provider.

## Hosting limitations (plan pages read 2026-11-15)

- Render free web services sleep after 15 minutes without traffic; the next request takes about a
  minute (**cold start**). They have no persistent disk: files written at runtime are lost on
  restart, so the demo DEM is re-downloaded (2 MB) by `bootstrap_demo_data` at start.
- Render free PostgreSQL: 1 GB, expires 30 days after creation, no backups — not suitable for data
  that must survive the judging period.
- Remote DTM reads take about 5–20 s for the first window of a product; repeated reads are fast.
- Vercel proxying (if used) times out after 120 s.

## Security checks

- No secret in the repository or in `VITE_` variables; `.env` files are git-ignored.
- The Cesium token (if used) is a public client credential: restrict scope, assets and allowed URLs.
- AI keys stay on the backend (`ANTHROPIC_API_KEY`); the frontend never calls an AI provider.
- Server file paths are never returned by the API (registry `local_file` is `REGISTERED` or null).
- Remote raster reads only from allow-listed hosts (`REMOTE_RASTER_HOSTS`), HTTPS, no credentials.
- Public writes to shared records are refused when `PUBLIC_READ_ONLY=True` (403 `READ_ONLY_DEMO`).

## To finish deployment (owner)

1. Create the database, backend service (with a disk) and static site as in `docs/DEPLOYMENT.md`.
2. Set the environment variables.
3. Run `python scripts/smoke_test.py --frontend … --api …` and record the result here.
4. Replace "NOT DEPLOYED" above with the URLs only after the smoke test passes.
