/**
 * Mission Data Package — schema for the future offline bundle.
 *
 *   mars_mission_package/
 *   ├── metadata.json      (MissionPackageMetadata)
 *   ├── imagery/           (pre-fetched WMTS tiles for the mission area — NOT implemented)
 *   ├── dem/               (DEM subsets — NOT implemented)
 *   ├── terrain/           (derived slope/roughness — NOT implemented)
 *   ├── hazards.json       (Hazard[])
 *   └── mission.json       (Mission incl. waypoints)
 *
 * Version 1 exports only the JSON parts as a single manifest file. The app is NOT
 * offline-capable yet: map tiles still require the network.
 */
import { MAP_COORDINATE_CONVENTION } from "../config/marsProjection";
import type { Hazard, Mission } from "../types/api";

export const MISSION_PACKAGE_SCHEMA_VERSION = 1;

export interface MissionPackageMetadata {
  schema: "mars-explorer/mission-package";
  schemaVersion: number;
  createdAt: string;
  app: { name: string; version: string };
  coordinateConvention: typeof MAP_COORDINATE_CONVENTION;
  contents: {
    mission: boolean;
    hazards: number;
    imagery: "NOT_INCLUDED";
    dem: "NOT_INCLUDED";
    terrain: "NOT_INCLUDED";
  };
  offlineReady: false;
}

export interface MissionPackage {
  "metadata.json": MissionPackageMetadata;
  "mission.json": Mission;
  "hazards.json": Hazard[];
}

export function buildMissionPackage(mission: Mission, hazards: Hazard[], now = new Date()): MissionPackage {
  const missionHazards = hazards.filter((h) => h.mission === mission.id);
  return {
    "metadata.json": {
      schema: "mars-explorer/mission-package",
      schemaVersion: MISSION_PACKAGE_SCHEMA_VERSION,
      createdAt: now.toISOString(),
      app: { name: "Nova", version: "0.5.0" },
      coordinateConvention: MAP_COORDINATE_CONVENTION,
      contents: {
        mission: true,
        hazards: missionHazards.length,
        imagery: "NOT_INCLUDED",
        dem: "NOT_INCLUDED",
        terrain: "NOT_INCLUDED",
      },
      offlineReady: false,
    },
    "mission.json": mission,
    "hazards.json": missionHazards,
  };
}

export function validateMissionPackage(pkg: unknown): string[] {
  const errors: string[] = [];
  if (typeof pkg !== "object" || pkg === null) return ["package is not an object"];
  const p = pkg as Record<string, unknown>;
  const meta = p["metadata.json"] as Partial<MissionPackageMetadata> | undefined;
  if (!meta || meta.schema !== "mars-explorer/mission-package") errors.push("metadata.json: wrong or missing schema");
  if (meta && meta.schemaVersion !== MISSION_PACKAGE_SCHEMA_VERSION) errors.push("metadata.json: unsupported schemaVersion");
  if (!p["mission.json"] || typeof p["mission.json"] !== "object") errors.push("mission.json missing");
  if (!Array.isArray(p["hazards.json"])) errors.push("hazards.json must be an array");
  return errors;
}

export function downloadJson(filename: string, data: unknown): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
