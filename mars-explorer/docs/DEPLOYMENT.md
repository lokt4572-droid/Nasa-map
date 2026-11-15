# Deploying Nova for public access

## Quick deploy (Render, free plans, about 15 minutes)

1. Make sure the branch you deploy (normally `main`) contains this release (merge the pull request).
2. Sign in at https://dashboard.render.com (GitHub login is fine) and allow access to the repository.
3. **New → Blueprint** → choose the repository → Render reads `render.yaml` and proposes
   `nova-api`, `nova-web` and `nova-db` → **Apply**.
4. Wait until all three are "Live" (first build about 5–10 minutes).
5. If Render renamed a service (name already taken), open it → Environment and correct
   `ALLOWED_HOSTS`, `FRONTEND_ORIGIN`, `CSRF_TRUSTED_ORIGINS` (on nova-api) and `VITE_API_BASE_URL`
   (on nova-web) to the real URLs, then redeploy.
6. Optional: add `VITE_CESIUM_ION_TOKEN` on nova-web (see `SETUP_CESIUM.md`) and redeploy.
7. Check: `python scripts/smoke_test.py --frontend https://nova-web.onrender.com/ --api https://nova-api.onrender.com/api/v1`
8. Judges' link: **https://nova-web.onrender.com/map/**

Free-plan limits: the API sleeps after 15 min idle (~1 min to wake; the app shows a notice), the
database expires after 30 days. For judging day, switching `nova-api` to the Starter plan removes
the sleep.

---


Goal: judges open **one HTTPS link** and land in the working map — no installation, no sign-in.

Send judges the map link directly: **`https://<your-frontend>/map/`**. The site root (`/`) shows the
landing page → Curiosity profile → map flow; `/map/` skips straight to the workspace.

Status of this repository on 2026-11-15: **prepared, not deployed.** Deployment needs your own
accounts on the hosting providers; nothing has been published yet. See
`docs/DEPLOYMENT_REPORT.md`.

## 1. Architecture

```
Browser ──HTTPS──> static host (React build: /, /rover/, /map/ -> index.html)
   │
   ├──HTTPS──> Django API (gunicorn)  ── PostgreSQL (missions, hazards, routes, dataset metadata)
   │                 │
   │                 ├── persistent disk: MARS_DATA_DIR (original DEM files; never in the database)
   │                 └── remote COG reads: USGS Astrogeology, Copernicus DEM on AWS (no keys)
   │
   ├──HTTPS──> NASA Trek / NASA GIBS / OpenStreetMap tiles (direct from the browser)
   └──HTTPS──> Cesium ion (optional, browser token)
```

Storage is separated as required:

| What | Where | Survives redeploy? |
|---|---|---|
| Records (missions, hazards, routes, dataset metadata, AI audit) | PostgreSQL (`DATABASE_URL`) | yes (managed database) |
| Original DEM files | persistent disk at `MARS_DATA_DIR` | yes on a disk/volume; **no** on a free instance's filesystem |
| Remote DTMs (CTX, HiRISE, Kaguya, Copernicus) | read window by window from the provider | nothing stored |
| Frontend build | static host CDN | rebuilt on each deploy |
| Temporary processing | memory / GDAL cache | not needed after a request |

The demo needs only one local file set: MOLA MEGDR 4 px/deg (2 MB). `python manage.py
bootstrap_demo_data` downloads it from NASA PDS, checks it against the MD5 sums PDS publishes and
registers it; it does nothing when it is already present. Everything finer is read remotely.

## 2. Choosing hosts (plan limits read 2026-11-15 — check again before you choose)

The application is provider-neutral. Example files are included for Vercel/Netlify (frontend) and
Render (backend), but any static host plus any Python host with PostgreSQL works.

| Option | Facts that matter |
|---|---|
| Vercel Hobby (frontend) | free; 100 GB/month transfer; static SPA fine (`frontend/vercel.json`); can proxy `/api/*` to an external backend (120 s proxy timeout) |
| Netlify Free (frontend) | credit-based (300 credits/month); `frontend/public/_redirects` handles page paths |
| Render free web service (backend) | **sleeps after 15 min idle, ~1 min cold start; no persistent disk** (files lost on restart). Free Postgres: 1 GB, **expires after 30 days**, no backups. Not production-grade |
| Render paid web service + disk (backend) | disk persists across deploys (daily snapshots); needed for a stable public demo |
| Railway | free: $1/month credit, 500 MB volume; trial $5 for 30 days |

A free backend that sleeps or loses files must not be presented as permanent hosting. For judging,
either use a paid instance for the judging period or warn judges that the first request after a
pause can take about a minute.

## 3. Deploy the backend

