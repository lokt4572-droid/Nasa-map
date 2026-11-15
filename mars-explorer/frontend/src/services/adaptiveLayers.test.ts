import { beforeEach, describe, expect, it } from "vitest";

import { getLayerConfig, layersForPlanet } from "../config/mapLayers";
import { PLANETS } from "../config/planetRegistry";
import { useAppStore } from "../store/useAppStore";
import {
  autoLayerChanges,
  bboxIntersectsExtent,
  coverageAtView,
  dataAtPoint,
  formatMpp,
  metersPerPixel,
  nativeResolutionDeg,
  regionalMaxResolution,
  shownAtCenter,
  viewScale,
  type LayerView,
} from "./adaptiveLayers";

const MARS = layersForPlanet("MARS");
const R_MARS = PLANETS.MARS.radiusEquatorial;
const ctx = getLayerConfig("jezero-ctx-ortho");
const hirise = getLayerConfig("jezero-hirise-ortho");
const mola = getLayerConfig("mola-global-clrshade");
const JEZ = [77.43, 18.47];
const around = (lon: number, lat: number, res: number, w = 466, h = 212) => [lon - (w / 2) * res, lat - (h / 2) * res, lon + (w / 2) * res, lat + (h / 2) * res];

function states(visible: string[], extra: Record<string, Partial<LayerView>> = {}): Record<string, LayerView> {
  return Object.fromEntries(MARS.map((l) => [l.id, { visible: visible.includes(l.id), ...extra[l.id] }]));
}

describe("view scale and resolution", () => {
  it("classifies global / regional / local on the body's own radius", () => {
    expect(viewScale(0.3515625, R_MARS)).toBe("GLOBAL"); // ~20.8 km/px
    expect(viewScale(0.02197265625, R_MARS)).toBe("REGIONAL"); // ~1.3 km/px
    expect(viewScale(0.0001, R_MARS)).toBe("LOCAL"); // ~6 m/px
    expect(metersPerPixel(1, R_MARS)).toBeCloseTo(59_275, -2);
    expect(viewScale(0.02, PLANETS.MOON.radiusEquatorial)).toBe("REGIONAL"); // ~606 m/px on the Moon
  });

  it("native resolution from the tile grid, else from the verified Trek level count", () => {
    expect(nativeResolutionDeg(mola)).toBeCloseTo(0.703125 / 128);
    expect(nativeResolutionDeg(mola, [0.7, 0.1, 0.005])).toBe(0.005);
    expect(nativeResolutionDeg(hirise)).toBeLessThan(nativeResolutionDeg(ctx));
  });

  it("formats ground resolution", () => {
    expect(formatMpp(20_800)).toBe("21 km/px");
    expect(formatMpp(1300)).toBe("1.3 km/px");
    expect(formatMpp(6)).toBe("6.0 m/px");
    expect(formatMpp(0.25)).toBe("25 cm/px");
  });
});

describe("coverage at the current view", () => {
  it("regional layer: outside view / zoom in to display / in view / overzoomed", () => {
    expect(coverageAtView(ctx, around(0, 0, 0.02), 0.02)).toBe("OUTSIDE_VIEW");
    expect(coverageAtView(ctx, around(JEZ[0]!, JEZ[1]!, 0.3515625), 0.3515625)).toBe("BELOW_DISPLAY_THRESHOLD");
    expect(coverageAtView(ctx, around(JEZ[0]!, JEZ[1]!, 0.0013), 0.0013)).toBe("IN_VIEW");
    const tiny = nativeResolutionDeg(ctx) / 4;
    expect(coverageAtView(ctx, around(JEZ[0]!, JEZ[1]!, tiny), tiny)).toBe("OVERZOOMED");
  });

  it("global layer is always in view and has no display threshold", () => {
    expect(regionalMaxResolution(mola)).toBeUndefined();
    expect(coverageAtView(mola, around(0, 0, 0.3515625), 0.3515625)).toBe("IN_VIEW");
  });

  it("handles views crossing the antimeridian", () => {
    expect(bboxIntersectsExtent({ west: -180, south: -10, east: -170, north: 10 }, [170, -5, 195, 5])).toBe(true);
    expect(bboxIntersectsExtent({ west: 77, south: 18, east: 78, north: 19 }, [170, -5, 195, 5])).toBe(false);
  });
});

