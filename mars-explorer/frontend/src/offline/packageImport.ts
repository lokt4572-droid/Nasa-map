/**
 * Restore a validated mission package into the backend (v0.4).
 *
 * Never overwrites silently:
 *  - a record whose client_id already exists is NOT changed; if its content differs from the
 *    package it is reported as KEPT_SERVER_COPY (a conflict the user can see);
 *  - the only change made to an existing record is re-linking a hazard that lost its mission
 *    (its mission was deleted) to the restored mission — reported as RELINKED.
 */
import { ApiError, apiRequest } from "../services/api";
import type { Hazard, Mission } from "../types/api";
import type { ImportResult } from "./zipPackage";

export type RecordOutcome = "CREATED" | "UNCHANGED" | "KEPT_SERVER_COPY" | "RELINKED" | "FAILED";

export interface RestoreReport {
  mission: { id: number | null; outcome: RecordOutcome; differences: string[] };
  hazards: { title: string; id: number | null; outcome: RecordOutcome; differences: string[]; error?: string }[];
  counts: Record<RecordOutcome, number>;
}

/** Deterministic UUID-shaped id from text (re-importing a package does not duplicate hazards). */
export async function stableUuid(text: string): Promise<string> {
  const h = [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text)))].map((b) => b.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-5${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20, 32)}`;
}

const MISSION_FIELDS = ["name", "description", "status"] as const;
const HAZARD_FIELDS = ["title", "hazard_type", "severity", "source", "radius_m", "description", "lon_east_deg", "lat_deg", "crs"] as const;

export function differences<T extends object>(pkg: T, server: T, fields: readonly (keyof T)[]): string[] {
  return fields.filter((f) => {
    const a = pkg[f];
    const b = server[f];
    if (typeof a === "number" && typeof b === "number") return Math.abs(a - b) > 1e-9;
    return (a ?? null) !== (b ?? null) && !(a === undefined || a === null);
  }).map(String);
}

type Req = typeof apiRequest;
type Replayable<T> = T & { replayed?: boolean };

export async function restoreMissionPackage(res: ImportResult, request: Req = apiRequest): Promise<RestoreReport> {
  if (!res.ok || !res.mission || !res.manifest) throw new Error("Package was not validated");
  const counts: Record<RecordOutcome, number> = { CREATED: 0, UNCHANGED: 0, KEPT_SERVER_COPY: 0, RELINKED: 0, FAILED: 0 };
  const m = res.mission;
  const mission = await request<Replayable<Mission>>("/missions/", {
    method: "POST",
    body: { name: m.name, description: m.description, status: m.status, client_id: res.manifest.mission_client_id },
  });
  const mDiff = mission.replayed ? differences(m as Mission, mission, MISSION_FIELDS) : [];
  const mOutcome: RecordOutcome = !mission.replayed ? "CREATED" : mDiff.length ? "KEPT_SERVER_COPY" : "UNCHANGED";
  counts[mOutcome]++;
  const report: RestoreReport = { mission: { id: mission.id, outcome: mOutcome, differences: mDiff }, hazards: [], counts };

  for (const h of res.hazards) {
    const clientId = (h as Hazard).client_id ?? (await stableUuid(`${res.manifest.mission_client_id}:${h.id}`));
    const body: Record<string, unknown> = { ...h, mission: mission.id, client_id: clientId };
    for (const k of ["id", "version", "created_at", "updated_at", "replayed"]) delete body[k];
    try {
      const saved = await request<Replayable<Hazard>>("/hazards/", { method: "POST", body });
      if (!saved.replayed) {
        counts.CREATED++;
        report.hazards.push({ title: h.title, id: saved.id, outcome: "CREATED", differences: [] });
        continue;
      }
      const diff = differences(h as Hazard, saved, HAZARD_FIELDS);
      if (saved.mission === null && !diff.length) {
        // Orphaned by a deleted mission: re-link it, guarded by its version (409 if it changed meanwhile).
        await request(`/hazards/${saved.id}/`, { method: "PATCH", body: { mission: mission.id, version: saved.version } });
        counts.RELINKED++;
        report.hazards.push({ title: h.title, id: saved.id, outcome: "RELINKED", differences: [] });
      } else {
        const outcome: RecordOutcome = diff.length ? "KEPT_SERVER_COPY" : "UNCHANGED";
        counts[outcome]++;
        report.hazards.push({ title: h.title, id: saved.id, outcome, differences: diff });
      }
    } catch (err) {
      counts.FAILED++;
      report.hazards.push({ title: h.title, id: null, outcome: "FAILED", differences: [], error: err instanceof ApiError ? `${err.code}: ${err.message}` : String(err) });
    }
  }
  return report;
}

export function summarizeRestore(r: RestoreReport, name: string): string {
  const c = r.counts;
  const parts = [`Mission "${name}": ${r.mission.outcome.replaceAll("_", " ").toLowerCase()}`];
  parts.push(`hazards: ${c.CREATED - (r.mission.outcome === "CREATED" ? 1 : 0)} created, ${c.UNCHANGED - (r.mission.outcome === "UNCHANGED" ? 1 : 0)} already present, ${c.RELINKED} re-linked, ${c.KEPT_SERVER_COPY - (r.mission.outcome === "KEPT_SERVER_COPY" ? 1 : 0)} kept as on the server (differs from the package), ${c.FAILED} failed`);
  return parts.join("; ") + ".";
}