1. Create a PostgreSQL database; copy its connection URL.
2. Create a Python web service from this repository with root directory `mars-explorer/backend`.
   - Build: `pip install -r requirements-prod.txt && python manage.py collectstatic --noinput`
   - Start: `python manage.py migrate --noinput && python manage.py bootstrap_demo_data && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers 2 --timeout 180`
   - Health check path: `/api/v1/health/`
   - Attach a persistent disk and point `MARS_DATA_DIR` at it (e.g. `/var/data/mars`).
3. Set the environment variables from `backend/.env.production.example` (section 5).
4. Render users can start from `render.yaml` at the repository root (Blueprint); it leaves every
   secret to the dashboard.

Never run `manage.py runserver` in production.

## 4. Deploy the frontend

1. Create a static site from `mars-explorer/frontend`: build `npm ci && npm run build`, output `dist`.
2. Set `VITE_API_BASE_URL=https://<your-backend>/api/v1` (or leave it empty if your host proxies
   `/api/*` to the backend on the same origin — then CORS is not involved).
3. Page paths: `vercel.json` (Vercel) and `public/_redirects` (Netlify) serve `index.html` for
   `/`, `/rover/`, `/map/` and refreshes. On other hosts add an equivalent "rewrite all non-file
   paths to /index.html" rule.

## 5. Environment variables

Backend (server only — see `backend/.env.production.example` for comments):

| Variable | Example | Notes |
|---|---|---|
| `DJANGO_SECRET_KEY` | long random value | required when `DEBUG=False` |
| `DEBUG` | `False` | |
| `ALLOWED_HOSTS` | `api.example.org` | host names, no scheme |
| `FRONTEND_ORIGIN` | `https://example.org` | CORS allow-list |
| `CSRF_TRUSTED_ORIGINS` | `https://example.org,https://api.example.org` | |
| `DATABASE_URL` | `postgres://…?sslmode=require` | PostgreSQL |
| `MARS_DATA_DIR` | `/var/data/mars` | on the persistent disk |
| `PUBLIC_READ_ONLY` | `True` | visitors cannot change shared records |
| `WRITE_API_TOKEN` | long random value | operators send `X-Api-Token` to write |
| `SECURE_SSL_REDIRECT` | `True` | behind the host's HTTPS proxy |
| `REMOTE_DEM_ENABLED` | `1` | remote DTMs (USGS, Copernicus) |
| `AI_PROVIDER` | `rules` | `rules` needs nothing; `anthropic` needs `ANTHROPIC_API_KEY` (server only) and `pip install -r requirements-ai.txt`; `ollama` needs `AI_BASE_URL` |

Frontend (compiled into public JavaScript — never secrets):

| Variable | Notes |
|---|---|
| `VITE_API_BASE_URL` | public backend URL ending in `/api/v1` |
| `VITE_TREK_WMTS_BASE` | `https://trek.nasa.gov/tiles/Mars/EQ` |
| `VITE_CESIUM_ION_TOKEN` | optional; **a public client credential**: restrict it (section 7) |

## 6. Migrations

`python manage.py migrate --noinput` runs at every start (safe to repeat). Migrations only add
tables/columns; they never drop user data. Back up the database before upgrading between versions.

## 7. Cesium

Follow `docs/SETUP_CESIUM.md`. For a public site: create a token with scope `assets:read`, only the
assets used (World Terrain, Cesium Mars 3644333, Cesium Moon 2684829), and your frontend URL in
**Allowed URLs**. Without a token the app shows `REQUIRES_USER_CONFIGURATION` for 3D Tiles and
everything else works. Check that your use fits the Cesium ion plan terms.

## 8. Allowed origins

`FRONTEND_ORIGIN` and `CSRF_TRUSTED_ORIGINS` must contain the exact frontend origin (scheme + host,
no trailing slash). The smoke test reports a CORS failure if they do not match.

## 9. Test the public deployment

```bash
python scripts/smoke_test.py --frontend https://<your-frontend>/ --api https://<your-backend>/api/v1
```

It checks: frontend and `/map/`, `/rover/` (page fallback), static files, API health, database,
version, GDAL, CORS, planet list, a real NASA Trek tile, Cesium status, a "no data" answer for a
location without elevation, and whether the public demo is read-only. Exit code 1 if anything fails.

Then verify map loading by hand in a browser: open `/map/` → the MOLA map appears within a few
seconds (NASA Trek latency), LAYER STATUS shows LOADED; click Jezero (18.4 N, 77.5 E) → the point
panel shows coverage AVAILABLE and the local 3D terrain loads; switch to Earth → the map appears.

## 10. Give judges the link

Share `https://<your-frontend>/map/` with one sentence: "Opens directly in the map; no sign-in.
The first request after a pause may take up to a minute (free hosting)." — only if that is true
for your host. Update `docs/DEPLOYMENT_REPORT.md` with the real URLs and the smoke test result.
