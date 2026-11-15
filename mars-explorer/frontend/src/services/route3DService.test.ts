import { describe, expect, it } from "vitest";

import { buildTerrainMesh } from "./localTerrainService";
import { gridPosition, routeOnPatch, toMesh } from "./route3DService";

// Synthetic 11 x 11 patch (arithmetic check only): elevation = 10 * column.
const n = 11;
const z = Float32Array.from({ length: n * n }, (_, i) => 10 * (i % n));
const patch = {
  z,
  bbox: { west: 10, south: 0, east: 11, north: 1 },
  grid: { width: n, height: n, cell_size_x_m: 100, cell_size_y_m: 100, native_cells_across: n, resampling: "" },
  statistics: { min: 0, max: 100, mean: 50, relief: 100, nodata_fraction: 0 },
};

describe("route on local 3D terrain", () => {
  it("uses the same frame as the terrain mesh", () => {
    const mesh = buildTerrainMesh(patch as never, 2);
    const g = gridPosition(patch as never, 10 + 7.5 / n, 1 - 3.5 / n)!; // centre of column 7, row 3
    expect(g.c).toBeCloseTo(7, 9);
    expect(g.r).toBeCloseTo(3, 9);
    const v = toMesh(patch as never, 7, 3, z[3 * n + 7]!, 2, 0);
    const i = (3 * n + 7) * 3;
    expect(v[0]).toBeCloseTo(mesh.positions[i]!, 6);
    expect(v[1]).toBeCloseTo(mesh.positions[i + 1]!, 6); // same height as the surface vertex
    expect(v[2]).toBeCloseTo(mesh.positions[i + 2]!, 6);
  });

  it("follows the surface, lifted, and reports start/end inside the patch", () => {
    const r = routeOnPatch(patch as never, [[10.05, 0.5], [10.95, 0.5]], 1, 5);
    expect(r.parts).toHaveLength(1);
    expect(r.insideFraction).toBe(1);
    const ys = Array.from(r.parts[0]!).filter((_, k) => k % 3 === 1);
    expect(ys[ys.length - 1]! - ys[0]!).toBeGreaterThan(0); // climbs with the terrain (10 m per column)
    expect(r.start).not.toBeNull();
    expect(r.end).not.toBeNull();
  });

  it("clips to the patch and reports no intersection outside it", () => {
    const part = routeOnPatch(patch as never, [[9.5, 0.5], [10.5, 0.5]], 1);
    expect(part.start).toBeNull();
    expect(part.insideFraction).toBeGreaterThan(0);
    expect(part.insideFraction).toBeLessThan(1);
    const none = routeOnPatch(patch as never, [[20, 5], [21, 5]], 1);
    expect(none.parts).toHaveLength(0);
    expect(none.insideFraction).toBe(0);
  });

  it("splits the line at NoData instead of bridging it", () => {
    const zz = Float32Array.from(z);
    for (let r = 0; r < n; r++) zz[r * n + 5] = NaN;
    const r = routeOnPatch({ ...patch, z: zz } as never, [[10.05, 0.5], [10.95, 0.5]], 1);
    expect(r.parts.length).toBe(2);
  });
});
