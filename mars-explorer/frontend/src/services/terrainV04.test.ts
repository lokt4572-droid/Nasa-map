import { describe, expect, it, vi } from "vitest";

import { footprintRings, formatResolution, productCenter, productKey, searchDemProducts, type DemProduct } from "./datasetDiscoveryService";
import { buildTerrainMesh, clearPatchCache, loadTerrainPatch, patchKey } from "./localTerrainService";
import { MESH_LIMITS, meshDimensionFor, textureSizeFor, triangleCount, withinBudget } from "./terrainMeshService";

// Synthetic grids: they test the mesh arithmetic only, not any planetary measurement.
const grid = (w: number, h: number, dx = 10, dy = 10) => ({ width: w, height: h, cell_size_x_m: dx, cell_size_y_m: dy, native_cells_across: w, resampling: "" });
const stats = (z: Float32Array) => {
  const v = Array.from(z).filter(Number.isFinite);
  const min = Math.min(...v);
  const max = Math.max(...v);
  return { min, max, mean: v.reduce((a, b) => a + b, 0) / v.length, relief: max - min, nodata_fraction: 1 - v.length / z.length };
};

describe("terrain mesh (v0.4)", () => {
  it("has one vertex per sample, UVs from south-west (0,0) to north-east (1,1)", () => {
    const z = Float32Array.from([1, 2, 3, 4, 5, 6]); // 3 x 2, row 0 = north
    const m = buildTerrainMesh({ z, grid: grid(3, 2), statistics: stats(z) });
    expect(m.positions.length).toBe(18);
    expect(Array.from(m.uvs.slice(0, 2))).toEqual([0, 1]); // north-west vertex
    expect(Array.from(m.uvs.slice(4, 6))).toEqual([1, 1]); // north-east
    expect(Array.from(m.uvs.slice(6, 8))).toEqual([0, 0]); // south-west
    expect(m.validTriangles).toBe(4);
  });

  it("is metric: a 10 m x 20 m cell grid keeps its aspect ratio; heights use the same scale", () => {
    const z = Float32Array.from([0, 0, 0, 0, 30, 0, 0, 0, 0]);
    const m = buildTerrainMesh({ z, grid: grid(3, 3, 10, 20), statistics: stats(z) });
    const size = m.sizeM; // 60 m
    expect(size).toBe(60);
    expect(m.positions[2 * 3]! - m.positions[0]!).toBeCloseTo(20 / size, 6); // east extent
    expect(m.positions[6 * 3 + 2]! - m.positions[2]!).toBeCloseTo(40 / size, 6); // south extent
    const mean = 30 / 9;
    expect(m.positions[4 * 3 + 1]!).toBeCloseTo((30 - mean) / size, 6); // true height, no exaggeration
  });

  it("vertical exaggeration scales only the vertical axis", () => {
    const z = Float32Array.from([0, 10, 20, 30]);
    const a = buildTerrainMesh({ z, grid: grid(2, 2), statistics: stats(z) }, 1);
    const b = buildTerrainMesh({ z, grid: grid(2, 2), statistics: stats(z) }, 5);
    for (let i = 0; i < 4; i++) {
      expect(b.positions[i * 3]).toBe(a.positions[i * 3]);
      expect(b.positions[i * 3 + 2]).toBe(a.positions[i * 3 + 2]);
      expect(b.positions[i * 3 + 1]!).toBeCloseTo(a.positions[i * 3 + 1]! * 5, 6);
    }
  });

  it("NoData stays a hole: no triangle uses it and bounds ignore it", () => {
    const z = Float32Array.from([1, 2, 3, 4, NaN, 6, 7, 8, 9]);
    const m = buildTerrainMesh({ z, grid: grid(3, 3), statistics: stats(z) });
    expect(Array.from(m.indices)).not.toContain(4);
    expect(m.skippedTriangles).toBe(6); // every triangle touching the centre vertex
    expect(m.validTriangles).toBe(2);
    expect(m.bounds.min.every(Number.isFinite)).toBe(true);
    expect(m.bounds.max[1]).toBeGreaterThan(m.bounds.min[1]!);
  });

  it("mesh budget follows the device and never exceeds the hard limits", () => {
    expect(meshDimensionFor({ deviceMemoryGb: 2 })).toBe(128);
    expect(meshDimensionFor({ deviceMemoryGb: 16, hardwareConcurrency: 4 })).toBe(256);
    expect(meshDimensionFor({ deviceMemoryGb: 16, hardwareConcurrency: 12 }, true)).toBe(384);
    expect(meshDimensionFor({})).toBe(256);
    expect(triangleCount(256, 256)).toBe(130_050);
    expect(withinBudget(512, 512)).toBe(true);
    expect(withinBudget(513, 512)).toBe(false);
    expect(textureSizeFor({ maxTextureSize: 16384 })).toBe(MESH_LIMITS.MAX_TEXTURE_SIZE);
    expect(textureSizeFor({})).toBe(2048);
  });
});

