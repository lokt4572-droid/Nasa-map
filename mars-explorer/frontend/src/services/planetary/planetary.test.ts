import { describe, expect, it } from "vitest";

import { CESIUM_BODIES, cesiumBodyFor, cesiumStatus, describeIonError, liveCesiumViewers } from "./cesiumSceneService";
import { centricToGeodetic, geodeticToCentric, localOffsetMeters, lonDelta, sphereDistance, splitAtSeam, wrapLon180, wrapLon360 } from "./planetaryCoordinateService";

const MARS = { a: 3_396_190, b: 3_376_200 };
const MOON = { a: 1_737_400, b: 1_737_400 };
const EARTH = { a: 6_378_137, b: 6_356_752.314245 };

describe("planetary coordinates", () => {
  it("latitude types agree at the equator and poles and round-trip elsewhere", () => {
    for (const shape of [MARS, MOON, EARTH]) {
      expect(geodeticToCentric(0, shape)).toBe(0);
      expect(geodeticToCentric(90, shape)).toBe(90);
      expect(geodeticToCentric(-90, shape)).toBe(-90);
      for (const lat of [-80, -45, -4.6, 18.44, 60]) expect(centricToGeodetic(geodeticToCentric(lat, shape), shape)).toBeCloseTo(lat, 9);
    }
  });

  it("Mars: planetographic 45° is planetocentric 44.66° (control value from the flattening)", () => {
    // tan(c) = (b/a)^2 tan(g) -> atan(0.988262...) = 44.6617°
    expect(geodeticToCentric(45, MARS)).toBeCloseTo(44.6617, 3);
    expect(Math.abs(geodeticToCentric(45, MARS) - 45)).toBeLessThan(0.35);
  });

  it("Earth: geodetic 45° is geocentric 44.8076° (WGS 84 control value)", () => {
    expect(geodeticToCentric(45, EARTH)).toBeCloseTo(44.8076, 3);
  });

  it("Moon is a sphere: both latitude types are identical", () => {
    for (const lat of [-89, -30, 12.5, 77]) expect(geodeticToCentric(lat, MOON)).toBeCloseTo(lat, 12);
  });

  it("wraps longitudes in both conventions", () => {
    expect(wrapLon180(190)).toBe(-170);
    expect(wrapLon180(-190)).toBe(170);
    expect(wrapLon180(360)).toBe(0);
    expect(wrapLon360(-10)).toBe(350);
    expect(wrapLon360(725)).toBe(5);
    expect(lonDelta(350, 10)).toBe(20);
    expect(lonDelta(10, 350)).toBe(-20);
    expect(lonDelta(-179, 179)).toBe(-2);
  });

  it("local metric offsets are continuous across the seam", () => {
    const r = 3_389_500;
    const o = localOffsetMeters({ lon: 179.9, lat: 0 }, { lon: -179.9, lat: 0 }, r);
    expect(o.east).toBeCloseTo((0.2 * Math.PI * r) / 180, 3);
    expect(o.north).toBe(0);
    const n = localOffsetMeters({ lon: 10, lat: 60 }, { lon: 11, lat: 60 }, r);
    expect(n.east).toBeCloseTo(((Math.PI * r) / 180) * 0.5, 0); // cos 60°
  });

  it("sphere distance: a quarter circumference and a seam crossing", () => {
    const r = 1_737_400;
    expect(sphereDistance({ lon: 0, lat: 0 }, { lon: 90, lat: 0 }, r)).toBeCloseTo((Math.PI * r) / 2, 3);
    expect(sphereDistance({ lon: 0, lat: 0 }, { lon: 0, lat: 90 }, r)).toBeCloseTo((Math.PI * r) / 2, 3);
    expect(sphereDistance({ lon: 359, lat: 0 }, { lon: 1, lat: 0 }, r)).toBeCloseTo((2 * Math.PI * r) / 180, 3);
  });

  it("splits a line at the ±180 seam with the crossing point on both sides", () => {
    const parts = splitAtSeam([[170, 0], [178, 4], [-178, 6], [-170, 10]]);
    expect(parts).toHaveLength(2);
    expect(parts[0]![parts[0]!.length - 1]).toEqual([180, 5]);
    expect(parts[1]![0]).toEqual([-180, 5]);
    expect(parts[1]![parts[1]!.length - 1]).toEqual([-170, 10]);
    // a route planned in 0..360 longitudes across 180
    expect(splitAtSeam([[179, 0], [181, 0]])).toEqual([[[179, 0], [180, 0]], [[-180, 0], [-179, 0]]]);
    // crossing 0°/360° is NOT a map seam in -180..180
    expect(splitAtSeam([[359, 1], [1, 1]])).toEqual([[[-1, 1], [1, 1]]]);
    expect(splitAtSeam([[10, 0], [20, 0]])).toHaveLength(1);
    expect(splitAtSeam([])).toEqual([]);
  });
});

describe("Cesium scene configuration", () => {
  it("uses the documented asset ids and body ellipsoids, never WGS 84", () => {
    expect(CESIUM_BODIES.MARS.assetId).toBe(3644333);
    expect(CESIUM_BODIES.MARS.ellipsoid).toBe("MARS");
    expect(CESIUM_BODIES.MARS.crs).toBe("IAU_2015:49901");
    expect(CESIUM_BODIES.MOON.assetId).toBe(2684829);
    expect(CESIUM_BODIES.MOON.ellipsoid).toBe("MOON");
  });

  it("Mars carries the estimated-colour provenance notice", () => {
    expect(CESIUM_BODIES.MARS.provenanceNotice).toMatch(/ESTIMATED/);
    expect(CESIUM_BODIES.MARS.provenanceNotice).toMatch(/not verified natural colour/);
  });

  it("only Mars and Moon have Cesium 3D Tiles", () => {
    expect(cesiumBodyFor("MARS")?.planet).toBe("MARS");
    expect(cesiumBodyFor("MOON")?.planet).toBe("MOON");
    for (const p of ["EARTH", "MERCURY", "VENUS"] as const) expect(cesiumBodyFor(p)).toBeNull();
  });

  it("without a token the status is REQUIRES_USER_CONFIGURATION; with one it is never 'working'", () => {
    for (const t of [undefined, "", "   "]) expect(cesiumStatus(t)).toMatchObject({ status: "REQUIRES_USER_CONFIGURATION", tokenPresent: false });
    expect(cesiumStatus("abc")).toMatchObject({ status: "CONFIGURED_NOT_VERIFIED", tokenPresent: true });
  });

  it("explains ion failures without echoing a token", () => {
    expect(describeIonError({ statusCode: 401 })).toMatch(/rejected the token/);
    expect(describeIonError({ statusCode: 404 })).toMatch(/Asset Depot/);
    expect(describeIonError({ statusCode: 429 })).toMatch(/quota/);
    expect(describeIonError(new Error("boom"))).toMatch(/boom/);
  });

  it("no viewer is alive before a scene is created", () => {
    expect(liveCesiumViewers()).toBe(0);
  });
});
