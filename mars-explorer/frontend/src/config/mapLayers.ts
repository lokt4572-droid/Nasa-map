/**
 * Catalog of NASA Mars Trek WMTS layers.
 *
 * Every entry was checked against the layer's live GetCapabilities document on
 * 2026-11-12 (layer identifier, TileMatrixSet, number of TileMatrix levels, format,
 * bounding box, SupportedCRS). Tile grids are NOT copied here: they are always read from
 * GetCapabilities at runtime by marsMapService.ts.
 *
 * To add a layer: append an entry with the exact Trek layer identifier. The map picks it
 * up automatically; no component changes are needed.
 *
 * Source documentation: https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars
 */
import { TREK_DECLARED_CRS } from "./marsProjection";
import type { PlanetId } from "./planetRegistry";

export const TREK_WMTS_BASE: string =
  (import.meta.env.VITE_TREK_WMTS_BASE ?? "").replace(/\/+$/, "") || "https://trek.nasa.gov/tiles/Mars/EQ";

export type LayerCategory = "imagery" | "topography" | "reference";
export type BBox = { west: number; south: number; east: number; north: number };

export interface MarsMapLayer {
  id: string;
  planet: PlanetId;
  name: string;
  description: string;
  source: "NASA_TREK";
  layerId: string;
  capabilitiesUrl?: string;
  resolution?: string;
  category: LayerCategory;
  visible: boolean;
  opacity: number;
  defaultEnabled: boolean;
  // --- extended metadata
  mission: string;
  instrument: string;
  /** What the pixels are. WMTS layers here are always rendered images. */
  dataKind: "COLOR_HILLSHADE" | "ORTHOIMAGE" | "THERMAL_IR_MOSAIC";
  /** Pixels are never numeric elevations for these layers. */
  numericElevation: false;
  coverage: "global" | "regional";
  /** Bounding box from GetCapabilities (degrees, in the declared CRS). */
  bbox: BBox;
  crs: string;
  longitudeConvention: "EAST_POSITIVE_180";
  latitudeConvention: "AS_DECLARED_BY_SOURCE";
  verticalDatum: "NOT_APPLICABLE";
  units: "degrees";
  format: "image/jpeg" | "image/png";
  /** Number of TileMatrix levels in GetCapabilities at verification time (informational). */
  tileMatrixLevelsVerified: number;
  verifiedAt: string;
  notes?: string;
}

const capsUrl = (layerId: string) => `${TREK_WMTS_BASE}/${layerId}/1.0.0/WMTSCapabilities.xml`;

const common = {
  planet: "MARS" as PlanetId,
  source: "NASA_TREK" as const,
  numericElevation: false as const,
  crs: TREK_DECLARED_CRS,
  longitudeConvention: "EAST_POSITIVE_180" as const,
  latitudeConvention: "AS_DECLARED_BY_SOURCE" as const,
  verticalDatum: "NOT_APPLICABLE" as const,
  units: "degrees" as const,
  verifiedAt: "2026-11-12",
};

