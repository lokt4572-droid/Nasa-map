# Licences and attribution

This file summarises the terms read on 2026-11-14. It is not legal advice — re-check the providers' pages before any
commercial or public deployment.

| Provider | What we use | Terms (summary) | Attribution shown in the app |
|---|---|---|---|
| **NASA** (Solar System Treks, PDS, GIBS, POWER) | Trek WMTS tiles, PDS MOLA MEGDR, GIBS imagery, POWER data | NASA data are generally free to use; NASA asks for credit and its insignia/logos must not imply endorsement. POWER asks to cite the POWER project. | "NASA Solar System Treks", "Imagery: NASA GIBS, part of NASA EOSDIS", POWER citation text |
| **USGS Astrogeology** | catalog entries (Mercury DEM 665 m, Moon WAC 100 m) | US government products are generally public domain; verify the product page (automated access returned 403) | credit "USGS Astrogeology Science Center" when the products are used |
| **LROC / ASU** | GLD100 catalog entry | NASA PDS data release | "NASA/GSFC/Arizona State University" when used |
| **ESA / Copernicus** | Copernicus DEM GLO-30/90 (user download) | free licence for GLO-30/90 | "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; all rights reserved" |
| **OpenStreetMap** | standard tiles, Nominatim search | data ODbL; tile policy: identifying User-Agent/Referer, honour caching, no bulk/offline download; Nominatim ≤ 1 req/s, no autocomplete, cache results | "© OpenStreetMap contributors" on the map; "Search © OpenStreetMap contributors (ODbL), Nominatim" in results |
| **GEBCO** | GEBCO_2026 grid (user download) | public domain, subject to GEBCO conditions of use; not for navigation | "GEBCO Compilation Group (2026) GEBCO 2026 Grid" (DOI 10.5285/4f68d5c7-45eb-f999-e063-7086abc036fa) |
| **Open-Meteo** | forecast API (via backend) | API data CC BY 4.0; free tier non-commercial, < 10 000 calls/day, 5 000/h, 600/min; upstream model data have their own licences | link "Weather data by Open-Meteo.com" next to all weather data |
| **Cesium** | CesiumJS (Apache 2.0) and optionally Cesium ion / World Terrain | Cesium ion Community plan: personal / non-commercial (or exploratory) use with monthly quotas; paid plans for commercial, government or funded projects | Cesium credits shown by the viewer |

Software dependencies keep their own licences (Django BSD, DRF BSD, OpenLayers BSD-2, proj4js MIT, React MIT,
Zustand MIT, fflate MIT, CesiumJS Apache-2.0, GDAL/rasterio MIT/BSD-style, PROJ MIT, NumPy/SciPy BSD).

For a team/hackathon project: Open-Meteo's free tier and Cesium's Community plan are restricted to non-commercial use;
check whether your event or organisation counts as commercial/funded before using them.
