/**
 * Mission Data Package as ZIP (format "mars-explorer/mission-package-zip", version 1).
 *
 *   mission_package/
 *   ├── package.json         manifest: format, version, planet, crs, created_at, files[{path, sha256, bytes}]
 *   ├── metadata/app.json    app + coordinate convention
 *   ├── imagery/README.txt   no third-party tiles are packaged (distribution terms)
 *   ├── dem/datasets.json    references to registered DEMs (metadata only, no rasters)
 *   ├── terrain/README.txt
 *   ├── hazards/hazards.json
 *   ├── routes/routes.json
 *   └── mission/mission.json
 *
 * Import validates manifest, format version, per-file SHA-256, JSON integrity, planet
 * and CRS before anything is registered. Registration uses client_id, so importing the
 * same package twice does not create duplicates.
 */
import { strFromU8, strToU8, unzipSync, zipSync } from "fflate";

import { MAP_COORDINATE_CONVENTION } from "../config/marsProjection";
import { PLANETS, type PlanetId } from "../config/planetRegistry";
import type { Dataset, Hazard, Mission } from "../types/api";

export const ZIP_FORMAT = "mars-explorer/mission-package-zip";
export const ZIP_FORMAT_VERSION = 1;
const ROOT = "mission_package/";

export interface ManifestFile {
  path: string;
  sha256: string;
  bytes: number;
}
export interface Manifest {
  format: string;
  format_version: number;
  planet: PlanetId;
  crs: string;
  created_at: string;
  mission_client_id: string;
  files: ManifestFile[];
  offline_ready: false;
}

async function sha256(data: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new Uint8Array(data));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function buildMissionZip(opts: {
  mission: Mission & { client_id?: string | null };
  hazards: Hazard[];
  routes?: unknown[];
  datasets?: Dataset[];
  planet?: PlanetId;
  now?: Date;
}): Promise<{ zip: Uint8Array; manifest: Manifest }> {
  const planet = opts.planet ?? "MARS";
  const crs = PLANETS[planet].mapCrs ?? PLANETS[planet].coordinateSystem;
  const clientId = opts.mission.client_id ?? crypto.randomUUID();
  const missionHazards = opts.hazards.filter((h) => h.mission === opts.mission.id);
  const json = (v: unknown) => strToU8(JSON.stringify(v, null, 2));
  const content: Record<string, Uint8Array> = {
    "metadata/app.json": json({ app: "Nova", version: "0.5", coordinate_convention: MAP_COORDINATE_CONVENTION }),
    "imagery/README.txt": strToU8("No imagery tiles are included: NASA Trek / OSM tiles are streamed, not redistributed.\n"),
    "dem/datasets.json": json((opts.datasets ?? []).filter((d) => (d.planet ?? "MARS") === planet).map((d) => ({ name: d.name, checksum: d.checksum, crs_name: d.crs_name, vertical_datum: d.vertical_datum, resolution_meters: d.resolution_meters }))),
    "terrain/README.txt": strToU8("Derived terrain products are recomputed from the registered DEM; none are included.\n"),
    "hazards/hazards.json": json(missionHazards),
    "routes/routes.json": json(opts.routes ?? []),
    "mission/mission.json": json({ ...opts.mission, client_id: clientId }),
  };
  const files: ManifestFile[] = [];
  for (const [path, data] of Object.entries(content)) files.push({ path, sha256: await sha256(data), bytes: data.length });
  const manifest: Manifest = {
    format: ZIP_FORMAT,
    format_version: ZIP_FORMAT_VERSION,
    planet,
    crs,
    created_at: (opts.now ?? new Date()).toISOString(),
    mission_client_id: clientId,
    files,
    offline_ready: false,
  };
  const entries: Record<string, Uint8Array> = { [`${ROOT}package.json`]: json(manifest) };
  for (const [p, d] of Object.entries(content)) entries[`${ROOT}${p}`] = d;
  return { zip: zipSync(entries, { level: 6 }), manifest };
}

export interface ImportResult {
  ok: boolean;
  errors: string[];
  warnings: string[];
  manifest: Manifest | null;
  mission: (Mission & { client_id: string }) | null;
  hazards: Hazard[];
}

export async function readMissionZip(data: Uint8Array, expectedPlanet?: PlanetId): Promise<ImportResult> {
  const res: ImportResult = { ok: false, errors: [], warnings: [], manifest: null, mission: null, hazards: [] };
  let files: Record<string, Uint8Array>;
  try {
    files = unzipSync(data);
  } catch {
    res.errors.push("Not a valid ZIP archive");
    return res;
  }
  const manRaw = files[`${ROOT}package.json`];
  if (!manRaw) {
    res.errors.push("package.json manifest missing");
    return res;
  }
  let m: Manifest;
  try {
    m = JSON.parse(strFromU8(manRaw)) as Manifest;
  } catch {
    res.errors.push("package.json is not valid JSON");
    return res;
  }
  res.manifest = m;
  if (m.format !== ZIP_FORMAT) res.errors.push(`Unknown package format ${String(m.format)}`);
  if (m.format_version !== ZIP_FORMAT_VERSION) res.errors.push(`Unsupported format_version ${String(m.format_version)} (expected ${ZIP_FORMAT_VERSION})`);
  if (!m.planet || !(m.planet in PLANETS)) res.errors.push(`Unknown planet ${String(m.planet)}`);
  else {
    if (expectedPlanet && m.planet !== expectedPlanet) res.errors.push(`Package is for ${m.planet}, current body is ${expectedPlanet}`);
    const expectedCrs = PLANETS[m.planet].mapCrs ?? PLANETS[m.planet].coordinateSystem;
    if (m.crs !== expectedCrs) res.errors.push(`Package CRS ${m.crs} does not match ${m.planet} (${expectedCrs})`);
  }
  for (const f of m.files ?? []) {
    const d = files[`${ROOT}${f.path}`];
    if (!d) {
      res.errors.push(`Missing file ${f.path}`);
      continue;
    }
    if (d.length !== f.bytes || (await sha256(d)) !== f.sha256) res.errors.push(`Checksum mismatch: ${f.path}`);
  }
  const listed = new Set((m.files ?? []).map((f) => `${ROOT}${f.path}`));
  for (const name of Object.keys(files)) {
    if (name !== `${ROOT}package.json` && !name.endsWith("/") && !listed.has(name)) res.warnings.push(`Unlisted file ignored: ${name}`);
  }
  if (res.errors.length) return res;
  try {
    res.mission = JSON.parse(strFromU8(files[`${ROOT}mission/mission.json`]!));
    res.hazards = JSON.parse(strFromU8(files[`${ROOT}hazards/hazards.json`]!));
  } catch {
    res.errors.push("mission.json or hazards.json is not valid JSON");
    return res;
  }
  for (const h of res.hazards) {
    if (h.crs && m.planet === "MARS" && !/104905|104971|49900/.test(h.crs)) res.warnings.push(`Hazard "${h.title}" uses CRS ${h.crs}`);
  }
  res.ok = true;
  return res;
}