export const MARS_LAYERS: MarsMapLayer[] = [
  {
    ...common,
    id: "mola-global-clrshade",
    name: "MOLA Global Color Hillshade",
    layerId: "Mars_MGS_MOLA_ClrShade_merge_global_463m",
    capabilitiesUrl: capsUrl("Mars_MGS_MOLA_ClrShade_merge_global_463m"),
    description:
      "Mars Global Surveyor MOLA global colour hillshade. Colour-coded shaded relief for visual interpretation of topography. Colours are a visualization, not numeric elevations.",
    resolution: "463 m/px",
    category: "topography",
    visible: true,
    opacity: 1,
    defaultEnabled: true,
    mission: "Mars Global Surveyor",
    instrument: "MOLA",
    dataKind: "COLOR_HILLSHADE",
    coverage: "global",
    bbox: { west: -180, south: -89.9991635, east: 179.9983271, north: 90 },
    format: "image/jpeg",
    tileMatrixLevelsVerified: 8,
  },
  {
    ...common,
    id: "mola-hrsc-blend-clrshade",
    name: "MOLA + HRSC Color Hillshade Blend",
    layerId: "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
    capabilitiesUrl: capsUrl("Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw"),
    description:
      "Mars Global Surveyor MOLA and Mars Express HRSC colour hillshade blend for regional relief. Visualization only, not numeric elevations.",
    resolution: "200 m/px",
    category: "topography",
    visible: false,
    opacity: 1,
    defaultEnabled: false,
    mission: "Mars Global Surveyor / Mars Express",
    instrument: "MOLA + HRSC",
    dataKind: "COLOR_HILLSHADE",
    coverage: "global",
    bbox: { west: -180, south: -89.999224, east: 179.9984479, north: 90 },
    format: "image/jpeg",
    tileMatrixLevelsVerified: 9,
  },
  {
    ...common,
    id: "viking-mdim21-color",
    name: "Viking MDIM 2.1 Colorized Mosaic",
    layerId: "Mars_Viking_MDIM21_ClrMosaic_global_232m",
    capabilitiesUrl: capsUrl("Mars_Viking_MDIM21_ClrMosaic_global_232m"),
    description:
      "Viking Orbiter MDIM 2.1 global image mosaic, colorized (USGS). Albedo/surface appearance at 232 m/px; colours are an approximation, not elevation.",
    resolution: "232 m/px",
    category: "imagery",
    visible: false,
    opacity: 1,
    defaultEnabled: false,
    mission: "Viking Orbiter 1 & 2",
    instrument: "Viking VIS (MDIM 2.1)",
    dataKind: "ORTHOIMAGE",
    coverage: "global",
    bbox: { west: -180, south: -90, east: 180, north: 90 },
    format: "image/jpeg",
    tileMatrixLevelsVerified: 10,
    verifiedAt: "2026-11-14",
  },
  {
    ...common,
    id: "themis-day-ir-100m",
    name: "THEMIS Day IR Global Mosaic",
    layerId: "Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12_clon0_ly",
    capabilitiesUrl: capsUrl("Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12_clon0_ly"),
    description:
      "Mars Odyssey THEMIS daytime thermal-infrared global mosaic (v12, 100 m/px). Brightness reflects daytime surface temperature (slope, albedo, thermal inertia), not visible reflectance and not elevation.",
    resolution: "100 m/px",
    category: "imagery",
    visible: false,
    opacity: 1,
    defaultEnabled: false,
    mission: "2001 Mars Odyssey",
    instrument: "THEMIS IR",
    dataKind: "THERMAL_IR_MOSAIC",
    coverage: "global",
    bbox: { west: -179.9999996, south: -89.9162505, east: 179.9986947, north: 89.9169529 },
    format: "image/png",
    tileMatrixLevelsVerified: 11,
    verifiedAt: "2026-11-14",
  },
  {
    ...common,
    id: "jezero-ctx-ortho",
    name: "CTX Jezero Orthomosaic",
    layerId: "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0",
    capabilitiesUrl: capsUrl("JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0"),
    description:
      "MRO Context Camera (CTX) orthomosaic of the Jezero crater region. Image data, not a digital elevation model.",
    resolution: "6 m/px",
    category: "imagery",
    visible: false,
    opacity: 1,
    defaultEnabled: false,
    mission: "Mars Reconnaissance Orbiter",
    instrument: "CTX",
    dataKind: "ORTHOIMAGE",
    coverage: "regional",
    bbox: { west: 77.1604655, south: 18.2110274, east: 77.6991776, north: 18.7211945 },
    format: "image/png",
    tileMatrixLevelsVerified: 14,
  },
  {
    ...common,
    id: "jezero-hirise-ortho",
    name: "HiRISE Jezero Controlled Orthomosaic",
    layerId: "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd",
    capabilitiesUrl: capsUrl("JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd"),
    description:
      "MRO HiRISE controlled orthomosaic of the Jezero crater region. Image data only: RGB/greyscale pixels must never be used as elevations (a HiRISE DTM is a separate product).",
    resolution: "25 cm/px",
    category: "imagery",
    visible: false,
    opacity: 1,
    defaultEnabled: false,
    mission: "Mars Reconnaissance Orbiter",
    instrument: "HiRISE",
    dataKind: "ORTHOIMAGE",
    coverage: "regional",
    bbox: { west: 77.2229331, south: 18.3067994, east: 77.583964, north: 18.669315 },
    format: "image/png",
    tileMatrixLevelsVerified: 18,
  },
];

/** Region shortcuts; extents come from the layer bounding boxes above (GetCapabilities). */
export const JEZERO_REGION_LAYER_ID = "jezero-ctx-ortho";

export function getLayerConfig(id: string): MarsMapLayer {
  const l = ALL_LAYERS.find((x) => x.id === id);
  if (!l) throw new Error(`Unknown map layer ${id}`);
  return l;
}

export function bboxContains(b: BBox, lon: number, lat: number): boolean {
  return lon >= b.west && lon <= b.east && lat >= b.south && lat <= b.north;
}

// ---------------------------------------------------------------------------
// Moon and Mercury (v0.2). Verified against live GetCapabilities on 2026-11-14.
const TREK_TILES = TREK_WMTS_BASE.replace(/\/Mars\/EQ$/, "");
const trekCaps = (body: string, layerId: string) => `${TREK_TILES}/${body}/EQ/${layerId}/1.0.0/WMTSCapabilities.xml`;
const GLOBAL_BBOX: BBox = { west: -180, south: -90, east: 180, north: 90 };

