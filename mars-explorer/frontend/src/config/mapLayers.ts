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

export const TREK_WMTS_BASE: string =
  (import.meta.env.VITE_TREK_WMTS_BASE ?? "").replace(/\/+$/, "") || "https://trek.nasa.gov/tiles/Mars/EQ";

export type LayerCategory = "imagery" | "topography" | "reference";
export type BBox = { west: number; south: number; east: number; north: number };

export interface MarsMapLayer {
  id: string;
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
  dataKind: "COLOR_HILLSHADE" | "ORTHOIMAGE";
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
  const l = MARS_LAYERS.find((x) => x.id === id);
  if (!l) throw new Error(`Unknown map layer ${id}`);
  return l;
}

export function bboxContains(b: BBox, lon: number, lat: number): boolean {
  return lon >= b.west && lon <= b.east && lat >= b.south && lat <= b.north;
}
