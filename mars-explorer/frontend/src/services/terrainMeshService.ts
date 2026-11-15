/**
 * Terrain mesh limits and budget checks for the local 3D viewer (v0.4).
 *
 * The mesh itself is built by `buildTerrainMesh` (localTerrainService): one vertex per DEM
 * sample in a local east/north metric frame, triangles skipped at NoData, UVs for draping
 * imagery, bounds of the valid vertices. This module decides HOW LARGE a mesh the device gets.
 * Render geometry is never used for analysis: slopes, profiles and routes are computed from
 * the DEM grid on the backend.
 */
export { buildTerrainMesh, type TerrainMeshArrays } from "./localTerrainService";

export const MESH_LIMITS = {
  MAX_LOCAL_MESH_WIDTH: 512,
  MAX_LOCAL_MESH_HEIGHT: 512,
  /** two triangles per grid cell: 511 * 511 * 2 */
  MAX_TRIANGLE_COUNT: 522_242,
  MAX_TEXTURE_SIZE: 4096,
  MAX_CONCURRENT_TERRAIN_REQUESTS: 1,
} as const;

export interface DeviceHints {
  /** navigator.deviceMemory (GB), when the browser reports it */
  deviceMemoryGb?: number;
  /** gl.MAX_TEXTURE_SIZE, when a context is available */
  maxTextureSize?: number;
  hardwareConcurrency?: number;
}

/**
 * Grid side (cells) to request for a patch on this device: 256 by default, 128 on low-memory
 * devices, never above the hard limits. The backend additionally never returns a grid finer
 * than the DEM itself.
 */
export function meshDimensionFor(hints: DeviceHints, expanded = false): number {
  const mem = hints.deviceMemoryGb ?? 8;
  const cores = hints.hardwareConcurrency ?? 4;
  let side = mem <= 2 || cores <= 2 ? 128 : 256;
  if (expanded && mem >= 8 && cores >= 8) side = 384;
  return Math.min(side, MESH_LIMITS.MAX_LOCAL_MESH_WIDTH, MESH_LIMITS.MAX_LOCAL_MESH_HEIGHT);
}

export function triangleCount(width: number, height: number): number {
  return Math.max(0, width - 1) * Math.max(0, height - 1) * 2;
}

export function withinBudget(width: number, height: number): boolean {
  return width <= MESH_LIMITS.MAX_LOCAL_MESH_WIDTH && height <= MESH_LIMITS.MAX_LOCAL_MESH_HEIGHT && triangleCount(width, height) <= MESH_LIMITS.MAX_TRIANGLE_COUNT;
}

export function textureSizeFor(hints: DeviceHints): number {
  return Math.min(MESH_LIMITS.MAX_TEXTURE_SIZE, hints.maxTextureSize ?? 2048);
}

export function deviceHints(): DeviceHints {
  if (typeof navigator === "undefined") return {};
  return { deviceMemoryGb: (navigator as Navigator & { deviceMemory?: number }).deviceMemory, hardwareConcurrency: navigator.hardwareConcurrency };
}