const moonCommon = { ...common, planet: "MOON" as PlanetId, crs: "urn:ogc:def:crs:EPSG::104903", verifiedAt: "2026-11-14" };
const mercuryCommon = { ...common, planet: "MERCURY" as PlanetId, crs: "urn:ogc:def:crs:IAU2000::19900", verifiedAt: "2026-11-14" };

export const MOON_LAYERS: MarsMapLayer[] = [
  {
    ...moonCommon,
    id: "moon-lroc-wac-mosaic",
    name: "LROC WAC Global Mosaic v2",
    layerId: "LRO_WAC_Mosaic_Global_303ppd_v02",
    capabilitiesUrl: trekCaps("Moon", "LRO_WAC_Mosaic_Global_303ppd_v02"),
    description: "LRO Wide Angle Camera global image mosaic (303 px/deg, ≈100 m/px at the equator). Image data, not elevation.",
    resolution: "303 px/deg (≈100 m/px)",
    category: "imagery",
    visible: true,
    opacity: 1,
    defaultEnabled: true,
    mission: "Lunar Reconnaissance Orbiter",
    instrument: "LROC WAC",
    dataKind: "ORTHOIMAGE",
    coverage: "global",
    bbox: GLOBAL_BBOX,
    format: "image/jpeg",
    tileMatrixLevelsVerified: 9,
  },
  {
    ...moonCommon,
    id: "moon-lola-clrshade",
    name: "LOLA Color Hillshade v4",
    layerId: "LRO_LOLA_ClrShade_Global_128ppd_v04",
    capabilitiesUrl: trekCaps("Moon", "LRO_LOLA_ClrShade_Global_128ppd_v04"),
    description: "LRO LOLA laser-altimetry DEM shown as colour hillshade (128 px/deg ≈ 237 m/px). Colours are a visualization, not elevation values.",
    resolution: "128 px/deg (≈237 m/px)",
    category: "topography",
    visible: false,
    opacity: 1,
    defaultEnabled: false,
    mission: "Lunar Reconnaissance Orbiter",
    instrument: "LOLA",
    dataKind: "COLOR_HILLSHADE",
    coverage: "global",
    bbox: GLOBAL_BBOX,
    format: "image/png",
    tileMatrixLevelsVerified: 6,
  },
];

export const MERCURY_LAYERS: MarsMapLayer[] = [
  {
    ...mercuryCommon,
    id: "mercury-mdis-mosaic",
    name: "MESSENGER MDIS Global Mosaic (2013)",
    layerId: "Mercury_MESSENGER_mosaic_global_250m_2013",
    capabilitiesUrl: trekCaps("Mercury", "Mercury_MESSENGER_mosaic_global_250m_2013"),
    description: "MESSENGER MDIS global image mosaic, 250 m/px. Image data, not elevation.",
    resolution: "250 m/px",
    category: "imagery",
    visible: true,
    opacity: 1,
    defaultEnabled: true,
    mission: "MESSENGER",
    instrument: "MDIS",
    dataKind: "ORTHOIMAGE",
    coverage: "global",
    bbox: { west: -180, south: -89.9999824, east: 179.9999648, north: 90 },
    format: "image/png",
    tileMatrixLevelsVerified: 8,
  },
  {
    ...mercuryCommon,
    id: "mercury-usgs-dem-clrshade",
    name: "USGS MESSENGER DEM 665 m — Color Hillshade",
    layerId: "Mercury_Messenger_USGS_DEM_665m_v2_HillshadeColor",
    capabilitiesUrl: trekCaps("Mercury", "Mercury_Messenger_USGS_DEM_665m_v2_HillshadeColor"),
    description: "Colour hillshade of the USGS global MESSENGER DEM (≈665 m/px). Low-detail topography; colours are not elevation values.",
    resolution: "665 m/px (low detail)",
    category: "topography",
    visible: false,
    opacity: 1,
    defaultEnabled: false,
    mission: "MESSENGER",
    instrument: "MDIS stereo (USGS DEM)",
    dataKind: "COLOR_HILLSHADE",
    coverage: "global",
    bbox: GLOBAL_BBOX,
    format: "image/png",
    tileMatrixLevelsVerified: 6,
  },
];

/** Every Trek layer of every body. Layer ids are unique across bodies. */
export const ALL_LAYERS: MarsMapLayer[] = [...MARS_LAYERS, ...MOON_LAYERS, ...MERCURY_LAYERS];

export function layersForPlanet(planet: PlanetId): MarsMapLayer[] {
  return ALL_LAYERS.filter((l) => l.planet === planet);
}
