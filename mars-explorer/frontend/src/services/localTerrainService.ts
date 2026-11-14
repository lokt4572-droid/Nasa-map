/**
 * Local terrain patches for the click-to-explore 3D viewer (Phase 4).
 *
 * Elevations come only from GET /api/v1/terrain/patch/ (a registered, validated DEM). When no DEM
 * covers the point the result is UNAVAILABLE — there is no fallback terrain. If the DEM is too
 * coarse for the requested radius, the request is repeated once with a radius giving
 * TARGET_NATIVE_CELLS real cells across (the backend states the native resolution), and the UI
 * shows the radius actually used.
 */
import { unzlibSync } from "fflate";

import type { PlanetId } from "../config/planetRegistry";
import { ApiError, apiRequest } from "./api";

export const TARGET_NATIVE_CELLS = 24;
export const MAX_RADIUS_M = 500_000;
export const DEFAULT_RADIUS_M = 20_000;

export interface PatchResponse {
  planet: string;
  center: { lon_east_deg: number; lat_deg: number };
  radius_m: number;
  bbox: { west: number; south: number; east: number; north: number };
  grid: { width: number; height: number; cell_size_x_m: number; cell_size_y_m: number; native_cells_across: number; resampling: string };
  dataset: {
    id: number;
    name: string;
    instrument: string;
    product_id: string;
    source: string;
    license: string;
    native_resolution_m: number;
    crs_name: string;
    latitude_convention: string;
    vertical_datum: string;
    units: string;
  };
  statistics: { min: number; max: number; mean: number; relief: number; nodata_fraction: number };
  encoding: string;
  elevation: string;
  suitability: "REGIONAL_OVERVIEW_ONLY" | "SITE_RECONNAISSANCE" | "DETAILED_STUDY";
  notes: string[];
  latitude?: { status: string; warning: string | null };
}

export interface TerrainPatch extends Omit<PatchResponse, "elevation"> {
  /** row-major, north -> south, west -> east; NaN = NoData */
  z: Float32Array;
  /** radius was enlarged because the DEM is too coarse for the requested one */
  radiusAdjusted: boolean;
  requestedRadiusM: number;
}

export type PatchResult =
  | { status: "OK"; patch: TerrainPatch }
  | { status: "UNAVAILABLE"; code: string; message: string };

/** Decode the backend's zlib+base64 float32 grid. */
export function decodeElevation(b64: string, width: number, height: number): Float32Array {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  const raw = unzlibSync(bytes);
  if (raw.byteLength !== width * height * 4) throw new Error(`Elevation grid has ${raw.byteLength} bytes, expected ${width * height * 4}`);
  // little-endian float32 (DataView: independent of host byte order)
  const dv = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const z = new Float32Array(width * height);
  for (let i = 0; i < z.length; i++) z[i] = dv.getFloat32(i * 4, true);
  return z;
}

const cache = new Map<string, PatchResult>();
const MAX_CACHE = 24;

export function patchKey(planet: string, lon: number, lat: number, radiusM: number, maxDim: number): string {
  return `${planet}:${lon.toFixed(5)}:${lat.toFixed(5)}:${Math.round(radiusM)}:${maxDim}`;
}

export function clearPatchCache(): void {
  cache.clear();
}

type Request = typeof apiRequest;

