/**
 * Map projections for every body that has a NASA Trek map service.
 *
 * The CRS identifiers are registered EXACTLY as each Trek GetCapabilities declares them
 * (checked 2026-11-14), with parameters from the PROJ database:
 *   Moon    urn:ogc:def:crs:EPSG::104903   -> ESRI:104903 GCS_Moon_2000, sphere R = 1 737 400 m
 *   Mercury urn:ogc:def:crs:IAU2000::19900 -> IAU_2015:19900, sphere R = 2 440 530 m
 *           (PROJ ships only the IAU 2015 namespace; see planetRegistry conflicts)
 *   Mars    see marsProjection.ts
 * Each body gets its own projection object: a Mars coordinate can never be shown on a
 * lunar map without an explicit transformation.
 */
import proj4 from "proj4";
import { get as getProjection } from "ol/proj";
import type Projection from "ol/proj/Projection";
import { register } from "ol/proj/proj4";

import { MARS_GEOGRAPHIC_EXTENT, registerMarsProjections } from "./marsProjection";
import { PLANETS, type PlanetId } from "./planetRegistry";

const DEFS: Record<string, string> = {
  "urn:ogc:def:crs:EPSG::104903": "+proj=longlat +R=1737400 +no_defs +type=crs",
  "ESRI:104903": "+proj=longlat +R=1737400 +no_defs +type=crs",
  "urn:ogc:def:crs:IAU2000::19900": "+proj=longlat +R=2440530 +no_defs +type=crs",
  "IAU_2015:19900": "+proj=longlat +R=2440530 +no_defs +type=crs",
};

let registered = false;

export function registerPlanetProjections(): void {
  registerMarsProjections();
  if (!registered) {
    for (const [code, def] of Object.entries(DEFS)) proj4.defs(code, def);
    register(proj4);
    registered = true;
  }
  for (const code of Object.keys(DEFS)) {
    const p = getProjection(code);
    if (!p) throw new Error(`Failed to register projection ${code}`);
    p.setExtent(MARS_GEOGRAPHIC_EXTENT);
    p.setWorldExtent(MARS_GEOGRAPHIC_EXTENT);
    p.setGlobal(true);
  }
}

/** Projection of the body's 2D map (Trek CRS). Throws for bodies without a map service. */
export function mapProjectionFor(planet: PlanetId): Projection {
  registerPlanetProjections();
  const code = PLANETS[planet].mapCrs;
  if (!code) throw new Error(`${planet} has no map service CRS`);
  const p = getProjection(code);
  if (!p) throw new Error(`Projection ${code} not registered`);
  return p;
}
