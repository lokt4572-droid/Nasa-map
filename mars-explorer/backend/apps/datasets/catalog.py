"""Unified catalog of scientific products and services, per celestial body.

Every entry states where its facts come from. "verified" = checked by this project on the
date given (live service/GetCapabilities or the official page); "from specification" =
taken from the project specification because the official page refused automated access
(USGS Astrogeology returned HTTP 403 on 2026-11-14) — to be confirmed manually.

Status of an entry (computed in catalog_with_status):
  ONLINE_SOURCE     streamed from a public service (WMTS / API), nothing to download
  NOT_DOWNLOADED    downloadable product, no local copy registered
  VALID / INVALID   local copy registered and validated / rejected
  PARTIAL_COVERAGE  valid local copy of a product that does not cover the whole body
  UNAVAILABLE       local copy registered but its file is missing
"""
from __future__ import annotations

from typing import Any

from services import remote_raster

E = dict[str, Any]

CATALOG: list[E] = [
    # ------------------------------------------------------------------ MARS
    {"key": "mars-trek-mola-clrshade", "planet": "MARS", "dataset": "MOLA Global Color Hillshade (Trek WMTS)", "source": "NASA Solar System Treks", "instrument": "MGS MOLA",
     "product_id": "Mars_MGS_MOLA_ClrShade_merge_global_463m", "data_type": "IMAGERY", "resolution": "463 m/px", "spatial_coverage": "global", "temporal_coverage": "MGS mission 1997–2006",
     "crs": "urn:ogc:def:crs:EPSG::104905", "units": "RGB visualization", "vertical_datum": "n/a (image)", "license": "NASA public data", "access": "ONLINE",
     "url": "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars", "purpose": "Global relief context map", "facts": "verified 2026-11-12"},
    {"key": "mars-trek-hirise-jezero", "planet": "MARS", "dataset": "HiRISE Jezero Controlled Orthomosaic (Trek WMTS)", "source": "NASA Solar System Treks", "instrument": "MRO HiRISE",
     "product_id": "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd", "data_type": "IMAGERY", "resolution": "25 cm/px", "spatial_coverage": "regional: Jezero 77.22–77.58°E, 18.31–18.67°N",
     "temporal_coverage": "not stated in capabilities", "crs": "urn:ogc:def:crs:EPSG::104905", "units": "image", "vertical_datum": "n/a (image)", "license": "NASA public data", "access": "ONLINE",
     "url": "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars", "purpose": "Landing-site scale imagery (not a DTM)", "facts": "verified 2026-11-12"},
    {"key": "mars-mola-megdr", "planet": "MARS", "dataset": "MGS MOLA MEGDR topography (PDS4)", "source": "NASA PDS Geosciences Node", "instrument": "MGS MOLA",
     "product_id": "megt* (meg004 … meg128)", "data_type": "DEM", "resolution": "4–128 px/deg (≈14.8 km – 463 m)", "spatial_coverage": "global (polar products separate)", "temporal_coverage": "1997–2001 altimetry",
     "crs": "Equirectangular on 3 396 000 m sphere (from label)", "units": "m", "vertical_datum": "MOLA areoid (GMM3, mgm1025)", "license": "NASA PDS public data", "access": "DOWNLOAD",
     "url": "https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/", "purpose": "Elevation, slope, A* routing", "facts": "verified 2026-11-14 (label read, MD5 checked)",
     "match": {"planet": "MARS", "instrument": "MGS MOLA"}},
    {"key": "mars-hirise-dtm", "planet": "MARS", "dataset": "HiRISE DTMs", "source": "University of Arizona / HiRISE", "instrument": "MRO HiRISE",
     "product_id": "DTEE*/DTEC* per site", "data_type": "DEM", "resolution": "≈1–2 m post spacing (typical)", "spatial_coverage": "regional, only where stereo DTMs exist", "temporal_coverage": "per product",
     "crs": "per product label", "units": "m", "vertical_datum": "per product label", "license": "NASA/UA public data", "access": "DOWNLOAD",
     "url": "https://www.uahirise.org/dtm/", "purpose": "Metre-scale local terrain", "facts": "page read 2026-11-12", "match": {"planet": "MARS", "instrument": "MRO HiRISE"}, "partial": True},
    # ------------------------------------------------------------------ MOON
    {"key": "moon-trek-wac", "planet": "MOON", "dataset": "LROC WAC Global Mosaic v2 (Trek WMTS)", "source": "NASA Solar System Treks", "instrument": "LRO LROC WAC",
     "product_id": "LRO_WAC_Mosaic_Global_303ppd_v02", "data_type": "IMAGERY", "resolution": "303 px/deg (≈100 m/px)", "spatial_coverage": "global", "temporal_coverage": "LRO mission",
     "crs": "urn:ogc:def:crs:EPSG::104903", "units": "image", "vertical_datum": "n/a (image)", "license": "NASA public data", "access": "ONLINE",
     "url": "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=moon", "purpose": "Global lunar basemap", "facts": "verified 2026-11-14"},
    {"key": "moon-usgs-wac-100m", "planet": "MOON", "dataset": "LRO LROC WAC Global Morphology Mosaic 100 m (USGS)", "source": "USGS Astrogeology", "instrument": "LRO LROC WAC",
     "product_id": "moon_lro_lroc_wac_global_morphology_mosaic_100m", "data_type": "IMAGERY", "resolution": "≈100 m/px", "spatial_coverage": "global", "temporal_coverage": "LRO mission",
     "crs": "per product metadata", "units": "image", "vertical_datum": "n/a (image)", "license": "USGS/NASA public data", "access": "DOWNLOAD",
     "url": "https://astrogeology.usgs.gov/search/map/moon_lro_lroc_wac_global_morphology_mosaic_100m", "purpose": "Downloadable lunar mosaic", "facts": "from specification (USGS page HTTP 403 to automated access)"},
    {"key": "moon-gld100", "planet": "MOON", "dataset": "LROC WAC GLD100 DTM", "source": "LROC (Arizona State University)", "instrument": "LRO LROC WAC stereo",
     "product_id": "WAC_GLD100", "data_type": "DEM", "resolution": "100 m/px grid; formal resolution ≈ 300 m; vertical accuracy ≈ 10–20 m", "spatial_coverage": "79°S–79°N (98.2 %); poles need LOLA",
     "temporal_coverage": "LRO mission", "crs": "Equirectangular / Polar Stereographic tiles", "units": "m", "vertical_datum": "not stated on the product page", "license": "NASA PDS public data", "access": "DOWNLOAD",
     "url": "https://data.lroc.im-ldi.com/lroc/view_rdr/WAC_GLD100", "purpose": "Lunar elevation", "facts": "page read 2026-11-14", "match": {"planet": "MOON", "instrument": "LRO LROC WAC stereo"}, "partial": True},
    {"key": "moon-lola", "planet": "MOON", "dataset": "LOLA DEM (via Trek colour hillshade; DEM download from PDS)", "source": "NASA Solar System Treks / PDS", "instrument": "LRO LOLA",
     "product_id": "LRO_LOLA_ClrShade_Global_128ppd_v04", "data_type": "TOPOGRAPHY", "resolution": "128 px/deg (≈237 m)", "spatial_coverage": "global incl. poles", "temporal_coverage": "LRO mission",
     "crs": "urn:ogc:def:crs:EPSG::104903", "units": "RGB visualization", "vertical_datum": "n/a (visualization)", "license": "NASA public data", "access": "ONLINE",
     "url": "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=moon", "purpose": "Polar relief context where GLD100 has no data", "facts": "verified 2026-11-14"},
    # ------------------------------------------------------------------ MERCURY
    {"key": "mercury-trek-mdis", "planet": "MERCURY", "dataset": "MESSENGER MDIS Global Mosaic 2013 (Trek WMTS)", "source": "NASA Solar System Treks", "instrument": "MESSENGER MDIS",
     "product_id": "Mercury_MESSENGER_mosaic_global_250m_2013", "data_type": "IMAGERY", "resolution": "250 m/px", "spatial_coverage": "global", "temporal_coverage": "MESSENGER 2011–2015",
     "crs": "urn:ogc:def:crs:IAU2000::19900", "units": "image", "vertical_datum": "n/a (image)", "license": "NASA public data", "access": "ONLINE",
     "url": "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mercury", "purpose": "Global basemap", "facts": "verified 2026-11-14"},
    {"key": "mercury-usgs-dem-665m", "planet": "MERCURY", "dataset": "USGS MESSENGER Global DEM 665 m", "source": "USGS Astrogeology", "instrument": "MESSENGER MDIS stereo",
     "product_id": "mercury_messenger_global_dem_665m", "data_type": "DEM", "resolution": "≈665.24 m/px (low detail)", "spatial_coverage": "global, lat −90..90, lon 0..360",
     "temporal_coverage": "MESSENGER mission", "crs": "planetocentric, positive east (per metadata)", "units": "m", "vertical_datum": "relative to reference sphere (per metadata)", "license": "USGS/NASA public data", "access": "DOWNLOAD",
     "url": "https://astrogeology.usgs.gov/search/map/mercury_messenger_global_dem_665m", "purpose": "Low-detail Mercury elevation", "facts": "from specification (USGS page HTTP 403 to automated access)",
     "match": {"planet": "MERCURY"}},
    # ------------------------------------------------------------------ VENUS
    {"key": "venus-gtdr", "planet": "VENUS", "dataset": "Magellan Global Topographic Data Record (GTDR)", "source": "NASA PDS", "instrument": "Magellan altimeter",
     "product_id": "MGN-V-RDRS-5-GDR-TOPOGRAPHIC-V1.0", "data_type": "TOPOGRAPHY", "resolution": "≈5 × 5 km/px", "spatial_coverage": "near-global (Magellan coverage)", "temporal_coverage": "1990–1994",
     "crs": "Sinusoidal / Mercator / polar stereographic", "units": "planetary radius (not height)", "vertical_datum": "radius values — convert before use", "license": "NASA PDS public data", "access": "DOWNLOAD",
     "url": "https://pds.nasa.gov/ds-view/pds/viewDataset.jsp?dsid=MGN-V-RDRS-5-GDR-TOPOGRAPHIC-V1.0", "purpose": "Experimental low-detail topography", "facts": "page read 2026-11-14", "match": {"planet": "VENUS"}},
    # ------------------------------------------------------------------ EARTH
    {"key": "earth-gibs", "planet": "EARTH", "dataset": "NASA GIBS imagery (MODIS, VIIRS, IMERG, …)", "source": "NASA EOSDIS GIBS", "instrument": "MODIS / VIIRS / GPM IMERG / OMI / AMSR2",
     "product_id": "see GIBS layer list", "data_type": "IMAGERY", "resolution": "per layer (≈306 m – 2.4 km per pixel at max zoom)", "spatial_coverage": "global", "temporal_coverage": "per layer, from GetCapabilities",
     "crs": "EPSG:3857", "units": "visualization", "vertical_datum": "n/a", "license": "NASA open data; attribution requested", "access": "ONLINE",
     "url": "https://nasa-gibs.github.io/gibs-api-docs/", "purpose": "Satellite imagery and atmosphere/precipitation views", "facts": "verified 2026-11-14"},
    {"key": "earth-osm", "planet": "EARTH", "dataset": "OpenStreetMap standard tiles", "source": "OpenStreetMap Foundation", "instrument": "—",
     "product_id": "tile.openstreetmap.org", "data_type": "IMAGERY", "resolution": "z0–19", "spatial_coverage": "global", "temporal_coverage": "continuously updated",
     "crs": "EPSG:3857", "units": "map", "vertical_datum": "n/a", "license": "ODbL data; tile usage policy (no bulk/offline download)", "access": "ONLINE",
     "url": "https://operations.osmfoundation.org/policies/tiles/", "purpose": "Street map, borders, roads, names", "facts": "policy read 2026-11-14"},
    {"key": "earth-open-meteo", "planet": "EARTH", "dataset": "Open-Meteo forecast", "source": "Open-Meteo", "instrument": "numerical weather models",
     "product_id": "/v1/forecast", "data_type": "WEATHER", "resolution": "model grid (provider-dependent)", "spatial_coverage": "global", "temporal_coverage": "7-day forecast",
     "crs": "WGS 84", "units": "per variable", "vertical_datum": "n/a", "license": "CC BY 4.0; free tier non-commercial, < 10 000 calls/day", "access": "ONLINE",
     "url": "https://open-meteo.com/en/docs", "purpose": "Point forecast", "facts": "terms read 2026-11-14"},
    {"key": "earth-nasa-power", "planet": "EARTH", "dataset": "NASA POWER daily point data", "source": "NASA LaRC POWER", "instrument": "reanalysis / satellite-derived",
     "product_id": "temporal/daily/point", "data_type": "WEATHER", "resolution": "coarse grid (source-dependent)", "spatial_coverage": "global", "temporal_coverage": "1981-01-01 → near real time",
     "crs": "WGS 84", "units": "per parameter (from response)", "vertical_datum": "n/a", "license": "NASA open data", "access": "ONLINE",
     "url": "https://power.larc.nasa.gov/docs/", "purpose": "Historical daily climate context", "facts": "docs read 2026-11-14"},
    {"key": "earth-copernicus-dem", "planet": "EARTH", "dataset": "Copernicus DEM GLO-30 / GLO-90", "source": "ESA / Copernicus (DLR, Airbus)", "instrument": "TanDEM-X",
     "product_id": "COP-DEM GLO-30, GLO-90", "data_type": "DEM", "resolution": "1″ (≈30 m) / 3″ (≈90 m)", "spatial_coverage": "global land, 1°×1° tiles", "temporal_coverage": "acquired 2011–2015",
     "crs": "WGS84-G1150 (EPSG:4326)", "units": "m", "vertical_datum": "EGM2008 (EPSG:3855)", "license": "free licence (GLO-30/90); attribution required", "access": "DOWNLOAD",
     "url": "https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM",
     "purpose": "Detailed land relief (surface model incl. buildings/vegetation)", "facts": "page read 2026-11-14", "match": {"planet": "EARTH", "instrument": "TanDEM-X"}, "partial": True},
    {"key": "earth-gebco-2026", "planet": "EARTH", "dataset": "GEBCO_2026 Grid + TID Grid", "source": "GEBCO / BODC", "instrument": "compilation (soundings, satellite gravity, DEMs)",
     "product_id": "GEBCO_2026", "data_type": "BATHYMETRY", "resolution": "15 arc-second grid (not equal to accuracy)", "spatial_coverage": "global land + ocean", "temporal_coverage": "2026 release",
     "crs": "WGS 84", "units": "m", "vertical_datum": "mean sea level (with stated exceptions)", "license": "public domain (with GEBCO conditions of use)", "access": "DOWNLOAD",
     "url": "https://www.gebco.net/data-products/gridded-bathymetry-data", "purpose": "Global topography + bathymetry context; not for navigation", "facts": "page read 2026-11-14",
     "match": {"planet": "EARTH", "instrument": "GEBCO"}},
]

