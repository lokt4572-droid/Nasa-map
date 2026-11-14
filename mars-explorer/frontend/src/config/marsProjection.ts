/**
 * Mars coordinate reference systems for the map.
 *
 * NASA Mars Trek "EQ" WMTS layers declare their CRS as `urn:ogc:def:crs:EPSG::104905`
 * (checked in GetCapabilities on 2026-11-12). The code 104905 does not exist in the EPSG
 * registry; in the PROJ database it is `ESRI:104905` (GCS_Mars_2000):
 *   +proj=longlat +a=3396190 +rf=169.894447223612
 * We register the service's identifier *exactly as written* with those parameters, so
 * OpenLayers' `optionsFromCapabilities` can resolve it. This is a documented, explicit
 * interpretation (see docs/COORDINATE_SYSTEM.md), not a silent namespace rewrite.
 *
 * Latitude type: the capabilities document does not state whether the mosaics use
 * planetocentric or planetographic latitude. Map coordinates are therefore labelled
 * "as declared by source" in the UI and in API requests.
 */
import proj4 from "proj4";
import { get as getProjection } from "ol/proj";
import type Projection from "ol/proj/Projection";
import { register } from "ol/proj/proj4";

export const TREK_DECLARED_CRS = "urn:ogc:def:crs:EPSG::104905";
export const MARS_2000_ESRI = "ESRI:104905";
export const MARS_2000_PROJ4 = "+proj=longlat +a=3396190 +rf=169.894447223612 +no_defs +type=crs";

export const MARS_EQUATORIAL_RADIUS_M = 3_396_190;
export const MARS_INVERSE_FLATTENING = 169.894447223612;
export const MARS_FLATTENING = 1 / MARS_INVERSE_FLATTENING;
export const MARS_POLAR_RADIUS_M = MARS_EQUATORIAL_RADIUS_M * (1 - MARS_FLATTENING);
export const MARS_E2 = MARS_FLATTENING * (2 - MARS_FLATTENING);

/** Full geographic extent in degrees: [west, south, east, north]. */
export const MARS_GEOGRAPHIC_EXTENT: [number, number, number, number] = [-180, -90, 180, 90];

export type LatitudeConvention = "PLANETOCENTRIC" | "PLANETOGRAPHIC" | "AS_DECLARED_BY_SOURCE";

/** How coordinates picked on the Trek map are labelled everywhere in the app. */
export const MAP_COORDINATE_CONVENTION = {
  crs: TREK_DECLARED_CRS,
  interpretedAs: MARS_2000_ESRI,
  longitude: "EAST_POSITIVE_180",
  latitude: "AS_DECLARED_BY_SOURCE" as LatitudeConvention,
  units: "degrees",
} as const;

let registered = false;

export function registerMarsProjections(): Projection {
  if (!registered) {
    proj4.defs(MARS_2000_ESRI, MARS_2000_PROJ4);
    proj4.defs(TREK_DECLARED_CRS, MARS_2000_PROJ4);
    register(proj4);
    registered = true;
  }
  for (const code of [MARS_2000_ESRI, TREK_DECLARED_CRS]) {
    const p = getProjection(code);
    if (!p) throw new Error(`Failed to register Mars projection ${code}`);
    p.setExtent(MARS_GEOGRAPHIC_EXTENT);
    p.setWorldExtent(MARS_GEOGRAPHIC_EXTENT);
    p.setGlobal(true);
  }
  const trek = getProjection(TREK_DECLARED_CRS);
  if (!trek) throw new Error("Trek CRS not registered");
  return trek;
}

/** Normalize an east-positive longitude to [-180, 180). */
export function normalizeLon180(lon: number): number {
  if (!Number.isFinite(lon)) throw new RangeError("longitude must be finite");
  const v = ((((lon + 180) % 360) + 360) % 360) - 180;
  return Object.is(v, -0) ? 0 : v;
}

export function lonTo360(lon: number): number {
  return ((lon % 360) + 360) % 360;
}

/** Radius of curvature in the prime vertical, N(φ), Mars 2000 ellipsoid. */
export function primeVerticalRadius(latDeg: number): number {
  const s = Math.sin((latDeg * Math.PI) / 180);
  return MARS_EQUATORIAL_RADIUS_M / Math.sqrt(1 - MARS_E2 * s * s);
}

/** Radius of curvature in the meridian, M(φ), Mars 2000 ellipsoid. */
export function meridionalRadius(latDeg: number): number {
  const s = Math.sin((latDeg * Math.PI) / 180);
  return (MARS_EQUATORIAL_RADIUS_M * (1 - MARS_E2)) / Math.pow(1 - MARS_E2 * s * s, 1.5);
}

/**
 * Ground size of one screen pixel on Mars for a view resolution given in degrees/pixel.
 * East-west size shrinks with cos(latitude). OpenLayers' own ScaleLine assumes an Earth
 * sphere for degree-based projections, so we do not use it.
 */
export function groundResolutionM(resolutionDegPerPx: number, latDeg: number): { ew: number; ns: number } {
  const rad = (resolutionDegPerPx * Math.PI) / 180;
  const lat = Math.max(-89.999, Math.min(89.999, latDeg));
  return {
    ew: rad * primeVerticalRadius(lat) * Math.cos((lat * Math.PI) / 180),
    ns: rad * meridionalRadius(lat),
  };
}

export function formatLat(lat: number, digits = 4): string {
  return `${Math.abs(lat).toFixed(digits)}° ${lat >= 0 ? "N" : "S"}`;
}

export function formatLon(lon: number, mode: "180" | "360" = "180", digits = 4): string {
  if (mode === "360") return `${lonTo360(lon).toFixed(digits)}° E`;
  const v = normalizeLon180(lon);
  return `${Math.abs(v).toFixed(digits)}° ${v >= 0 ? "E" : "W"}`;
}

export function formatDistance(m: number): string {
  if (!Number.isFinite(m)) return "—";
  if (m === 0) return "0 m";
  if (m >= 1000) return `${(m / 1000).toFixed(m >= 100_000 ? 0 : 1)} km`;
  if (m >= 1) return `${m.toFixed(m >= 100 ? 0 : 1)} m`;
  return `${(m * 100).toFixed(0)} cm`;
}

/** Choose a "nice" scale-bar length (1, 2, 5 × 10^n metres) not wider than maxPx. */
export function niceScaleBar(metersPerPx: number, maxPx = 120): { meters: number; px: number } {
  const maxM = metersPerPx * maxPx;
  const pow = Math.pow(10, Math.floor(Math.log10(maxM)));
  const candidates = [5, 2, 1].map((k) => k * pow);
  const meters = candidates.find((c) => c <= maxM) ?? pow;
  return { meters, px: meters / metersPerPx };
}
