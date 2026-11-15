/**
 * Planet-specific coordinate helpers shared by the 3D scenes. Pure functions (unit-tested).
 *
 * Latitude types: a 3D engine working on an ellipsoid reports GEODETIC (planetographic)
 * latitude — the angle of the surface normal. Most planetary rasters (MOLA, USGS DTMs) use
 * PLANETOCENTRIC latitude — the angle at the body centre. On a sphere (Moon) they are equal;
 * on Mars they differ by up to 0.34 degrees (about 20 km on the ground).
 */
export interface BodyShape {
  /** Equatorial radius, metres. */
  a: number;
  /** Polar radius, metres. */
  b: number;
}

const RAD = Math.PI / 180;

/** Planetographic (geodetic) latitude -> planetocentric latitude, degrees. */
export function geodeticToCentric(latDeg: number, shape: BodyShape): number {
  if (Math.abs(latDeg) >= 90) return Math.sign(latDeg) * 90;
  const k = (shape.b * shape.b) / (shape.a * shape.a);
  return Math.atan(k * Math.tan(latDeg * RAD)) / RAD;
}

/** Planetocentric latitude -> planetographic (geodetic) latitude, degrees. */
export function centricToGeodetic(latDeg: number, shape: BodyShape): number {
  if (Math.abs(latDeg) >= 90) return Math.sign(latDeg) * 90;
  const k = (shape.a * shape.a) / (shape.b * shape.b);
  return Math.atan(k * Math.tan(latDeg * RAD)) / RAD;
}

/** Longitude wrapped to -180..180 (180 maps to -180). */
export function wrapLon180(lon: number): number {
  return ((((lon + 180) % 360) + 360) % 360) - 180;
}

/** Longitude wrapped to 0..360. */
export function wrapLon360(lon: number): number {
  return ((lon % 360) + 360) % 360;
}

/** Shortest signed longitude difference b - a, degrees, in -180..180. */
export function lonDelta(a: number, b: number): number {
  return wrapLon180(b - a);
}

/**
 * Local east/north offsets in metres of a point from a reference, on a sphere of the body's
 * mean radius at that latitude (local tangent approximation; good for patches of a few 100 km,
 * handles the longitude seam, not meant for the poles).
 */
export function localOffsetMeters(ref: { lon: number; lat: number }, p: { lon: number; lat: number }, radius: number): { east: number; north: number } {
  return {
    east: lonDelta(ref.lon, p.lon) * RAD * radius * Math.cos(ref.lat * RAD),
    north: (p.lat - ref.lat) * RAD * radius,
  };
}

/** Great-circle distance on a sphere, metres (haversine). */
export function sphereDistance(a: { lon: number; lat: number }, b: { lon: number; lat: number }, radius: number): number {
  const dLat = (b.lat - a.lat) * RAD;
  const dLon = lonDelta(a.lon, b.lon) * RAD;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * RAD) * Math.cos(b.lat * RAD) * Math.sin(dLon / 2) ** 2;
  return 2 * radius * Math.asin(Math.min(1, Math.sqrt(h)));
}

/**
 * Split a lon/lat line where it jumps across the map seam, so a 2D map never draws a segment
 * across the whole world. Input longitudes may be in any range; output is in -180..180 with the
 * crossing point interpolated on both sides.
 */
export function splitAtSeam(line: [number, number][]): [number, number][][] {
  const parts: [number, number][][] = [];
  let cur: [number, number][] = [];
  for (let i = 0; i < line.length; i++) {
    const lon = wrapLon180(line[i]![0]);
    const lat = line[i]![1];
    const prev = cur[cur.length - 1];
    if (prev && Math.abs(lon - prev[0]) > 180) {
      const dir = lon < prev[0] ? 1 : -1; // +1: crossing +180 eastwards
      const span = lon + dir * 360 - prev[0];
      const t = span === 0 ? 0 : (dir * 180 - prev[0]) / span;
      const latX = prev[1] + t * (lat - prev[1]);
      cur.push([dir * 180, latX]);
      parts.push(cur);
      cur = [[-dir * 180, latX]];
    }
    cur.push([lon, lat]);
  }
  if (cur.length) parts.push(cur);
  return parts;
}