describe("auto high-resolution switching", () => {
  const regional = (res: number) => around(JEZ[0]!, JEZ[1]!, res);

  it("switches regional layers on when their coverage is in view and big enough", () => {
    const ch = autoLayerChanges(MARS, states(["mola-global-clrshade"]), regional(0.0013), 0.0013, true);
    expect(ch.map((c) => [c.id, c.visible])).toEqual([
      ["jezero-ctx-ortho", true],
      ["jezero-hirise-ortho", true],
    ]);
  });

  it("does nothing at the global view, and never touches global layers", () => {
    expect(autoLayerChanges(MARS, states(["mola-global-clrshade"]), around(0, 0, 0.35), 0.35, true)).toEqual([]);
    const off = autoLayerChanges(MARS, states([]), regional(0.0013), 0.0013, true);
    expect(off.some((c) => c.id === "mola-global-clrshade")).toBe(false);
  });

  it("switches off only layers it switched on, with hysteresis", () => {
    const st = states(["mola-global-clrshade", "jezero-ctx-ortho", "jezero-hirise-ortho"], {
      "jezero-ctx-ortho": { autoEnabled: true },
    });
    const thr = regionalMaxResolution(ctx)!;
    expect(autoLayerChanges(MARS, st, regional(thr * 1.5), thr * 1.5, true)).toEqual([]); // inside hysteresis band
    const out = autoLayerChanges(MARS, st, around(0, 0, 0.02), 0.02, true);
    expect(out).toEqual([{ id: "jezero-ctx-ortho", visible: false, reason: "coverage left the view" }]); // HiRISE was user-enabled
  });

  it("respects a user's explicit 'off'", () => {
    const st = states(["mola-global-clrshade"], { "jezero-hirise-ortho": { autoSuppressed: true } });
    const ch = autoLayerChanges(MARS, st, regional(0.0013), 0.0013, true);
    expect(ch.map((c) => c.id)).toEqual(["jezero-ctx-ortho"]);
  });

  it("turning auto mode off removes only auto-enabled layers", () => {
    const st = states(["jezero-ctx-ortho", "jezero-hirise-ortho"], { "jezero-ctx-ortho": { autoEnabled: true } });
    expect(autoLayerChanges(MARS, st, regional(0.0013), 0.0013, false).map((c) => c.id)).toEqual(["jezero-ctx-ortho"]);
  });
});

describe("what is shown at the view centre", () => {
  it("names the top-most visible layer and the finest data available", () => {
    const st = states(["mola-global-clrshade", "jezero-ctx-ortho"]);
    const r = shownAtCenter(MARS, st, JEZ[0]!, JEZ[1]!, 0.0013);
    expect(r.shown?.id).toBe("jezero-ctx-ortho");
    expect(r.finest?.id).toBe("jezero-hirise-ortho");
    expect(r.overzoomed).toBe(false);
  });

  it("falls back to the parent where the regional layer has no coverage (no gap, no substitute)", () => {
    const st = states(["mola-global-clrshade", "jezero-ctx-ortho", "jezero-hirise-ortho"]);
    expect(shownAtCenter(MARS, st, -120, -30, 0.0013).shown?.id).toBe("mola-global-clrshade");
  });

  it("a regional layer below its display threshold is not reported as shown", () => {
    const st = states(["mola-global-clrshade", "jezero-ctx-ortho"]);
    expect(shownAtCenter(MARS, st, JEZ[0]!, JEZ[1]!, 0.35).shown?.id).toBe("mola-global-clrshade");
  });

  it("reports overzoom of the shown product", () => {
    const st = states(["mola-global-clrshade"]);
    expect(shownAtCenter(MARS, st, 0, 0, 0.0001).overzoomed).toBe(true);
  });

  it("lists data at a point finest first; Mars products stay distinct", () => {
    const ids = dataAtPoint(MARS, states([]), JEZ[0]!, JEZ[1]!).map((d) => d.layer.id);
    expect(ids[0]).toBe("jezero-hirise-ortho");
    expect(ids).toContain("viking-mdim21-color");
    expect(ids).toContain("themis-day-ir-100m");
    expect(getLayerConfig("themis-day-ir-100m").dataKind).toBe("THERMAL_IR_MOSAIC");
  });
});

describe("store: user choices vs auto mode", () => {
  beforeEach(() => useAppStore.setState({ layers: useAppStore.getState().layers }));

  it("auto changes do not touch the active layer; user 'off' suppresses auto", () => {
    const s = useAppStore.getState();
    const active = s.activeLayerId;
    s.applyAutoLayers([{ id: "jezero-ctx-ortho", visible: true }]);
    let l = useAppStore.getState().layers["jezero-ctx-ortho"]!;
    expect([l.visible, l.autoEnabled]).toEqual([true, true]);
    expect(useAppStore.getState().activeLayerId).toBe(active);
    s.setLayerVisible("jezero-ctx-ortho", false);
    l = useAppStore.getState().layers["jezero-ctx-ortho"]!;
    expect([l.visible, l.autoEnabled, l.autoSuppressed]).toEqual([false, false, true]);
    s.setLayerVisible("jezero-ctx-ortho", true);
    expect(useAppStore.getState().layers["jezero-ctx-ortho"]!.autoSuppressed).toBe(false);
  });

  it("auto high-res setting defaults on", () => {
    expect(useAppStore.getState().settings.autoHighRes).toBe(true);
  });
});
