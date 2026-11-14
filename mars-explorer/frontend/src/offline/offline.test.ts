import { describe, expect, it } from "vitest";

import type { Hazard, Mission } from "../types/api";
import { listMissionPackages, loadMissionPackage, saveMissionPackage } from "./localStore";
import { buildMissionPackage, validateMissionPackage } from "./missionPackage";

const mission: Mission = {
  id: 7,
  name: "Traverse study",
  description: "",
  status: "PLANNED",
  demo_mode: true,
  waypoints: [],
  hazard_count: 1,
  created_at: "2026-11-12T00:00:00Z",
  updated_at: "2026-11-12T00:00:00Z",
};
const hz = (id: number, missionId: number | null): Hazard => ({
  id,
  mission: missionId,
  title: `h${id}`,
  hazard_type: "CRATER",
  severity: "LOW",
  source: "IMAGERY_INTERPRETATION",
  verification: "UNVERIFIED",
  radius_m: null,
  description: "",
  reference_layer: "",
  reported_by: "",
  observed_at: null,
  lon_east_deg: 77.4,
  lat_deg: 18.4,
  crs: "urn:ogc:def:crs:EPSG::104905",
  latitude_convention: "AS_DECLARED_BY_SOURCE",
  created_at: "",
  updated_at: "",
});

describe("mission data package", () => {
  it("includes only the mission's hazards and never claims offline readiness", () => {
    const pkg = buildMissionPackage(mission, [hz(1, 7), hz(2, 8), hz(3, null)]);
    expect(pkg["hazards.json"].map((h) => h.id)).toEqual([1]);
    expect(pkg["metadata.json"].offlineReady).toBe(false);
    expect(pkg["metadata.json"].contents.imagery).toBe("NOT_INCLUDED");
    expect(pkg["metadata.json"].coordinateConvention.crs).toBe("urn:ogc:def:crs:EPSG::104905");
    expect(validateMissionPackage(pkg)).toEqual([]);
  });

  it("rejects malformed packages", () => {
    expect(validateMissionPackage({})).toContain("mission.json missing");
    expect(validateMissionPackage(null)).toEqual(["package is not an object"]);
  });

  it("round-trips through IndexedDB", async () => {
    const pkg = buildMissionPackage(mission, [hz(1, 7)]);
    await saveMissionPackage(pkg);
    const loaded = await loadMissionPackage(7);
    expect(loaded?.package["mission.json"].name).toBe("Traverse study");
    expect(loaded?.package["hazards.json"]).toHaveLength(1);
    expect((await listMissionPackages()).map((r) => r.missionId)).toContain(7);
  });
});
