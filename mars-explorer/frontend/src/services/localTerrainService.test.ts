import { zlibSync } from "fflate";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import {
  TARGET_NATIVE_CELLS,
  buildTerrainMesh,
  clearPatchCache,
  decodeElevation,
  loadTerrainPatch,
  type PatchResponse,
} from "./localTerrainService";

function encode(values: number[]): string {
  const buf = new ArrayBuffer(values.length * 4);
  const dv = new DataView(buf);
  values.forEach((v, i) => dv.setFloat32(i * 4, v, true));
  const z = zlibSync(new Uint8Array(buf));
  return btoa(String.fromCharCode(...z));
}

function response(values: number[], w: number, h: number, extra: Partial<PatchResponse> = {}): PatchResponse {
  const finite = values.filter(Number.isFinite);
  return {
    planet: "MARS",
    center: { lon_east_deg: 77.4, lat_deg: 18.4 },
    radius_m: 20_000,
    bbox: { west: 77, south: 18, east: 78, north: 19 },
    grid: { width: w, height: h, cell_size_x_m: 100, cell_size_y_m: 100, native_cells_across: w, resampling: "nearest" },
    dataset: {
      id: 1, name: "fixture", instrument: "test", product_id: "p", source: "s", license: "l", native_resolution_m: 100,
      crs_name: "c", latitude_convention: "PLANETOCENTRIC", vertical_datum: "d", units: "meter",
    },
    statistics: {
      min: Math.min(...finite), max: Math.max(...finite), mean: finite.reduce((a, b) => a + b, 0) / finite.length,
      relief: Math.max(...finite) - Math.min(...finite), nodata_fraction: 1 - finite.length / values.length,
    },
    encoding: "zlib+base64; float32 little-endian; row-major north->south, west->east; NaN = NoData",
    elevation: encode(values),
    suitability: "SITE_RECONNAISSANCE",
    notes: [],
    ...extra,
  };
}

beforeEach(() => clearPatchCache());

describe("decoding", () => {
  it("decodes zlib+base64 little-endian float32 and keeps NaN", () => {
    const z = decodeElevation(encode([1.5, -2, Number.NaN, 4000]), 2, 2);
    expect(Array.from(z.slice(0, 2))).toEqual([1.5, -2]);
    expect(Number.isNaN(z[2])).toBe(true);
    expect(z[3]).toBe(4000);
  });

  it("rejects a grid of the wrong size", () => {
    expect(() => decodeElevation(encode([1, 2, 3]), 2, 2)).toThrow(/expected 16/);
  });
});

describe("mesh", () => {
  it("skips triangles touching NoData (holes stay holes)", () => {
    const vals = [0, 1, 2, 3, Number.NaN, 5, 6, 7, 8];
    const p = response(vals, 3, 3);
    const m = buildTerrainMesh({ ...p, z: Float32Array.from(vals) });
    expect(m.validTriangles + m.skippedTriangles).toBe(8);
    expect(m.skippedTriangles).toBe(6); // centre vertex touches 6 of the 8 triangles
    for (let i = 0; i < m.indices.length; i++) expect(m.indices[i]).not.toBe(4);
  });

  it("orientation: x east, z south; exaggeration scales only heights", () => {
    const vals = [0, 10, 20, 30];
    const p = { ...response(vals, 2, 2), z: Float32Array.from(vals) };
    const a = buildTerrainMesh(p, 1);
    const b = buildTerrainMesh(p, 3);
    expect(a.positions[0]).toBeLessThan(a.positions[3]!); // col 0 west of col 1
    expect(a.positions[2]).toBeLessThan(a.positions[8]!); // row 0 (north) at smaller z
    for (const i of [0, 2, 3, 5]) expect(b.positions[i]).toBe(a.positions[i]);
    expect(b.positions[10]! - b.positions[1]!).toBeCloseTo(3 * (a.positions[10]! - a.positions[1]!), 6);
    expect(a.sizeM).toBe(200);
  });
});

describe("loading", () => {
  it("returns the patch and caches it", async () => {
    const request = vi.fn(async () => response([1, 2, 3, 4], 2, 2));
    const r1 = await loadTerrainPatch("MARS", 77.4, 18.4, { request: request as never });
    const r2 = await loadTerrainPatch("MARS", 77.4, 18.4, { request: request as never });
    expect(r1.status).toBe("OK");
    expect(r2).toBe(r1);
    expect(request).toHaveBeenCalledTimes(1);
    expect((request.mock.calls[0] as unknown as [string, { query: Record<string, unknown> }])[1].query).toMatchObject({
      planet: "MARS", longitude: 77.4, latitude: 18.4, radius_m: 20_000,
    });
  });

  it("no DEM -> UNAVAILABLE (no fallback terrain)", async () => {
    const request = vi.fn(async () => {
      throw new ApiError(404, "DEM_NOT_AVAILABLE", "No validated DEM covering this point is loaded.");
    });
    const r = await loadTerrainPatch("MOON", 0, 0, { request: request as never });
    expect(r).toEqual({ status: "UNAVAILABLE", code: "DEM_NOT_AVAILABLE", message: "No validated DEM covering this point is loaded." });
  });

  it("DEM too coarse -> one retry with a radius of TARGET_NATIVE_CELLS native cells, flagged as adjusted", async () => {
    const request = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(422, "DEM_TOO_COARSE_FOR_PATCH", "too coarse", { native_resolution_m: 14_818, min_radius_m: 29_636 }))
      .mockResolvedValueOnce(response([1, 2, 3, 4], 2, 2, { radius_m: 177_816 }));
    const r = await loadTerrainPatch("MARS", 77.4, 18.4, { radiusM: 20_000, request: request as never });
    expect(r.status).toBe("OK");
    if (r.status !== "OK") return;
    expect(r.patch.radiusAdjusted).toBe(true);
    expect(r.patch.requestedRadiusM).toBe(20_000);
    expect((request.mock.calls[1] as [string, { query: { radius_m: number } }])[1].query.radius_m).toBe(Math.round((TARGET_NATIVE_CELLS * 14_818) / 2));
  });

  it("network errors are thrown and not cached", async () => {
    const request = vi.fn().mockRejectedValueOnce(new ApiError(0, "NETWORK_ERROR", "down")).mockResolvedValueOnce(response([1, 2, 3, 4], 2, 2));
    await expect(loadTerrainPatch("MARS", 1, 1, { request: request as never })).rejects.toThrow("down");
    expect((await loadTerrainPatch("MARS", 1, 1, { request: request as never })).status).toBe("OK");
  });
});
