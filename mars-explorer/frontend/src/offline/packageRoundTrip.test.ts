/**
 * Mission package round trip: CREATE -> EXPORT ZIP -> DELETE TEST COPY -> IMPORT ZIP ->
 * VALIDATE CHECKSUMS -> RESTORE -> VERIFY RECORDS. The backend is an in-memory fake that follows
 * the real API's rules (client_id replay returns the existing record; PATCH needs the version).
 * The live check against the running backend is recorded separately (manual/browser test).
 */
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";
import { describe, expect, it } from "vitest";

import { ApiError } from "../services/api";
import type { Hazard, Mission } from "../types/api";
import { restoreMissionPackage } from "./packageImport";
import { buildMissionZip, readMissionZip } from "./zipPackage";

function fakeBackend() {
  const db = { missions: new Map<number, Mission & { client_id?: string; version: number }>(), hazards: new Map<number, Hazard & { version: number }>() };
  let next = 1;
  const request = async <T,>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> => {
    const body = opts.body as Record<string, unknown>;
    if (path === "/missions/" && opts.method === "POST") {
      const hit = [...db.missions.values()].find((m) => body.client_id && m.client_id === body.client_id);
      if (hit) return { ...hit, replayed: true } as T;
      const m = { ...(body as unknown as Mission), id: next++, version: 1 };
      db.missions.set(m.id, m as never);
      return m as T;
    }
    if (path === "/hazards/" && opts.method === "POST") {
      const hit = [...db.hazards.values()].find((h) => body.client_id && h.client_id === body.client_id);
      if (hit) return { ...hit, replayed: true } as T;
      const h = { ...(body as unknown as Hazard), id: next++, version: 1 };
      db.hazards.set(h.id, h as never);
      return h as T;
    }
    const m = /^\/hazards\/(\d+)\/$/.exec(path);
    if (m && opts.method === "PATCH") {
      const h = db.hazards.get(Number(m[1]))!;
      if (body.version !== undefined && body.version !== h.version) throw new ApiError(409, "CONFLICT", "stale");
      Object.assign(h, { ...body, version: h.version + 1 });
      return h as T;
    }
    throw new ApiError(404, "NOT_FOUND", path);
  };
  return { db, request: request as never };
}

const hazard = (id: number, mission: number, title: string, client_id: string): Hazard =>
  ({ id, mission, title, hazard_type: "CRATER", severity: "LOW", source: "OTHER", verification: "UNVERIFIED", radius_m: 50, description: "",
     reference_layer: "", reported_by: "", observed_at: null, lon_east_deg: 77.4, lat_deg: 18.4, crs: "urn:ogc:def:crs:EPSG::104905",
     latitude_convention: "AS_DECLARED_BY_SOURCE", client_id, created_at: "", updated_at: "" }) as Hazard;

describe("mission package round trip (disposable test mission)", () => {
  it("restores a deleted mission and re-links its orphaned hazards without duplicating anything", async () => {
    const { db, request } = fakeBackend();
    // CREATE
    const mission = { id: 100, name: "TEST-roundtrip", description: "disposable", status: "PLANNED", client_id: "11111111-1111-4111-8111-111111111111" } as unknown as Mission;
    db.missions.set(100, { ...mission, version: 1 } as never);
    const hz = [hazard(201, 100, "Rim", "22222222-2222-4222-8222-222222222222"), hazard(202, 100, "Scarp", "33333333-3333-4333-8333-333333333333")];
    hz.forEach((h) => db.hazards.set(h.id, { ...h, version: 1 } as never));
    // EXPORT
    const { zip, manifest } = await buildMissionZip({ mission, hazards: hz, planet: "MARS" });
    expect(manifest.mission_client_id).toBe(mission.client_id);
    // DELETE TEST COPY (hazards stay, orphaned, as with the real backend's SET_NULL)
    db.missions.delete(100);
    db.hazards.forEach((h) => (h.mission = null));
    // IMPORT + VALIDATE CHECKSUMS
    const parsed = await readMissionZip(zip, "MARS");
    expect(parsed.errors).toEqual([]);
    // RESTORE
    const report = await restoreMissionPackage(parsed, request);
    expect(report.mission.outcome).toBe("CREATED");
    expect(report.hazards.map((h) => h.outcome)).toEqual(["RELINKED", "RELINKED"]);
    // VERIFY RECORDS
    expect(db.missions.size).toBe(1);
    expect(db.hazards.size).toBe(2);
    const newId = report.mission.id;
    expect([...db.hazards.values()].every((h) => h.mission === newId)).toBe(true);
    // Importing again changes nothing.
    const again = await restoreMissionPackage(parsed, request);
    expect(again.mission.outcome).toBe("UNCHANGED");
    expect(again.hazards.map((h) => h.outcome)).toEqual(["UNCHANGED", "UNCHANGED"]);
    expect(db.hazards.size).toBe(2);
  });

  it("keeps an edited server copy and reports the difference instead of overwriting it", async () => {
    const { db, request } = fakeBackend();
    const mission = { id: 1, name: "TEST-conflict", description: "", status: "PLANNED", client_id: "44444444-4444-4444-8444-444444444444" } as unknown as Mission;
    const h = hazard(5, 1, "Boulders", "55555555-5555-4555-8555-555555555555");
    const { zip } = await buildMissionZip({ mission, hazards: [h], planet: "MARS" });
    const parsed = await readMissionZip(zip, "MARS");
    await restoreMissionPackage(parsed, request);
    const server = [...db.hazards.values()][0]!;
    server.radius_m = 400; // someone edited it after the first import
    const r = await restoreMissionPackage(parsed, request);
    expect(r.hazards[0]).toMatchObject({ outcome: "KEPT_SERVER_COPY", differences: ["radius_m"] });
    expect(server.radius_m).toBe(400);
  });

  it("refuses a tampered package and a package for another body", async () => {
    const mission = { id: 1, name: "T", description: "", status: "PLANNED" } as unknown as Mission;
    const { zip } = await buildMissionZip({ mission, hazards: [hazard(5, 1, "X", "66666666-6666-4666-8666-666666666666")], planet: "MARS" });
    const files = unzipSync(zip);
    const key = Object.keys(files).find((k) => k.endsWith("hazards/hazards.json"))!;
    files[key] = strToU8(strFromU8(files[key]!).replace("\"X\"", "\"Y\""));
    const tampered = await readMissionZip(zipSync(files), "MARS");
    expect(tampered.ok).toBe(false);
    expect(tampered.errors.join()).toMatch(/Checksum mismatch: hazards\/hazards.json/);
    expect((await readMissionZip(zip, "MOON")).errors.join()).toMatch(/Package is for MARS/);
    await expect(restoreMissionPackage(tampered, fakeBackend().request)).rejects.toThrow("not validated");
  });

  it("exports a Moon mission with the lunar CRS", async () => {
    const mission = { id: 1, name: "Lunar", description: "", status: "PLANNED" } as unknown as Mission;
    const { manifest } = await buildMissionZip({ mission, hazards: [], planet: "MOON" });
    expect(manifest.planet).toBe("MOON");
    expect(manifest.crs).toMatch(/104903/);
  });
});
