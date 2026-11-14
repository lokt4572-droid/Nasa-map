import { strToU8, unzipSync, zipSync } from "fflate";
import { IDBFactory } from "fake-indexeddb";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../services/api";
import type { Hazard, Mission } from "../types/api";
import { registerServiceWorker, serviceWorkerStatus } from "./serviceWorker";
import { listRecords, queueCreate, queueUpdate, resolveConflict, syncAll } from "./syncQueue";
import { buildMissionZip, readMissionZip } from "./zipPackage";

const mission = { id: 3, name: "Jezero traverse", description: "", status: "PLANNED", demo_mode: true, waypoints: [], hazard_count: 1, created_at: "", updated_at: "" } as Mission;
const hazard = {
  id: 9, mission: 3, title: "Boulders", hazard_type: "BOULDER_FIELD", severity: "MEDIUM", source: "IMAGERY_INTERPRETATION", verification: "UNVERIFIED",
  radius_m: 200, description: "", reference_layer: "", reported_by: "", observed_at: null, lon_east_deg: 77.4, lat_deg: 18.4,
  crs: "urn:ogc:def:crs:EPSG::104905", latitude_convention: "AS_DECLARED_BY_SOURCE", created_at: "", updated_at: "",
} as Hazard;

describe("sync queue (IndexedDB)", () => {
  it("syncs a create and keeps the server id/version", async () => {
    const f = new IDBFactory();
    await queueCreate("hazard", { title: "A" }, f);
    const req = vi.fn(async () => ({ id: 41, version: 1 }));
    const counts = await syncAll(req as never, f);
    expect(counts.SYNCED).toBe(1);
    const [r] = await listRecords(f);
    expect(r).toMatchObject({ sync_status: "SYNCED", server_id: 41, version: 1 });
    expect((req.mock.calls[0] as unknown[])[1]).toMatchObject({ method: "POST", body: { title: "A", client_id: r!.client_id } });
  });

  it("marks a 409 as CONFLICT and never drops the local change", async () => {
    const f = new IDBFactory();
    await queueUpdate("hazard", 7, 1, { severity: "LOW" }, "c-1", f);
    const req = vi.fn(async () => {
      throw new ApiError(409, "CONFLICT", "changed", { server: { id: 7, severity: "HIGH", version: 2 } });
    });
    await syncAll(req as never, f);
    let [r] = await listRecords(f);
    expect(r).toMatchObject({ sync_status: "CONFLICT", payload: { severity: "LOW" }, server_copy: { severity: "HIGH", version: 2 } });
    r = await resolveConflict("c-1", "keep-local", f);
    expect(r).toMatchObject({ sync_status: "PENDING", version: 2, payload: { severity: "LOW" } });
  });

  it("marks network errors FAILED and retries them later", async () => {
    const f = new IDBFactory();
    await queueCreate("mission", { name: "M" }, f);
    await syncAll((vi.fn(async () => { throw new ApiError(0, "NETWORK_ERROR", "down"); })) as never, f);
    expect((await listRecords(f))[0]!.sync_status).toBe("FAILED");
    await syncAll((vi.fn(async () => ({ id: 1, version: 1 }))) as never, f);
    expect((await listRecords(f))[0]!.sync_status).toBe("SYNCED");
  });
});

describe("ZIP mission package", () => {
  it("round-trips with the specified layout and checksums", async () => {
    const { zip, manifest } = await buildMissionZip({ mission, hazards: [hazard, { ...hazard, id: 10, mission: 99 }] });
    const names = Object.keys(unzipSync(zip));
    for (const d of ["package.json", "metadata/app.json", "imagery/README.txt", "dem/datasets.json", "terrain/README.txt", "hazards/hazards.json", "routes/routes.json", "mission/mission.json"]) {
      expect(names).toContain(`mission_package/${d}`);
    }
    expect(manifest.files.every((f) => /^[0-9a-f]{64}$/.test(f.sha256))).toBe(true);
    expect(manifest.offline_ready).toBe(false);
    // independent of map tiles: the package never carries tile images
    expect(names.filter((n) => n.includes("/imagery/"))).toEqual(["mission_package/imagery/README.txt"]);
    expect(names.some((n) => /\.(png|jpe?g|webp)$/i.test(n))).toBe(false);
    const r = await readMissionZip(zip, "MARS");
    expect(r.ok).toBe(true);
    expect(r.hazards.map((h) => h.id)).toEqual([9]); // only this mission's hazards
    expect(r.mission?.client_id).toBe(manifest.mission_client_id);
  });

  it("detects tampering, wrong planet, wrong version and garbage", async () => {
    const { zip } = await buildMissionZip({ mission, hazards: [hazard] });
    const files = unzipSync(zip);
    files["mission_package/hazards/hazards.json"] = strToU8("[]");
    expect((await readMissionZip(zipSync(files), "MARS")).errors).toContain("Checksum mismatch: hazards/hazards.json");

    expect((await readMissionZip(zip, "MOON")).errors.join()).toMatch(/Package is for MARS/);

    const f2 = unzipSync(zip);
    const man = JSON.parse(new TextDecoder().decode(f2["mission_package/package.json"]));
    f2["mission_package/package.json"] = strToU8(JSON.stringify({ ...man, format_version: 99, crs: "EPSG:4326" }));
    const bad = await readMissionZip(zipSync(f2), "MARS");
    expect(bad.errors.join()).toMatch(/Unsupported format_version 99/);
    expect(bad.errors.join()).toMatch(/does not match MARS/);

    expect((await readMissionZip(new Uint8Array([1, 2, 3]))).errors).toEqual(["Not a valid ZIP archive"]);
  });
});

describe("service worker registration", () => {
  it("is disabled in development and registers in production", async () => {
    const register = vi.fn(async () => ({}));
    registerServiceWorker(false, { serviceWorker: { register } } as unknown as Navigator);
    expect(serviceWorkerStatus()).toBe("DEV_DISABLED");
    expect(register).not.toHaveBeenCalled();
    registerServiceWorker(true, { serviceWorker: { register } } as unknown as Navigator);
    await Promise.resolve();
    await Promise.resolve();
    expect(register).toHaveBeenCalledWith("/sw.js");
    expect(serviceWorkerStatus()).toBe("ACTIVE");
  });
});