describe("patch requests (v0.4)", () => {
  const body = { planet: "MARS", center: { lon_east_deg: 1, lat_deg: 2 }, radius_m: 130, bbox: {}, grid: grid(1, 1), dataset: {}, statistics: {}, elevation: "eJxjYGBgAAAABAAB" };

  it("auto source and native radius: no radius_m is sent, source=auto is", async () => {
    clearPatchCache();
    const request = vi.fn().mockResolvedValue(body);
    await loadTerrainPatch("MARS", 1, 2, { radiusM: "native", source: "auto", request: request as never }).catch(() => null);
    const q = request.mock.calls[0]![1].query;
    expect(q.source).toBe("auto");
    expect("radius_m" in q).toBe(false);
    expect(request.mock.calls[0]![1].timeoutMs).toBeGreaterThanOrEqual(60_000);
  });

  it("local source keeps the v0.3 request shape", async () => {
    clearPatchCache();
    const request = vi.fn().mockResolvedValue(body);
    await loadTerrainPatch("MARS", 1, 2, { radiusM: 5000, request: request as never }).catch(() => null);
    const q = request.mock.calls[0]![1].query;
    expect(q.radius_m).toBe(5000);
    expect("source" in q).toBe(false);
  });

  it("a chosen product or dataset is part of the request and of the cache key", async () => {
    clearPatchCache();
    const request = vi.fn().mockResolvedValue(body);
    await loadTerrainPatch("MARS", 1, 2, { product: "coll/ID", source: "auto", request: request as never }).catch(() => null);
    expect(request.mock.calls[0]![1].query.product).toBe("coll/ID");
    expect(patchKey("MARS", 1, 2, "native", 256, "auto::a")).not.toBe(patchKey("MARS", 1, 2, "native", 256, "auto::b"));
  });
});

describe("dataset discovery", () => {
  const product = (over: Partial<DemProduct> = {}): DemProduct =>
    ({ dataset_id: "c", product_id: "P1", bbox: [10, -2, 12, 2], footprint: { type: "Polygon", coordinates: [[[10, -2], [12, -2], [12, 2], [10, -2]]] }, ...over }) as DemProduct;

  it("reads footprint rings from polygons and multipolygons", () => {
    expect(footprintRings(product().footprint)).toHaveLength(1);
    expect(footprintRings({ type: "MultiPolygon", coordinates: [[[[0, 0], [1, 0], [1, 1], [0, 0]]], [[[5, 5], [6, 5], [6, 6], [5, 5]]]] })).toHaveLength(2);
    expect(footprintRings(null)).toEqual([]);
  });

  it("derives centre, key and readable resolution", () => {
    expect(productCenter(product())).toEqual({ lon: 11, lat: 0 });
    expect(productCenter(product({ bbox: null }))).toBeNull();
    expect(productKey(product())).toBe("c/P1");
    expect(formatResolution(1.0165)).toBe("1.02 m");
    expect(formatResolution(20.16)).toBe("20 m");
    expect(formatResolution(14817)).toBe("14.8 km");
    expect(formatResolution(null)).toBe("resolution not stated");
  });

  it("sends the view box clamped to valid latitudes and asks for DEM products only", async () => {
    const request = vi.fn().mockResolvedValue({ products: [] });
    await searchDemProducts("MARS", [-200, -95, 200, 95], { request: request as never });
    const q = request.mock.calls[0]![1].query;
    expect(q.data_type).toBe("DEM");
    expect(q.planet).toBe("MARS");
    expect(q.bbox).toBe("-200.00000,-90.00000,160.00000,90.00000"); // whole world: span capped at 360
  });
});
