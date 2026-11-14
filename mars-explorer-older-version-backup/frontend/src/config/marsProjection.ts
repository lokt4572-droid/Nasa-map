/** MARS EXPLORER - Mars Projection Configuration (OpenLayers) */
import proj4 from 'proj4';
import { register } from 'ol/proj/proj4';
import { Projection } from 'ol/proj';
import { createXYZ, TileGrid } from 'ol/tilegrid';

// Register Mars projection (IAU 2000 spheroid)
// Semi-major axis: 3396.19 km, Semi-minor axis: 3376.20 km
proj4.defs('MARS:4326', '+proj=longlat +a=3396190 +b=3376200 +no_defs +type=crs');
register(proj4);

export const MARS_PROJECTION = new Projection({
  code: 'MARS:4326',
  units: 'degrees',
  axisOrientation: 'enu',
  global: true,
  extent: [-180, -90, 180, 90],
  metersPerUnit: Math.PI * 3396190 / 180, // equatorial circumference / 360
});

// Mars extent in projection coordinates
export const MARS_EXTENT = [-180, -90, 180, 90];

// Resolutions for each zoom level (degrees per pixel)
// Zoom 0: ~1.4 degrees/pixel, Zoom 18: ~0.000005 degrees/pixel
export const MARS_RESOLUTIONS = Array.from({ length: 19 }, (_, z) => 360 / (256 * Math.pow(2, z)));

// Matrix IDs for WMTS (matching resolutions)
export const MARS_MATRIX_IDS = MARS_RESOLUTIONS.map((_, z) => `${z}`);

// WMTS TileGrid for Mars (matches NASA Mars Trek)
export const MARS_TILE_GRID = new WMTSTileGrid({
  origin: getTopLeft(MARS_EXTENT),
  resolutions: MARS_RESOLUTIONS,
  matrixIds: MARS_MATRIX_IDS,
  tileSize: [256, 256],
});

// Helper: get resolution at zoom
export function getResolutionAtZoom(zoom: number): number {
  if (zoom < 0 || zoom >= MARS_RESOLUTIONS.length) return MARS_RESOLUTIONS[0];
  return MARS_RESOLUTIONS[zoom];
}

// Helper: get zoom for resolution
export function getZoomForResolution(resolution: number): number {
  const idx = MARS_RESOLUTIONS.findIndex(r => r <= resolution);
  return idx >= 0 ? idx : MARS_RESOLUTIONS.length - 1;
}

// Convert meters to degrees at latitude
export function metersToDegreesAtLat(meters: number, latitude: number): number {
  const latRad = (latitude * Math.PI) / 180;
  const radiusAtLat = 3396190 * Math.cos(latRad); // equatorial radius * cos(lat)
  return (meters / (2 * Math.PI * radiusAtLat)) * 360;
}

// Convert degrees to meters at latitude
export function degreesToMetersAtLat(degrees: number, latitude: number): number {
  const latRad = (latitude * Math.PI) / 180;
  const radiusAtLat = 3396190 * Math.cos(latRad);
  return (degrees / 360) * (2 * Math.PI * radiusAtLat);
}

// Scale denominator for a given zoom (for printing)
export function getScaleDenominator(zoom: number, dpi = 96): number {
  const resolution = getResolutionAtZoom(zoom); // degrees/pixel
  const metersPerPixel = resolution * (Math.PI * 3396190 / 180) * 1000; // m/px
  return metersPerPixel * dpi / 0.0254; // standard scale formula
}
