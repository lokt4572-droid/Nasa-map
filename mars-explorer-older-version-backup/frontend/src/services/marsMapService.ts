/** MARS EXPLORER - Mars Map Service (OpenLayers integration) */
import Map from 'ol/Map';
import View from 'ol/View';
import { fromLonLat, toLonLat, get as getProjection } from 'ol/proj';
import { register } from 'ol/proj/proj4';
import proj4 from 'proj4';
import TileLayer from 'ol/layer/Tile';
import WMTS from 'ol/source/WMTS';
import WMTSTileGrid from 'ol/tilegrid/WMTS';
import { getTopLeft } from 'ol/extent';
import { getWidth } from 'ol/extent';
import { ScaleLine, MousePosition, Zoom, Attribution } from 'ol/control';
import { Coordinate } from '../types';
import { MARS_PROJECTION, MARS_EXTENT, MARS_RESOLUTIONS, MARS_MATRIX_IDS, MARS_TILE_GRID } from '../config/marsProjection';
import { NASA_LAYERS, getLayerConfig, type NasaLayerKey } from '../config/mapLayers';

// Initialize Mars projection
proj4.defs('MARS:4326', '+proj=longlat +a=3396190 +b=3376200 +no_defs +type=crs');
register(proj4);

export interface MapInstance {
  map: Map;
  view: View;
  baseLayers: Map<string, TileLayer<WMTS>>;
  overlayLayers: Map<string, TileLayer<WMTS>>;
}

let mapInstance: MapInstance | null = null;

export function createMarsMap(target: string | HTMLElement): MapInstance {
  if (mapInstance) {
    return mapInstance;
  }

  const view = new View({
    projection: MARS_PROJECTION,
    center: fromLonLat([0, 0], MARS_PROJECTION),
    zoom: 2,
    minZoom: 0,
    maxZoom: 18,
    extent: MARS_EXTENT,
    constrainResolution: true,
  });

  const baseLayers = new Map<string, TileLayer<WMTS>>();
  const overlayLayers = new Map<string, TileLayer<WMTS>>();

  // Create NASA WMTS layers
  NASA_LAYERS.forEach((layerMeta) => {
    const config = getLayerConfig(layerMeta.key);
    if (!config) return;

    const source = new WMTS({
      url: config.url,
      layer: config.layerId,
      matrixSet: config.matrixSet,
      format: config.format,
      style: config.style,
      projection: MARS_PROJECTION,
      tileGrid: MARS_TILE_GRID,
      attributions: config.attribution,
      requestEncoding: 'REST',
    });

    const layer = new TileLayer({
      source,
      opacity: config.opacity,
      visible: config.visible,
      zIndex: config.zIndex,
      properties: {
        id: config.id,
        name: config.name,
        type: config.type,
        layerMeta: layerMeta,
      },
    });

    if (config.isBaseLayer) {
      baseLayers.set(config.id, layer);
    } else {
      overlayLayers.set(config.id, layer);
    }
  });

  const map = new Map({
    target,
    view,
    layers: [
      ...Array.from(baseLayers.values()),
      ...Array.from(overlayLayers.values()),
    ],
    controls: [
      new Zoom(),
      new ScaleLine({ units: 'metric', minWidth: 100 }),
      new MousePosition({
        coordinateFormat: (coord) => formatMarsCoordinate(coord),
        projection: MARS_PROJECTION,
        className: 'ol-mouse-position',
        target: undefined,
      }),
      new Attribution({ collapsible: true }),
    ],
  });

  mapInstance = { map, view, baseLayers, overlayLayers };
  return mapInstance;
}

export function getMapInstance(): MapInstance | null {
  return mapInstance;
}

export function destroyMap(): void {
  if (mapInstance) {
    mapInstance.map.setTarget(null);
    mapInstance = null;
  }
}

// Layer management
export function setBaseLayer(layerId: string): boolean {
  if (!mapInstance) return false;
  
  mapInstance.baseLayers.forEach((layer, id) => {
    layer.setVisible(id === layerId);
  });
  return true;
}

export function toggleOverlayLayer(layerId: string, visible?: boolean): boolean {
  if (!mapInstance) return false;
  
  const layer = mapInstance.overlayLayers.get(layerId);
  if (!layer) return false;
  
  layer.setVisible(visible ?? !layer.getVisible());
  return true;
}

export function setLayerOpacity(layerId: string, opacity: number): boolean {
  if (!mapInstance) return false;
  
  const layer = mapInstance.baseLayers.get(layerId) || mapInstance.overlayLayers.get(layerId);
  if (!layer) return false;
  
  layer.setOpacity(Math.max(0, Math.min(1, opacity)));
  return true;
}

export function setLayerZIndex(layerId: string, zIndex: number): boolean {
  if (!mapInstance) return false;
  
  const layer = mapInstance.baseLayers.get(layerId) || mapInstance.overlayLayers.get(layerId);
  if (!layer) return false;
  
  layer.setZIndex(zIndex);
  return true;
}