TYPES = ["IMAGERY", "DEM", "TOPOGRAPHY", "WEATHER", "GEOLOGY", "BATHYMETRY"]


def _matches(ds, match: dict) -> bool:
    if ds.planet != match.get("planet"):
        return False
    instr = match.get("instrument")
    return instr is None or instr.lower() in (ds.instrument or "").lower()


def catalog_with_status(planet: str | None = None, data_type: str | None = None) -> list[E]:
    from pathlib import Path

    from apps.datasets.models import Dataset

    local = list(Dataset.objects.all())
    out = []
    for e in CATALOG:
        if planet and e["planet"] != planet:
            continue
        if data_type and e["data_type"] != data_type:
            continue
        item = {k: v for k, v in e.items() if k != "match"}
        if e["access"] == "ONLINE":
            item["status"] = "ONLINE_SOURCE"
            item["local_datasets"] = []
        else:
            mine = [d for d in local if _matches(d, e.get("match", {"planet": e["planet"]}))]
            item["local_datasets"] = [{"id": d.id, "name": d.name, "status": d.status} for d in mine]
            if not mine:
                item["status"] = "NOT_DOWNLOADED"
            elif any(d.status == "VALID" and remote_raster.file_available(d.file_path) for d in mine):
                item["status"] = "PARTIAL_COVERAGE" if e.get("partial") else "VALID"
            elif any(d.status == "INVALID" for d in mine):
                item["status"] = "INVALID"
            else:
                item["status"] = "UNAVAILABLE"
        out.append(item)
    return out
