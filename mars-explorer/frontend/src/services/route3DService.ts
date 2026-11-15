/**
 * Routes on the local 3D terrain. Route coordinates (lon/lat, the same values drawn on the 2D map)
 * are converted into the terrain mesh's own frame, and their heights are read from the SAME
 * elevation grid the mesh is built from — so the line and the surface share one DEM and datum.
 * The route geometry itself is never changed: this only produces display vertices.
 */
import type { TerrainPatch } from "./localTerrainService";
import { lonDelta } from "./planetary/planetaryCoordinateService";

export interface Route3D {
  /** polyline parts inside the patch, as [x, y, z, x, y, z, ...] in mesh units */
  parts: Float32Array[];
  start: [number, number, number] | null;
  end: [number, number, number] | null;
  /** fraction of the route length that lies inside the patch (0..1) */
  insideFraction: number;
}

type Grid = Pick<TerrainPatch, "z" | "grid" | "statistics" | "bbox">;

/** Fractional grid column/row (cell centres at integers) of a lon/lat, or null outside the patch. */
export function gridPosition(p: Grid, lon: number, lat: number): { c: number; r: number } | null {
  const { west, south, east, north } = p.bbox;
  const { width: w, height: h } = p.grid;
  const fx = lonDelta(west, lon) / (east - west);
  const fy = (north - lat) / (north - south);
  if (fx < 0 || fx > 1 || fy < 0 || fy > 1) return null;
  return { c: fx * w - 0.5, r: fy * h - 0.5 };
}

/** Elevation at a fractional grid position from the patch values (nearest cell; NaN = NoData). */
export function heightAt(p: Grid, c: number, r: number): number {
  const { width: w, height: h } = p.grid;
  const ci = Math.min(w - 1, Math.max(0, Math.round(c)));
  const ri = Math.min(h - 1, Math.max(0, Math.round(r)));
  return p.z[ri * w + ci]!;
}

/** Mesh coordinates, identical to buildTerrainMesh: x east, y up, z south, in units of sizeM. */
export function toMesh(p: Grid, c: number, r: number, zM: number, exaggeration: number, liftM: number): [number, number, number] {
  const { width: w, height: h, cell_size_x_m: dx, cell_size_y_m: dy } = p.grid;
  const sizeM = Math.max(w * dx, h * dy);
  return [((c - (w - 1) / 2) * dx) / sizeM, ((zM - p.statistics.mean) * exaggeration + liftM) / sizeM, ((r - (h - 1) / 2) * dy) / sizeM];
}

/**
 * Route line on the patch: densified to about one grid cell, clipped to the patch, split at NoData.
 * ``liftM`` raises the line above the surface (metres, before exaggeration) to avoid z-fighting.
 */
export function routeOnPatch(p: Grid, coords: [number, number][], exaggeration: number, liftM?: number): Route3D {
  const { width: w, height: h, cell_size_x_m: dx, cell_size_y_m: dy } = p.grid;
  const lift = liftM ?? Math.max(dx, dy) * 0.6;
  const parts: Float32Array[] = [];
  let cur: number[] = [];
  let inside = 0;
  let total = 0;
  const flush = () => {
    if (cur.length >= 6) parts.push(Float32Array.from(cur));
    cur = [];
  };
  for (let k = 0; k < coords.length - 1; k++) {
    const [lo1, la1] = coords[k]!;
    const [lo2, la2] = coords[k + 1]!;
    const dLon = lonDelta(lo1, lo2);
    // samples per segment: about one per grid cell crossed (bounded)
    const g1 = gridPosition(p, lo1, la1);
    const g2 = gridPosition(p, lo2, la2);
    const spanCells = g1 && g2 ? Math.hypot(g2.c - g1.c, g2.r - g1.r) : (Math.abs(dLon) / (p.bbox.east - p.bbox.west)) * w + (Math.abs(la2 - la1) / (p.bbox.north - p.bbox.south)) * h;
    const n = Math.min(4 * Math.max(w, h), Math.max(1, Math.ceil(spanCells)));
    for (let i = 0; i < n; i++) {
      const t = i / n;
      const lon = lo1 + dLon * t;
      const lat = la1 + (la2 - la1) * t;
      total++;
      const g = gridPosition(p, lon, lat);
      const z = g ? heightAt(p, g.c, g.r) : NaN;
      if (!g || !Number.isFinite(z)) {
        flush();
        continue;
      }
      inside++;
      cur.push(...toMesh(p, g.c, g.r, z, exaggeration, lift));
    }
  }
  const last = coords[coords.length - 1];
  if (last) {
    total++;
    const g = gridPosition(p, last[0], last[1]);
    const z = g ? heightAt(p, g.c, g.r) : NaN;
    if (g && Number.isFinite(z)) {
      inside++;
      cur.push(...toMesh(p, g.c, g.r, z, exaggeration, lift));
    }
  }
  flush();
  const end = (pt?: [number, number]) => {
    if (!pt) return null;
    const g = gridPosition(p, pt[0], pt[1]);
    const z = g ? heightAt(p, g.c, g.r) : NaN;
    return g && Number.isFinite(z) ? toMesh(p, g.c, g.r, z, exaggeration, lift * 2) : null;
  };
  return { parts, start: end(coords[0]), end: end(last), insideFraction: total ? inside / total : 0 };
}
