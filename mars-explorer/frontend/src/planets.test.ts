import { get as getProjection } from "ol/proj";
import { describe, expect, it } from "vitest";

import { getLayerConfig, layersForPlanet } from "./config/mapLayers";
import { mapProjectionFor, registerPlanetProjections } from "./config/planetProjections";
import { PLANETS, PLANET_ORDER, planetE2 } from "./config/planetRegistry";
import { groundResolutionM } from "./config/marsProjection";
import { buildWmtsSource, createMarsMap, describeTileGrid, parseCapabilities } from "./services/marsMapService";
import { useAppStore } from "./store/useAppStore";
import MOON_XML from "./test/fixtures/LRO_WAC_Mosaic_Global_303ppd_v02.xml?raw";

describe("planet registry", () => {
  it("contains the five bodies with Mars as default and Venus experimental", () => {
    expect(PLANET_ORDER).toEqual(["EARTH", "MARS", "MOON", "MERCURY", "VENUS"]);
    expect(useAppStore.getState().planet).toBe("MARS");
    expect(PLANETS.VENUS.status).toBe("EXPERIMENTAL");
    expect(PLANETS.VENUS.mapCrs).toBeNull();
  });

  it("allows browser geolocation only on Earth", () => {
    expect(PLANET_ORDER.filter((p) => PLANETS[p].browserGeolocationAllowed)).toEqual(["EARTH"]);
  });

  it("keeps per-body radii (no shared ellipsoid)", () => {
    const radii = new Set(PLANET_ORDER.map((p) => PLANETS[p].radiusEquatorial));
    expect(radii.size).toBe(5);
    expect(planetE2(PLANETS.MOON)).toBe(0);
    expect(planetE2(PLANETS.MARS)).toBeGreaterThan(0);
  });

  it("every layer belongs to its body's declared map CRS", () => {
    for (const p of ["MARS", "MOON", "MERCURY"] as const) {
      const ls = layersForPlanet(p);
      expect(ls.length).toBeGreaterThan(0);
      for (const l of ls) expect(l.crs).toBe(PLANETS[p].mapCrs);
    }
    expect(layersForPlanet("VENUS")).toEqual([]);
  });
});

describe("projections per body", () => {
  it("registers Moon and Mercury Trek CRS separately from Mars", () => {
    registerPlanetProjections();
    for (const code of ["urn:ogc:def:crs:EPSG::104903", "urn:ogc:def:crs:IAU2000::19900", "urn:ogc:def:crs:EPSG::104905"]) {
      const p = getProjection(code);
      expect(p?.getUnits()).toBe("degrees");
    }
    expect(mapProjectionFor("MOON").getCode()).toBe("urn:ogc:def:crs:EPSG::104903");
    expect(() => mapProjectionFor("VENUS")).toThrow();
  });

  it("computes the scale bar on the Moon's radius, not Mars'", () => {
    const moon = groundResolutionM(1, 0, PLANETS.MOON.radiusEquatorial, 0).ew;
    const mars = groundResolutionM(1, 0).ew;
    expect(moon).toBeCloseTo((Math.PI / 180) * 1_737_400, 3);
    expect(mars / moon).toBeCloseTo(3_396_190 / 1_737_400, 6);
  });
});

describe("Moon WMTS from real NASA Moon Trek capabilities", () => {
  it("builds the WAC source in the Moon CRS", () => {
    const layer = getLayerConfig("moon-lroc-wac-mosaic");
    const g = describeTileGrid(buildWmtsSource(parseCapabilities(MOON_XML, layer.layerId), layer));
    expect(g.projection).toBe("urn:ogc:def:crs:EPSG::104903");
    expect(g.matrixIds).toHaveLength(9);
    expect(g.format).toBe("image/jpeg");
  });

  it("refuses to overlay a lunar layer as if it were Mars", () => {
    const moonLayer = getLayerConfig("moon-lroc-wac-mosaic");
    const asMars = { ...moonLayer, crs: "urn:ogc:def:crs:EPSG::104905" };
    expect(() => buildWmtsSource(parseCapabilities(MOON_XML, moonLayer.layerId), asMars)).toThrowError(
      expect.objectContaining({ code: "UNSUPPORTED_CRS" }),
    );
  });

  it("creates the Moon map view in the Moon CRS", () => {
    const h = createMarsMap(document.createElement("div"), "MOON");
    expect(h.view.getProjection().getCode()).toBe("urn:ogc:def:crs:EPSG::104903");
    h.map.setTarget(undefined);
  });
});

describe("planet switching", () => {
  it("clears the selected point and picks the body's default layer", () => {
    const s = useAppStore.getState();
    s.selectPoint({ lon: 77, lat: 18, crs: "urn:ogc:def:crs:EPSG::104905", layerId: "mola-global-clrshade", pickedAt: "" });
    s.setPlanet("MOON");
    let st = useAppStore.getState();
    expect(st.planet).toBe("MOON");
    expect(st.selectedPoint).toBeNull();
    expect(st.activeLayerId).toBe("moon-lroc-wac-mosaic");
    s.setPlanet("VENUS");
    expect(useAppStore.getState().activeLayerId).toBe("");
    s.setPlanet("MARS");
    st = useAppStore.getState();
    expect(st.activeLayerId).toBe("mola-global-clrshade");
  });
});
