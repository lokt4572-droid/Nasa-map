/** MARS EXPLORER - NASA Mars Trek Layer Configuration */
import type { NasaLayerMeta } from '../types';

// NASA Mars Trek WMTS layers (from project specification)
export const NASA_LAYERS: NasaLayerMeta[] = [
  {
    key: 'mola_global',
    name: 'MOLA Global Color Hillshade',
    description: 'Mars Global Surveyor MOLA Global Color Hillshade (463m/px)',
    type: 'hillshade',
    identifier: 'Mars_MGS_MOLA_ClrShade_merge_global_463m',
    resolutionM: 463,
    coverage: 'global',
    attribution: 'NASA/USGS',
    wmtsUrl: 'https://trek.nasa.gov/tiles/mars/{TileMatrix}/{TileCol}/{TileRow}.png',
    wmtsLayerId: 'Mars_MGS_MOLA_ClrShade_merge_global_463m',
    wmtsStyle: 'default',
    wmtsFormat: 'image/png',
  },
  {
    key: 'hrsc_mola_blend',
    name: 'HRSC + MOLA Blend',
    description: 'MOLA and HRSC Color Hillshade Blend (200m/px)',
    type: 'hillshade',
    identifier: 'Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw',
    resolutionM: 200,
    coverage: 'regional',
    attribution: 'NASA/ESA/DLR/FU Berlin',
    wmtsUrl: 'https://trek.nasa.gov/tiles/mars/{TileMatrix}/{TileCol}/{TileRow}.png',
    wmtsLayerId: 'Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw',
    wmtsStyle: 'default',
    wmtsFormat: 'image/png',
  },
  {
    key: 'hirise_jezero',
    name: 'HiRISE Jezero Orthomosaic',
    description: 'MRO HiRISE Jezero Controlled Orthomosaic (25cm/px)',
    type: 'orthoimage',
    identifier: 'JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd',
    resolutionM: 0.25,
    coverage: {
      west: 77.2229331,
      south: 18.3067994,
      east: 77.583964,
      north: 18.669315,
    },
    attribution: 'NASA/JPL-Caltech/University of Arizona',
    wmtsUrl: 'https://trek.nasa.gov/tiles/mars/{TileMatrix}/{TileCol}/{TileRow}.png',
    wmtsLayerId: 'JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd',
    wmtsStyle: 'default',
    wmtsFormat: 'image/png',
  },
];

export interface LayerUIConfig {
  id: string;
  name: string;
  type: 'wmts' | 'xyz' | 'geojson';
  url: string;
  layerId: string;
  matrixSet: string;
  style: string;
  format: string;
  attribution: string;
  opacity: number;
  visible: boolean;
  zIndex: number;
  minZoom: number;
  maxZoom: number;
  isBaseLayer: boolean;
  layerMeta: NasaLayerMeta;
}

export function getLayerConfig(key: string): LayerUIConfig | undefined {
  const meta = NASA_LAYERS.find(l => l.key === key);
  if (!meta) return undefined;

  const isBase = meta.type === 'hillshade' || meta.type === 'orthoimage';

  return {
    id: `nasa_${key}`,
    name: meta.name,
    type: 'wmts',
    url: meta.wmtsUrl,
    layerId: meta.identifier,
    matrixSet: 'Mars_Equirectangular',
    style: meta.wmtsStyle,
    format: meta.wmtsFormat,
    attribution: meta.attribution,
    opacity: isBase ? 1.0 : 0.8,
    visible: isBase,
    zIndex: isBase ? 10 : 20,
    minZoom: 0,
    maxZoom: 18,
    isBaseLayer: isBase,
    layerMeta: meta,
  };
}

export function getBaseLayerConfigs(): LayerUIConfig[] {
  return NASA_LAYERS
    .filter(l => l.type === 'hillshade' || l.type === 'orthoimage')
    .map(l => getLayerConfig(l.key)!)
    .filter(Boolean);
}

export function getOverlayLayerConfigs(): LayerUIConfig[] {
  return NASA_LAYERS
    .filter(l => l.type !== 'hillshade' && l.type !== 'orthoimage')
    .map(l => getLayerConfig(l.key)!)
    .filter(Boolean);
}
