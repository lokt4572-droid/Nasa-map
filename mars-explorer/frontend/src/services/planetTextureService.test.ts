import { describe, expect, it } from "vitest";

import { PLANET_TEXTURES, textureFor } from "../config/planetTextures";
import { PLANETS } from "../config/planetRegistry";
import { useAppStore } from "../store/useAppStore";
import { buildEllipsoidArrays, graticule, lonLatToXYZ, placeTiles, xyzToLonLat } from "./planetTextureService";

const M = PLANETS.MARS;
const E = PLANETS.EARTH;

describe("ellipsoid geometry", () => {
  it("lon/lat -> xyz -> lon/lat round-trips (geodetic ellipsoid and sphere)", () => {
    for (const [a, b, mode] of [
      [M.radiusEquatorial, M.radiusPolar, "GEODETIC"],
      [E.radiusEquatorial, E.radiusPolar, "GEODETIC"],
      [PLANETS.MOON.radiusEquatorial, PLANETS.MOON.radiusPolar, "SPHERE"],
    ] as const) {
      for (const [lon, lat] of [[0, 0], [77.43, 18.47], [-120, -45], [179.9, 89], [-180, -89.5]]) {
        const [x, y, z] = lonLatToXYZ(lon!, lat!, a, b, mode);
        const r = xyzToLonLat(x, y, z, a, b, mode);
        expect(r.lat).toBeCloseTo(lat!, 9);
        expect(((r.lon - lon! + 540) % 360) - 180).toBeCloseTo(0, 9);
      }
    }
  });

  it("uses the body's real flattening (not a sphere) and correct axes", () => {
    const [, yPole] = lonLatToXYZ(0, 90, M.radiusEquatorial, M.radiusPolar, "GEODETIC");
    expect(yPole).toBeCloseTo(M.radiusPolar / M.radiusEquatorial, 9); // polar radius / a
    expect(lonLatToXYZ(0, 0, 1, 1, "SPHERE")).toEqual([1, 0, -0]);
    const east = lonLatToXYZ(90, 0, 1, 1, "SPHERE");
    expect(east[2]).toBeCloseTo(-1); // lon +90 E -> -Z (east to the right seen from outside)
  });

  it("geodetic and planetocentric latitude differ as expected on Mars (documented, < 0.35 deg)", () => {
    const [x, y, z] = lonLatToXYZ(0, 45, M.radiusEquatorial, M.radiusPolar, "GEODETIC");
    const centric = (Math.atan2(y, Math.hypot(x, z)) * 180) / Math.PI;
    expect(45 - centric).toBeGreaterThan(0.3);
    expect(45 - centric).toBeLessThan(0.35);
  });

  it("mesh: equirectangular UVs, seam duplicated, normals unit length", () => {
    const g = buildEllipsoidArrays(1, 0.99, "GEODETIC", 8, 4);
    expect(g.positions.length).toBe(9 * 5 * 3);
    expect(g.indices.length).toBe(8 * 4 * 6);
    expect([g.uvs[0], g.uvs[1]]).toEqual([0, 1]); // lon -180, lat 90 -> top-left of the image
    expect([g.uvs[8 * 2], g.uvs[8 * 2 + 1]]).toEqual([1, 1]); // lon +180 duplicate
    for (let i = 0; i < g.normals.length; i += 3) {
      expect(Math.hypot(g.normals[i]!, g.normals[i + 1]!, g.normals[i + 2]!)).toBeCloseTo(1, 5);
    }
  });

  it("graticule lies just above the surface", () => {
    const lines = graticule(1, 1, "SPHERE", 30, 0.002);
    expect(lines.length).toBe(5 + 12);
    expect(Math.hypot(...(lines[0]![0] as [number, number, number]))).toBeCloseTo(1.002, 6);
  });
});

describe("texture mosaic placement", () => {
  it("places NASA Trek level-2 tiles (8x4 of 256 px) into a 2048x1024 equirectangular canvas", () => {
    const res = 0.703125 / 4;
    const p = placeTiles(2, [-180, 90], res, 256, { minX: 0, maxX: 7, minY: 0, maxY: 3 });
    expect([p.width, p.height, p.tiles.length]).toEqual([2048, 1024, 32]);
    expect(p.tiles[0]).toMatchObject({ x: 0, y: 0, dx: 0, dy: 0 });
    expect(p.tiles[31]).toMatchObject({ x: 7, y: 3, dx: 1792, dy: 768 });
  });

  it("respects a grid origin that is not at -180/90", () => {
    const p = placeTiles(0, [-90, 45], 1, 10, { minX: 0, maxX: 0, minY: 0, maxY: 0 });
    expect(p.tiles[0]).toMatchObject({ dx: 90, dy: 45 });
  });
});

describe("texture catalog", () => {
  it("Earth, Mars, Moon, Mercury have documented textures; Venus has none", () => {
    for (const id of ["EARTH", "MARS", "MOON", "MERCURY"] as const) {
      const t = textureFor(id)!;
      expect(t.projection).toMatch(/Equirectangular/);
      for (const f of [t.attribution, t.sourceUrl, t.date, t.coverage, t.nativeResolution, t.verifiedAt]) expect(f).toBeTruthy();
    }
    expect(textureFor("VENUS")).toBeNull();
    expect(PLANET_TEXTURES.MARS!.source.kind).toBe("TREK_WMTS");
    expect(JSON.stringify(PLANET_TEXTURES)).not.toMatch(/3857|GoogleMaps/); // never Web Mercator
  });

  it("Mars uses the Viking colorized mosaic; Mercury enhanced colour is labelled as such", () => {
    expect(JSON.stringify(PLANET_TEXTURES.MARS)).toContain("Mars_Viking_MDIM21_ClrMosaic_global_232m");
    expect(PLANET_TEXTURES.MERCURY!.notes).toMatch(/Enhanced colour/);
  });
});

describe("view mode", () => {
  it("globe mode survives switching to a body with a texture and falls back to the map otherwise", () => {
    const s = useAppStore.getState();
    s.setPlanet("MARS");
    s.setBodyView("GLOBE");
    s.setPlanet("MOON");
    expect(useAppStore.getState().bodyView).toBe("GLOBE");
    s.setPlanet("VENUS");
    expect(useAppStore.getState().bodyView).toBe("MAP");
    s.setPlanet("MARS");
  });
});