export async function loadTerrainPatch(
  planet: PlanetId,
  lon: number,
  lat: number,
  opts: { radiusM?: number; maxDimension?: number; signal?: AbortSignal; request?: Request } = {},
): Promise<PatchResult> {
  const radius = opts.radiusM ?? DEFAULT_RADIUS_M;
  const maxDim = opts.maxDimension ?? 192;
  const key = patchKey(planet, lon, lat, radius, maxDim);
  const hit = cache.get(key);
  if (hit) return hit;
  const request = opts.request ?? apiRequest;
  const get = (r: number) =>
    request<PatchResponse>("/terrain/patch/", {
      query: { planet, longitude: lon, latitude: lat, radius_m: Math.round(r), max_dimension: maxDim },
      signal: opts.signal,
      timeoutMs: 30_000,
    });

  let result: PatchResult;
  try {
    let body: PatchResponse;
    let adjusted = false;
    try {
      body = await get(radius);
    } catch (err) {
      const d = err instanceof ApiError ? (err.details as { native_resolution_m?: number } | undefined) : undefined;
      if (err instanceof ApiError && err.code === "DEM_TOO_COARSE_FOR_PATCH" && d?.native_resolution_m) {
        const r2 = Math.min(MAX_RADIUS_M, (TARGET_NATIVE_CELLS * d.native_resolution_m) / 2);
        if (r2 <= radius) throw err;
        body = await get(r2);
        adjusted = true;
      } else throw err;
    }
    const { elevation, ...rest } = body;
    result = {
      status: "OK",
      patch: { ...rest, z: decodeElevation(elevation, body.grid.width, body.grid.height), radiusAdjusted: adjusted, requestedRadiusM: radius },
    };
  } catch (err) {
    if (opts.signal?.aborted) throw err;
    if (err instanceof ApiError && (err.status === 404 || err.status === 422)) {
      result = { status: "UNAVAILABLE", code: err.code, message: err.message };
    } else throw err; // network/server errors are not cached
  }
  cache.set(key, result);
  if (cache.size > MAX_CACHE) cache.delete(cache.keys().next().value!);
  return result;
}

export interface TerrainMeshArrays {
  positions: Float32Array;
  colors: Float32Array;
  indices: Uint32Array;
  /** horizontal extent of the scene (metres) used for normalisation */
  sizeM: number;
  validTriangles: number;
  skippedTriangles: number;
}

const RAMP: [number, [number, number, number]][] = [
  [0, [0.16, 0.24, 0.55]],
  [0.25, [0.24, 0.59, 0.47]],
  [0.5, [0.75, 0.71, 0.35]],
  [0.75, [0.59, 0.37, 0.2]],
  [1, [0.96, 0.96, 0.96]],
];

export function rampColor(t: number): [number, number, number] {
  const x = Math.min(1, Math.max(0, t));
  for (let i = 1; i < RAMP.length; i++) {
    const [t1, c1] = RAMP[i]!;
    const [t0, c0] = RAMP[i - 1]!;
    if (x <= t1) {
      const f = (x - t0) / (t1 - t0 || 1);
      return [c0[0] + f * (c1[0] - c0[0]), c0[1] + f * (c1[1] - c0[1]), c0[2] + f * (c1[2] - c0[2])];
    }
  }
  return RAMP[RAMP.length - 1]![1];
}

/**
 * Mesh in a local east/north frame: x = east, y = up, z = south (metres / sizeM).
 * Triangles touching a NoData cell are skipped (holes stay holes). `exaggeration` scales only
 * the vertical axis and is a visual aid.
 */
export function buildTerrainMesh(p: Pick<TerrainPatch, "z" | "grid" | "statistics">, exaggeration = 1): TerrainMeshArrays {
  const { width: w, height: h, cell_size_x_m: dx, cell_size_y_m: dy } = p.grid;
  const sizeM = Math.max(w * dx, h * dy);
  const { min, max, mean } = p.statistics;
  const span = max - min || 1;
  const positions = new Float32Array(w * h * 3);
  const colors = new Float32Array(w * h * 3);
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      const i = r * w + c;
      const zv = p.z[i]!;
      const ok = Number.isFinite(zv);
      positions[i * 3] = ((c - (w - 1) / 2) * dx) / sizeM;
      positions[i * 3 + 1] = ok ? ((zv - mean) * exaggeration) / sizeM : 0;
      positions[i * 3 + 2] = ((r - (h - 1) / 2) * dy) / sizeM;
      const col = ok ? rampColor((zv - min) / span) : [0, 0, 0];
      colors.set(col, i * 3);
    }
  }
  const idx: number[] = [];
  let skipped = 0;
  const fin = (i: number) => Number.isFinite(p.z[i]!);
  for (let r = 0; r < h - 1; r++) {
    for (let c = 0; c < w - 1; c++) {
      const a = r * w + c;
      const b = a + 1;
      const d = a + w;
      const e = d + 1;
      if (fin(a) && fin(d) && fin(b)) idx.push(a, d, b);
      else skipped++;
      if (fin(b) && fin(d) && fin(e)) idx.push(b, d, e);
      else skipped++;
    }
  }
  return { positions, colors, indices: Uint32Array.from(idx), sizeM, validTriangles: idx.length / 3, skippedTriangles: skipped };
}
