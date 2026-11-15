/**
 * Global textures for the 3D globes (Phase 3). Every source was checked live on 2026-11-14.
 *
 * All sources are equirectangular (simple cylindrical, lon -180..180, lat -90..90), so they map
 * onto the ellipsoid by longitude/latitude directly — no Web Mercator stretching anywhere.
 * Textures are built at runtime from these services (low resolution first, then finer) and are
 * cached by the browser's HTTP cache only; no imagery is stored in Git.
 */
import type { PlanetId } from "./planetRegistry";

export type TextureSource =
  | {
      kind: "TREK_WMTS";
      /** GetCapabilities of the layer: the tile grid is read from it, never hard-coded. */
      capabilitiesUrl: string;
      layerId: string;
      crs: string;
      /** Tile matrix levels to load, coarse first (level L of a Trek grid is 2^(L+1) x 2^L tiles). */
      levels: number[];
    }
  | {
      kind: "WMS_GETMAP";
      /** One equirectangular GetMap per size, smallest first. */
      urls: { width: number; height: number; url: string }[];
    };

export interface PlanetTexture {
  planet: PlanetId;
  title: string;
  source: TextureSource;
  instrument: string;
  projection: string;
  /** Latitude used to place texture rows on the ellipsoid. */
  latitude: "GEODETIC" | "SPHERE";
  nativeResolution: string;
  globeResolution: string;
  date: string;
  coverage: string;
  attribution: string;
  sourceUrl: string;
  notes: string;
  verifiedAt: string;
}

const TREK = "https://trek.nasa.gov/tiles";
const caps = (body: string, id: string) => `${TREK}/${body}/EQ/${id}/1.0.0/WMTSCapabilities.xml`;
const gibs = (w: number, h: number) =>
  "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.3.0" +
  `&LAYERS=BlueMarble_NextGeneration&STYLES=&CRS=EPSG:4326&BBOX=-90,-180,90,180&WIDTH=${w}&HEIGHT=${h}&FORMAT=image/jpeg`;

export const PLANET_TEXTURES: Partial<Record<PlanetId, PlanetTexture>> = {
  MARS: {
    planet: "MARS",
    title: "Viking MDIM 2.1 colorized global mosaic",
    source: {
      kind: "TREK_WMTS",
      capabilitiesUrl: caps("Mars", "Mars_Viking_MDIM21_ClrMosaic_global_232m"),
      layerId: "Mars_Viking_MDIM21_ClrMosaic_global_232m",
      crs: "urn:ogc:def:crs:EPSG::104905",
      levels: [1, 2],
    },
    instrument: "Viking Orbiter VIS (USGS MDIM 2.1, colorized)",
    projection: "Equirectangular, GCS_Mars_2000 (EPSG::104905 as declared by NASA Trek)",
    latitude: "GEODETIC",
    nativeResolution: "232 m/px",
    globeResolution: "2048 × 1024 px (≈10 km/px at the equator)",
    date: "Viking 1976–1980 imagery; MDIM 2.1 mosaic (USGS)",
    coverage: "Global",
    attribution: "NASA / JPL / USGS — Viking MDIM 2.1, via NASA Mars Trek",
    sourceUrl: "https://trek.nasa.gov/mars/",
    notes:
      "Colours are a colorization of Viking imagery, not true colour. NASA Trek does not state whether latitudes are planetocentric; rows are placed with the geodetic latitude of the declared Mars 2000 ellipsoid (max. difference to planetocentric ≈0.34° at 45°).",
    verifiedAt: "2026-11-14",
  },
  MOON: {
    planet: "MOON",
    title: "LRO WAC global mosaic v2",
    source: {
      kind: "TREK_WMTS",
      capabilitiesUrl: caps("Moon", "LRO_WAC_Mosaic_Global_303ppd_v02"),
      layerId: "LRO_WAC_Mosaic_Global_303ppd_v02",
      crs: "urn:ogc:def:crs:EPSG::104903",
      levels: [1, 2],
    },
    instrument: "LRO Wide Angle Camera",
    projection: "Equirectangular, Moon 2000 sphere (EPSG::104903)",
    latitude: "SPHERE",
    nativeResolution: "303 px/deg (≈100 m/px)",
    globeResolution: "2048 × 1024 px (≈5.3 km/px at the equator)",
    date: "LRO WAC 2009–2011, mosaic v2",
    coverage: "Global",
    attribution: "NASA / GSFC / Arizona State University — LROC WAC, via NASA Moon Trek",
    sourceUrl: "https://trek.nasa.gov/moon/",
    notes: "Greyscale reflectance image, not elevation.",
    verifiedAt: "2026-11-14",
  },
  MERCURY: {
    planet: "MERCURY",
    title: "MESSENGER MDIS enhanced-colour global mosaic",
    source: {
      kind: "TREK_WMTS",
      capabilitiesUrl: caps("Mercury", "Mercury_MESSENGER_MDIS_Basemap_EnhancedColor_Mosaic_Global_665m"),
      layerId: "Mercury_MESSENGER_MDIS_Basemap_EnhancedColor_Mosaic_Global_665m",
      crs: "urn:ogc:def:crs:IAU2000::19900",
      levels: [1, 2],
    },
    instrument: "MESSENGER MDIS (WAC colour filters)",
    projection: "Equirectangular, Mercury sphere (IAU2000:19900)",
    latitude: "SPHERE",
    nativeResolution: "665 m/px",
    globeResolution: "2048 × 1024 px (≈7.5 km/px at the equator)",
    date: "MESSENGER 2011–2015",
    coverage: "Global",
    attribution: "NASA / JHU APL / Carnegie Institution of Washington — MESSENGER MDIS, via NASA Mercury Trek",
    sourceUrl: "https://trek.nasa.gov/mercury/",
    notes: "Enhanced colour: band ratios that emphasise compositional differences. Not what the eye would see.",
    verifiedAt: "2026-11-14",
  },
  EARTH: {
    planet: "EARTH",
    title: "Blue Marble: Next Generation",
    source: {
      kind: "WMS_GETMAP",
      urls: [
        { width: 1024, height: 512, url: gibs(1024, 512) },
        { width: 2048, height: 1024, url: gibs(2048, 1024) },
      ],
    },
    instrument: "Terra/Aqua MODIS composite",
    projection: "Equirectangular, WGS 84 (EPSG:4326)",
    latitude: "GEODETIC",
    nativeResolution: "500 m/px",
    globeResolution: "2048 × 1024 px (≈20 km/px at the equator)",
    date: "2004 monthly composite (cloud-free)",
    coverage: "Global",
    attribution: "NASA Earth Observatory / NASA GIBS",
    sourceUrl: "https://earthdata.nasa.gov/gibs",
    notes: "Cloud-free composite, not current conditions. Terrain relief for Earth is the separate Cesium 3D view.",
    verifiedAt: "2026-11-14",
  },
  // VENUS: no verified global colour/radar texture service with CORS → no globe (see Venus preview).
};

export function textureFor(planet: PlanetId): PlanetTexture | null {
  return PLANET_TEXTURES[planet] ?? null;
}