// View control
export function animateTo(coordinate: Coordinate, zoom?: number, duration = 1000): void {
  if (!mapInstance) return;
  
  const center = fromLonLat([coordinate.longitude, coordinate.latitude], MARS_PROJECTION);
  mapInstance.view.animate({
    center,
    zoom: zoom ?? mapInstance.view.getZoom(),
    duration,
  });
}

export function fitToExtent(extent: [number, number, number, number], padding = 50): void {
  if (!mapInstance) return;
  
  const marsExtent = [
    fromLonLat([extent[0], extent[1]], MARS_PROJECTION),
    fromLonLat([extent[2], extent[3]], MARS_PROJECTION),
  ];
  
  mapInstance.view.fit(marsExtent, { padding, duration: 1000 });
}

export function getCurrentCenter(): Coordinate {
  if (!mapInstance) return { longitude: 0, latitude: 0 };
  
  const center = mapInstance.view.getCenter();
  if (!center) return { longitude: 0, latitude: 0 };
  
  const [lon, lat] = toLonLat(center, MARS_PROJECTION);
  return { longitude: lon, latitude: lat };
}

export function getCurrentZoom(): number {
  return mapInstance?.view.getZoom() ?? 0;
}

export function getCurrentResolution(): number {
  return mapInstance?.view.getResolution() ?? 0;
}

// Coordinate formatting
export function formatMarsCoordinate(coord: number[]): string {
  const [lon, lat] = toLonLat(coord, MARS_PROJECTION);
  return formatDMS(lon, lat);
}

export function formatDMS(longitude: number, latitude: number): string {
  const formatCoord = (val: number, isLat: boolean): string => {
    const abs = Math.abs(val);
    const deg = Math.floor(abs);
    const min = Math.floor((abs - deg) * 60);
    const sec = ((abs - deg - min / 60) * 3600).toFixed(1);
    const dir = isLat ? (val >= 0 ? 'N' : 'S') : (val >= 0 ? 'E' : 'W');
    return `${deg}°${min.toString().padStart(2, '0')}'${sec.padStart(4, '0')}"${dir}`;
  };
  
  return `${formatCoord(latitude, true)} ${formatCoord(longitude, false)}`;
}

export function formatDD(longitude: number, latitude: number, precision = 6): string {
  return `${latitude.toFixed(precision)}°, ${longitude.toFixed(precision)}°`;
}

export function parseCoordinate(input: string): Coordinate | null {
  // Try DD format first
  const ddMatch = input.match(/([+-]?\d+\.?\d*)[°,]\s*([+-]?\d+\.?\d*)/);
  if (ddMatch) {
    return { longitude: parseFloat(ddMatch[2]), latitude: parseFloat(ddMatch[1]) };
  }
  
  // Try DMS format
  const dmsMatch = input.match(/(\d+)°(\d+)'([\d.]+)"([NS])\s*(\d+)°(\d+)'([\d.]+)"([EW])/);
  if (dmsMatch) {
    const lat = parseFloat(dmsMatch[1]) + parseFloat(dmsMatch[2]) / 60 + parseFloat(dmsMatch[3]) / 3600;
    const lon = parseFloat(dmsMatch[5]) + parseFloat(dmsMatch[6]) / 60 + parseFloat(dmsMatch[7]) / 3600;
    return {
      longitude: dmsMatch[8] === 'W' ? -lon : lon,
      latitude: dmsMatch[4] === 'S' ? -lat : lat,
    };
  }
  
  return null;
}

// Distance measurement
export function measureDistance(coords: Coordinate[]): number {
  if (coords.length < 2) return 0;
  
  let total = 0;
  for (let i = 1; i < coords.length; i++) {
    const c1 = fromLonLat([coords[i - 1].longitude, coords[i - 1].latitude], MARS_PROJECTION);
    const c2 = fromLonLat([coords[i].longitude, coords[i].latitude], MARS_PROJECTION);
    const dx = c2[0] - c1[0];
    const dy = c2[1] - c1[1];
    total += Math.sqrt(dx * dx + dy * dy);
  }
  
  return total / 1000; // Convert to km
}

// Export current map state
export function exportMapState() {
  if (!mapInstance) return null;
  
  return {
    center: getCurrentCenter(),
    zoom: getCurrentZoom(),
    rotation: mapInstance.view.getRotation(),
    baseLayer: Array.from(mapInstance.baseLayers.entries()).find(([, l]) => l.getVisible())?.[0],
    overlays: Array.from(mapInstance.overlayLayers.entries())
      .filter(([, l]) => l.getVisible())
      .map(([id]) => id),
  };
}

// Import map state
export function importMapState(state: ReturnType<typeof exportMapState>): void {
  if (!mapInstance || !state) return;
  
  animateTo(state.center, state.zoom);
  
  if (state.baseLayer) {
    setBaseLayer(state.baseLayer);
  }
  
  mapInstance.overlayLayers.forEach((layer, id) => {
    layer.setVisible(state.overlays.includes(id));
  });
}
