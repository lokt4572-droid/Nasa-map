import { describe, expect, it } from "vitest";

import { layersForPlanet } from "../config/mapLayers";
import { PLANETS } from "../config/planetRegistry";
import { autoLayerChanges } from "./adaptiveLayers";
import mapControlsSource from "../components/map/MapControls.tsx?raw";
import { getLayerConfig } from "../config/mapLayers";
import { bboxAreaKm2, classifyDem, coverageRegions, unionBBox } from "./coverageCatalog";

describe("coverage catalogue", () => {
  it("is built from the layer catalogue; Jezero is one region among several", () => {
    const regions = coverageRegions("MARS");
    const ids = regions.map((r) => r.id);
    expect(ids).toEqual(expect.arrayContaining(["jezero", "gale", "gusev", "meridiani", "phoenix", "insight"]));
    expect(regions.length).toBeGreaterThanOrEqual(6);
    const jez = regions.find((r) => r.id === "jezero")!;
    expect(jez.datasets.map((d) => d.instrument)).toEqual(["HiRISE", "CTX"]); // finest pyramid first
    for (const r of regions) {
      expect(r.center.lon).toBeGreaterThanOrEqual(r.bbox.west);
      expect(r.center.lon).toBeLessThanOrEqual(r.bbox.east);
      for (const d of r.datasets) {
        expect(d.coverage).toBe("regional");
        expect(d.crs).toBe("urn:ogc:def:crs:EPSG::104905");
        expect(d.capabilitiesUrl).toMatch(/^https:\/\/trek\.nasa\.gov\/tiles\/Mars\/EQ\/.+\/WMTSCapabilities\.xml$/);
        expect(d.acquisition).toBeTruthy(); // stated or explicitly "not stated"
      }
    }
  });

  it("every regional Mars layer belongs to a region (nothing hidden from the explorer)", () => {
    const regional = layersForPlanet("MARS").filter((l) => l.coverage === "regional");
    expect(regional.every((l) => l.region)).toBe(true);
  });

  it("bodies without regional datasets have an empty explorer", () => {
    expect(coverageRegions("MOON")).toEqual([]);
    expect(coverageRegions("MERCURY")).toEqual([]);
  });

  it("auto high-res switching works for any catalogued region, not just Jezero", () => {
    const mars = layersForPlanet("MARS");
    const states = Object.fromEntries(mars.map((l) => [l.id, { visible: l.defaultEnabled }]));
    const b = getLayerConfig("gale-hirise-mosaic").bbox; // inside both Gale mosaics
    const c = [(b.west + b.east) / 2, (b.south + b.north) / 2] as const;
    const res = 0.0005;
    const ext = [c[0] - 0.1, c[1] - 0.05, c[0] + 0.1, c[1] + 0.05];
    const on = autoLayerChanges(mars, states, ext, res, true).map((c) => c.id);
    expect(on).toEqual(expect.arrayContaining(["gale-hirise-mosaic", "gale-ctx-mosaic"]));
    expect(on.some((id) => id.startsWith("jezero"))).toBe(false);
  });

  it("geometry helpers", () => {
    expect(unionBBox([{ west: 0, south: 0, east: 1, north: 1 }, { west: -1, south: 0.5, east: 0.5, north: 2 }])).toEqual({ west: -1, south: 0, east: 1, north: 2 });
    // 1 x 1 degree at the equator on Mars ~ 59.3 km x 59.3 km
    expect(bboxAreaKm2({ west: 0, south: 0, east: 1, north: 1 }, PLANETS.MARS.radiusEquatorial)).toBeCloseTo(3513, -1);
  });

  it("DEM availability is classified from registered DEMs, never assumed", () => {
    expect(classifyDem({ datasets: [], terrain_analysis_status: "NO DATA" }).status).toBe("NONE");
    const mola = { name: "mola-global", resolution_meters: 14817.8 } as never;
    const r = classifyDem({ datasets: [mola], terrain_analysis_status: "AVAILABLE" });
    expect(r.status).toBe("REGIONAL_ONLY");
    expect(r.label).toMatch(/14\.8 km\/cell/);
    const ctxDtm = { name: "ctx-dtm", resolution_meters: 20 } as never;
    expect(classifyDem({ datasets: [mola, ctxDtm], terrain_analysis_status: "AVAILABLE" }).status).toBe("LOCAL_DEM");
  });

  it("the standalone JEZERO map button is gone", () => {
    expect(mapControlsSource).not.toMatch(/JEZERO/);
    expect(mapControlsSource).toMatch(/COVERAGE/);
  });
});
