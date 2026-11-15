/**
 * High-resolution coverage catalogue (Phase 6). Regions are derived from the layer catalogue
 * (config/mapLayers.ts: every regional layer carries a `region`), so a new mosaic added there
 * appears here, on the map's coverage outlines and in auto high-resolution switching without
 * any component change. Jezero is one catalogue entry like the others.
 *
 * DEM availability is asked from the backend (registered, validated DEMs), never assumed.
 */
import { layersForPlanet, type BBox, type MarsMapLayer } from "../config/mapLayers";
import type { PlanetId } from "../config/planetRegistry";
import type { CoverageResponse, DatasetSummary } from "../types/api";
import { getCoverage } from "./datasetService";

export interface CoverageRegion {
  id: string;
  name: string;
  context: string;
  planet: PlanetId;
  /** union of the region's dataset bboxes */
  bbox: BBox;
  center: { lon: number; lat: number };
  datasets: MarsMapLayer[]; // finest tile pyramid first
}

export function unionBBox(boxes: BBox[]): BBox {
  return {
    west: Math.min(...boxes.map((b) => b.west)),
    south: Math.min(...boxes.map((b) => b.south)),
    east: Math.max(...boxes.map((b) => b.east)),
    north: Math.max(...boxes.map((b) => b.north)),
  };
}

export function coverageRegions(planet: PlanetId): CoverageRegion[] {
  const byRegion = new Map<string, CoverageRegion>();
  for (const l of layersForPlanet(planet)) {
    if (l.coverage !== "regional" || !l.region) continue;
    const r = byRegion.get(l.region.id);
    if (r) r.datasets.push(l);
    else byRegion.set(l.region.id, { ...l.region, planet, bbox: l.bbox, center: { lon: 0, lat: 0 }, datasets: [l] });
  }
  const out = [...byRegion.values()];
  for (const r of out) {
    r.datasets.sort((a, b) => b.tileMatrixLevelsVerified - a.tileMatrixLevelsVerified);
    r.bbox = unionBBox(r.datasets.map((d) => d.bbox));
    r.center = { lon: (r.bbox.west + r.bbox.east) / 2, lat: (r.bbox.south + r.bbox.north) / 2 };
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

/** Area of a lon/lat box on a sphere (km^2), for display. */
export function bboxAreaKm2(b: BBox, radiusM: number): number {
  const r = radiusM / 1000;
  const d2r = Math.PI / 180;
  return r * r * (b.east - b.west) * d2r * Math.abs(Math.sin(b.north * d2r) - Math.sin(b.south * d2r));
}

export interface DemAvailability {
  status: "LOADING" | "LOCAL_DEM" | "REGIONAL_ONLY" | "NONE" | "ERROR";
  label: string;
  datasets: DatasetSummary[];
}

/** Local-scale DEMs are those with cells of 100 m or finer (site reconnaissance or better). */
export const LOCAL_DEM_MAX_CELL_M = 100;

export function classifyDem(resp: Pick<CoverageResponse, "datasets" | "terrain_analysis_status">): DemAvailability {
  const ds = resp.datasets;
  if (!ds.length) return { status: "NONE", label: "No validated DEM covers this region", datasets: [] };
  const finest = Math.min(...ds.map((d) => d.resolution_meters ?? Infinity));
  if (finest <= LOCAL_DEM_MAX_CELL_M) {
    return { status: "LOCAL_DEM", label: `DEM ${Math.round(finest)} m/cell available (local 3D terrain)`, datasets: ds };
  }
  return {
    status: "REGIONAL_ONLY",
    label: `Only a ${(finest / 1000).toFixed(1)} km/cell DEM (${ds.map((d) => d.name).join(", ")}): regional overview, no local-scale terrain`,
    datasets: ds,
  };
}

const demCache = new Map<string, Promise<DemAvailability>>();

export function demAvailability(region: CoverageRegion): Promise<DemAvailability> {
  const key = `${region.planet}:${region.id}`;
  let p = demCache.get(key);
  if (!p) {
    p = getCoverage(region.center.lon, region.center.lat, undefined, region.planet).then(classifyDem);
    p.catch(() => demCache.delete(key)); // failures are retried next time
    demCache.set(key, p);
  }
  return p;
}
