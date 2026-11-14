import { get as getProjection, transform } from "ol/proj";
import { describe, expect, it } from "vitest";

import {
  MARS_2000_ESRI,
  MARS_EQUATORIAL_RADIUS_M,
  MARS_POLAR_RADIUS_M,
  TREK_DECLARED_CRS,
  formatLat,
  formatLon,
  groundResolutionM,
  lonTo360,
  meridionalRadius,
  niceScaleBar,
  normalizeLon180,
  registerMarsProjections,
} from "./marsProjection";

describe("Mars 2000 constants", () => {
  it("rf reproduces the IAU 2000 polar radius 3376200 m", () => {
    expect(MARS_POLAR_RADIUS_M).toBeCloseTo(3_376_200, 1);
  });
});

describe("projection registration", () => {
  it("registers the exact Trek CRS identifier in degrees", () => {
    const p = registerMarsProjections();
    expect(p.getCode()).toBe(TREK_DECLARED_CRS);
    expect(p.getUnits()).toBe("degrees");
    expect(p.getExtent()).toEqual([-180, -90, 180, 90]);
    expect(p.canWrapX()).toBe(true);
    expect(getProjection(MARS_2000_ESRI)).not.toBeNull();
  });

  it("Trek scale denominators map to 0.703125 deg/px at level 0 with OpenLayers' metersPerUnit", () => {
    // Level 0 of the Trek default028mm matrix set: ScaleDenominator 2.7922763629807472E+08,
    // 2x1 tiles of 256 px over 360 x 180 degrees -> 360 / 512 = 0.703125 deg/px.
    // NASA's denominators were computed with a metres-per-degree constant that differs from
    // OpenLayers' (2*pi*6370997/360) by ~2e-6 relative. Over a full 256-tile-wide matrix that
    // is < 0.1 px, so tiles align; we assert the relative error stays below 1e-5.
    const p = registerMarsProjections();
    const res = (2.7922763629807472e8 * 0.28e-3) / p.getMetersPerUnit()!;
    expect(Math.abs(res / 0.703125 - 1)).toBeLessThan(1e-5);
    expect(Math.abs(res - 0.703125) * 512 * 128).toBeLessThan(0.1); // drift in px across level 7
  });

  it("transforms between the Trek CRS and ESRI:104905 as identity (same parameters)", () => {
    registerMarsProjections();
    const [x, y] = transform([77.45, 18.44], TREK_DECLARED_CRS, MARS_2000_ESRI);
    expect(x).toBeCloseTo(77.45, 9);
    expect(y).toBeCloseTo(18.44, 9);
  });
});

describe("longitude helpers", () => {
  it.each([
    [0, 0],
    [180, -180],
    [270, -90],
    [360, 0],
    [-190, 170],
    [77.45, 77.45],
    [-540, -180],
  ])("normalizeLon180(%f) = %f", (input, expected) => {
    expect(normalizeLon180(input)).toBeCloseTo(expected, 9);
  });

  it("converts to 0..360", () => {
    expect(lonTo360(-90)).toBe(270);
    expect(lonTo360(77.45)).toBeCloseTo(77.45, 9);
  });

  it("rejects non-finite longitudes", () => {
    expect(() => normalizeLon180(Number.NaN)).toThrow();
  });

  it("formats hemispheres explicitly", () => {
    expect(formatLat(-4.5, 2)).toBe("4.50° S");
    expect(formatLon(-77.45, "180", 2)).toBe("77.45° W");
    expect(formatLon(-77.45, "360", 2)).toBe("282.55° E");
  });
});

describe("ground resolution on the Mars ellipsoid", () => {
  it("at the equator, east-west = rad(res) * a", () => {
    const g = groundResolutionM(0.703125, 0);
    expect(g.ew).toBeCloseTo((0.703125 * Math.PI * MARS_EQUATORIAL_RADIUS_M) / 180, 3);
  });

  it("north-south uses the meridional radius b^2/a at the equator", () => {
    const g = groundResolutionM(1, 0);
    const b = MARS_POLAR_RADIUS_M;
    expect(meridionalRadius(0)).toBeCloseTo((b * b) / MARS_EQUATORIAL_RADIUS_M, 3);
    expect(g.ns).toBeCloseTo((Math.PI / 180) * ((b * b) / MARS_EQUATORIAL_RADIUS_M), 3);
  });

  it("east-west size halves (approximately) at 60 degrees", () => {
    const eq = groundResolutionM(1, 0).ew;
    const at60 = groundResolutionM(1, 60).ew;
    expect(at60 / eq).toBeGreaterThan(0.5);
    expect(at60 / eq).toBeLessThan(0.505);
  });

  it("picks a nice scale bar length", () => {
    const s = niceScaleBar(37, 120); // max 4440 m
    expect(s.meters).toBe(2000);
    expect(s.px).toBeCloseTo(2000 / 37, 6);
  });
});
