# Cesium ion setup (Earth terrain, Mars and Moon 3D Tiles)

Status on 2026-11-15: **REQUIRES_USER_CONFIGURATION** — no token is set in this checkout, so
none of the Cesium ion features below have been seen working here. Everything else (2D maps,
texture globes, local 3D terrain, routing) works without Cesium ion.

## What needs a token

| Feature | Cesium ion asset | Without a token |
|---|---|---|
| Earth "3D TERRAIN" relief | Cesium World Terrain | Globe with imagery on a smooth WGS 84 ellipsoid, labelled as having no elevation |
| Mars "3D TILES" | Cesium Mars, asset **3644333** | Status panel "REQUIRES_USER_CONFIGURATION"; texture globe and 2D map remain |
| Moon "3D TILES" | Cesium Moon, asset **2684829** | same |

Asset ids were checked against cesium.com on 2026-11-15
([Cesium Mars](https://cesium.com/platform/cesium-ion/content/cesium-mars/),
[Cesium Moon](https://cesium.com/platform/cesium-ion/content/cesium-moon/)).

## Steps (you do these; the app never creates accounts or handles your password)

1. Create or sign in to a Cesium ion account at <https://ion.cesium.com/>.
2. Read the plan conditions (next section) and decide whether your use fits the free
   Community plan.
3. In **Asset Depot**, add **Cesium Mars** and **Cesium Moon** to "My Assets"
   (Cesium World Terrain is included by default).
4. In **Access Tokens**, create a token for this app:
   - scope `assets:read` only;
   - restrict it to the assets you need (World Terrain, Mars, Moon);
   - under **Allowed URLs**, list the origins that will run the app
     (`http://127.0.0.1:5173`, `http://localhost:5173`, and your deployed origin).
5. Put it in `frontend/.env.local` (git-ignored — never commit it):
   ```
   VITE_CESIUM_ION_TOKEN=your-token
   ```
6. Restart the Vite dev server (Vite reads `.env.local` only at start) and reload the page.
7. Verify in the app:
   - Earth → **3D TERRAIN**: the banner must read "Cesium World Terrain is streaming";
   - Mars and Moon → **3D TILES**: the status chip must read **STREAMING**.
   If a request fails, the panel shows why (HTTP 401 = token rejected, 403/404 = asset not in
   the account or not allowed for the token, 429 = quota).

## The token is not a secret

Every `VITE_` variable is compiled into the JavaScript that browsers download. Anyone who
opens the app can read the token. Protect it with **Allowed URLs** and a minimal scope, not by
hiding it. The backend never sees or stores it.

## Plan conditions and terms (check them yourself before a public demo)

From the Cesium ion pricing page (read 2026-11-15):

- **Community (free)**: "Personal and non-commercial use"; also exploratory commercial or
  government development and unfunded educational activities. A paid plan is required for
  organisations above USD 50k revenue or funding, government projects, funded research, or
  when usage limits are exceeded.
- **Monthly limits (Community)**: 15 GB data streaming, 10 GB storage, 1 000 global imagery
  sessions.
- Whether a particular hackathon entry counts as non-commercial is the account holder's
  decision; this project cannot confirm it for you.

Cesium Mars and Cesium Moon are Cesium-hosted content under the Cesium ion Terms of Service
and the Cesium Global 3D Content terms. The underlying data comes from NASA and the USGS
Astrogeology Science Center, but the **tiles are not an open download**:

- the app only streams them into the viewer;
- it does not download, cache offline or redistribute them (the service worker excludes
  Cesium ion hosts);
- it does not use them as an elevation model for analysis or routing — those read the original
  NASA/USGS rasters on the backend.

Attribution is shown in each scene (Cesium's credit display plus the "DATA SOURCES AND
ATTRIBUTION" panel).

## How the scenes are configured

- Mars / Moon follow Cesium's published pattern: `Ellipsoid.default` is set to
  `Ellipsoid.MARS` / `Ellipsoid.MOON` before the `Viewer` is created, with `globe: false`,
  no base imagery, no geocoder and 3D mode only; the tileset is loaded with
  `Cesium3DTileset.fromIonAssetId`.
- `Ellipsoid.default` is global in CesiumJS. The scene sets it on creation and restores WGS 84
  when it is destroyed; only one Cesium viewer exists at a time and the Earth globe sets
  WGS 84 explicitly when it starts.
- Earth requests Cesium World Terrain with the water mask and vertex normals. If the terrain
  request fails, the globe falls back to the smooth ellipsoid and says so.

## Data provenance notices shown in the app

- **Mars, Jezero and Gale**: the high-resolution colour is estimated (red from the grayscale
  image, green and blue from low-resolution colour ratios; empty pixels filled). It is not
  verified natural colour.
- **Resolution is not uniform**: documented values are approximate and vary by region
  (Mars global ≈ 232 m imagery / 200 m terrain; Jezero ≈ 6 m / 20 m; Gale ≈ 0.25 m / 1 m;
  Moon 60°N–60°S ≈ 100 m / 59 m, polar terrain down to ≈ 5 m; Earth from ≈ 0.5 m in a few
  regions to ≈ 1 km globally).

## Offline

Cesium ion content cannot be used offline. Offline, the app keeps the 2D maps (within what the
browser has cached) and reports the 3D scenes as unavailable.
