/**
 * Planet globe geometry and textures (Phase 3).
 *
 * Geometry: a true ellipsoid from the body's radii (registry), not a scaled sphere. Each vertex is
 * placed at (lon, lat) using the latitude convention of the texture, and texture coordinates are
 * linear in lon/lat — the exact layout of an equirectangular image. Picking inverts the same
 * formulas, so a click returns the coordinates of the pixel under the cursor.
 *
 * Axes (units: equatorial radius = 1): +X -> (lon 0, lat 0), +Y -> north pole,
 * -Z -> lon +90 E. Seen from outside with north up, east is to the right.
 *
 * Textures: equirectangular mosaics built from the sources in config/planetTextures.ts, coarse
 * level first. Tile placement comes from the WMTS tile grid read from GetCapabilities. Missing
 * tiles are left transparent and reported — never filled with invented imagery.
 */
import type WMTSTileGrid from "ol/tilegrid/WMTS";

import type { MarsMapLayer } from "../config/mapLayers";
import type { PlanetTexture } from "../config/planetTextures";
import { buildWmtsSource, fetchCapabilities } from "./marsMapService";

export type LatitudeMode = PlanetTexture["latitude"];
const D2R = Math.PI / 180;

/** (lon, lat) in degrees -> position with the equatorial radius = 1. `h` is a height in units of a. */
export function lonLatToXYZ(lonDeg: number, latDeg: number, a: number, b: number, mode: LatitudeMode, h = 0): [number, number, number] {
  const lon = lonDeg * D2R;
  const lat = latDeg * D2R;
  if (mode === "SPHERE" || a === b) {
    const r = 1 + h;
    return [r * Math.cos(lat) * Math.cos(lon), r * Math.sin(lat), -r * Math.cos(lat) * Math.sin(lon)];
  }
  // Geodetic latitude on the ellipsoid (a, b): standard prime-vertical formula.
  const e2 = 1 - (b * b) / (a * a);
  const s = Math.sin(lat);
  const n = 1 / Math.sqrt(1 - e2 * s * s); // N / a
  const xy = (n + h) * Math.cos(lat);
  return [xy * Math.cos(lon), (n * (1 - e2) + h) * s, -xy * Math.sin(lon)];
}

/** Inverse of lonLatToXYZ for a point on the surface (h = 0). */
export function xyzToLonLat(x: number, y: number, z: number, a: number, b: number, mode: LatitudeMode): { lon: number; lat: number } {
  const lon = Math.atan2(-z, x) / D2R;
  const p = Math.hypot(x, z);
  if (mode === "SPHERE" || a === b) return { lon, lat: Math.atan2(y, p) / D2R };
  const e2 = 1 - (b * b) / (a * a);
  return { lon, lat: Math.atan2(y, (1 - e2) * p) / D2R };
}

export interface EllipsoidArrays {
  positions: Float32Array;
  normals: Float32Array;
  uvs: Float32Array;
  indices: Uint32Array;
}

/** Triangulated ellipsoid; vertices duplicated along lon ±180 so the texture seam is exact. */
export function buildEllipsoidArrays(a: number, b: number, mode: LatitudeMode, lonSegments = 256, latSegments = 128): EllipsoidArrays {
  const nV = (lonSegments + 1) * (latSegments + 1);
  const positions = new Float32Array(nV * 3);
  const normals = new Float32Array(nV * 3);
  const uvs = new Float32Array(nV * 2);
  let k = 0;
  for (let j = 0; j <= latSegments; j++) {
    const lat = 90 - (180 * j) / latSegments;
    for (let i = 0; i <= lonSegments; i++) {
      const lon = -180 + (360 * i) / lonSegments;
      const [x, y, z] = lonLatToXYZ(lon, lat, a, b, mode);
      positions.set([x, y, z], k * 3);
      // Surface normal: the geodetic normal (exact for GEODETIC, radial for SPHERE).
      const la = lat * D2R;
      const lo = lon * D2R;
      normals.set([Math.cos(la) * Math.cos(lo), Math.sin(la), -Math.cos(la) * Math.sin(lo)], k * 3);
      uvs.set([(lon + 180) / 360, (lat + 90) / 180], k * 2);
      k++;
    }
  }
  const indices = new Uint32Array(lonSegments * latSegments * 6);
  let t = 0;
  for (let j = 0; j < latSegments; j++) {
    for (let i = 0; i < lonSegments; i++) {
      const p = j * (lonSegments + 1) + i;
      const q = p + lonSegments + 1;
      indices.set([p, q, p + 1, p + 1, q, q + 1], t);
      t += 6;
    }
  }
  return { positions, normals, uvs, indices };
}

/** Graticule polylines every `stepDeg`, lifted slightly above the surface. */
export function graticule(a: number, b: number, mode: LatitudeMode, stepDeg = 30, lift = 0.002): number[][][] {
  const lines: number[][][] = [];
  for (let lat = -90 + stepDeg; lat < 90; lat += stepDeg) {
    const l: number[][] = [];
    for (let lon = -180; lon <= 180; lon += 2) l.push(lonLatToXYZ(lon, lat, a, b, mode, lift));
    lines.push(l);
  }
  for (let lon = -180; lon < 180; lon += stepDeg) {
    const l: number[][] = [];
    for (let lat = -90; lat <= 90; lat += 2) l.push(lonLatToXYZ(lon, lat, a, b, mode, lift));
    lines.push(l);
  }
  return lines;
}

// ---------------------------------------------------------------------------
// Texture mosaics

export interface TilePlacement {
  z: number;
  x: number;
  y: number;
  /** pixel offset of the tile in the equirectangular canvas */
  dx: number;
  dy: number;
}

/**
 * Where each tile of level z goes in a lon -180..180 / lat 90..-90 canvas, from the grid's own
 * origin, resolution and tile size (all read from GetCapabilities).
 */
export function placeTiles(
  z: number,
  origin: [number, number],
  resolutionDeg: number,
  tileSize: number,
  range: { minX: number; maxX: number; minY: number; maxY: number },
): { width: number; height: number; tiles: TilePlacement[] } {
  const width = Math.round(360 / resolutionDeg);
  const height = Math.round(180 / resolutionDeg);
  const tiles: TilePlacement[] = [];
  for (let y = range.minY; y <= range.maxY; y++) {
    for (let x = range.minX; x <= range.maxX; x++) {
      const west = origin[0] + x * tileSize * resolutionDeg;
      const north = origin[1] - y * tileSize * resolutionDeg;
      tiles.push({ z, x, y, dx: Math.round((west + 180) / resolutionDeg), dy: Math.round((90 - north) / resolutionDeg) });
    }
  }
  return { width, height, tiles };
}

export interface TextureLevel {
  canvas: HTMLCanvasElement | OffscreenCanvas;
  width: number;
  height: number;
  tilesTotal: number;
  tilesMissing: number;
  level: string;
}

type ImageLoader = (url: string, signal: AbortSignal) => Promise<CanvasImageSource & { width: number; height: number }>;

async function defaultLoadImage(url: string, signal: AbortSignal) {
  const res = await fetch(url, { signal, mode: "cors", credentials: "omit" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return createImageBitmap(await res.blob());
}

function makeCanvas(w: number, h: number): HTMLCanvasElement | OffscreenCanvas {
  if (typeof OffscreenCanvas !== "undefined") return new OffscreenCanvas(w, h);
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

/** Run `fn` over `items` with at most `limit` in parallel. */
async function pool<T>(items: T[], limit: number, fn: (t: T) => Promise<void>): Promise<void> {
  let i = 0;
  const workers = Array.from({ length: Math.min(limit, items.length) }, async () => {
    while (i < items.length) await fn(items[i++]!);
  });
  await Promise.all(workers);
}

/**
 * Build the texture level by level (coarse first). `onLevel` is called with each finished level so
 * the globe shows something quickly and sharpens afterwards.
 */
export async function buildPlanetTexture(
  tex: PlanetTexture,
  onLevel: (l: TextureLevel) => void,
  signal: AbortSignal,
  opts: { maxTextureSize?: number; loadImage?: ImageLoader; concurrency?: number } = {},
): Promise<void> {
  const load = opts.loadImage ?? defaultLoadImage;
  const maxSize = opts.maxTextureSize ?? 4096;
  const src = tex.source;
  if (src.kind === "WMS_GETMAP") {
    for (const u of src.urls) {
      if (u.width > maxSize) continue;
      const img = await load(u.url, signal);
      const canvas = makeCanvas(u.width, u.height);
      (canvas.getContext("2d") as CanvasRenderingContext2D).drawImage(img, 0, 0, u.width, u.height);
      onLevel({ canvas, width: u.width, height: u.height, tilesTotal: 1, tilesMissing: 0, level: `${u.width}×${u.height}` });
    }
    return;
  }
  // NASA Trek WMTS: tile grid strictly from GetCapabilities.
  const caps = await fetchCapabilities(src.capabilitiesUrl, src.layerId);
  const layerStub = { layerId: src.layerId, crs: src.crs, planet: tex.planet, coverage: "global" } as unknown as MarsMapLayer;
  const source = buildWmtsSource(caps, layerStub);
  const grid = source.getTileGrid() as WMTSTileGrid;
  const urlFn = source.getTileUrlFunction();
  const projection = source.getProjection()!;
  for (const z of src.levels) {
    if (z > grid.getMaxZoom()) continue;
    const res = grid.getResolution(z);
    const size = grid.getTileSize(z);
    const tileSize = (Array.isArray(size) ? size[0] : size) ?? 256;
    // Tiles touching the world edge only (the extent's east/south edges fall exactly on a tile
    // boundary): shrink by a hair, and never go past the matrix size from GetCapabilities.
    const eps = res / 4;
    const range = grid.getTileRangeForExtentAndZ([-180 + eps, -90 + eps, 180 - eps, 90 - eps], z);
    const full = grid.getFullTileRange(z);
    if (full) {
      range.minX = Math.max(range.minX, full.minX);
      range.maxX = Math.min(range.maxX, full.maxX);
      range.minY = Math.max(range.minY, full.minY);
      range.maxY = Math.min(range.maxY, full.maxY);
    }
    const plan = placeTiles(z, grid.getOrigin(z) as [number, number], res, tileSize, range);
    if (plan.width > maxSize) break;
    const canvas = makeCanvas(plan.width, plan.height);
    const ctx = canvas.getContext("2d") as CanvasRenderingContext2D;
    let missing = 0;
    await pool(plan.tiles, opts.concurrency ?? 6, async (t) => {
      if (signal.aborted) return;
      const url = urlFn([t.z, t.x, t.y], 1, projection);
      if (!url) {
        missing++;
        return;
      }
      try {
        const img = await load(url, signal);
        ctx.drawImage(img, t.dx, t.dy, tileSize, tileSize);
      } catch {
        if (!signal.aborted) missing++;
      }
    });
    if (signal.aborted) return;
    onLevel({ canvas, width: plan.width, height: plan.height, tilesTotal: plan.tiles.length, tilesMissing: missing, level: `WMTS level ${z}` });
  }
}
