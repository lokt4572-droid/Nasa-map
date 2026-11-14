import { beforeEach, describe, expect, it, vi } from "vitest";

import HIRISE_XML from "../test/fixtures/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd.xml?raw";
import MOLA_XML from "../test/fixtures/Mars_MGS_MOLA_ClrShade_merge_global_463m.xml?raw";

import { getLayerConfig } from "../config/mapLayers";
import { TREK_DECLARED_CRS } from "../config/marsProjection";
import {
  WmtsLayerError,
  buildWmtsSource,
  clearCapabilitiesCache,
  createMarsMap,
  describeTileGrid,
  fetchCapabilities,
  loadWmtsLayer,
  parseCapabilities,
} from "./marsMapService";

const okFetch = (xml: string) =>
  vi.fn(async () => new Response(xml, { status: 200, headers: { "Content-Type": "application/xml" } })) as unknown as typeof fetch;

beforeEach(() => clearCapabilitiesCache());

describe("WMTS from real NASA Trek capabilities", () => {
  it("builds the MOLA source from GetCapabilities (not hard-coded)", () => {
    const layer = getLayerConfig("mola-global-clrshade");
    const src = buildWmtsSource(parseCapabilities(MOLA_XML, layer.layerId), layer);
    const g = describeTileGrid(src);
    expect(g.projection).toBe(TREK_DECLARED_CRS);
    expect(g.matrixSet).toBe("default028mm");
    expect(g.matrixIds).toEqual(["0", "1", "2", "3", "4", "5", "6", "7"]);
    expect(g.origin).toEqual([-180, 90]);
    expect(g.format).toBe("image/jpeg");
    // 360 deg / 512 px at level 0, halving each level; ~2e-6 relative deviation comes from
    // the metres-per-degree constant NASA used for the scale denominators (see marsProjection.test).
    expect(Math.abs(g.resolutionsDegPerPx[0]! / 0.703125 - 1)).toBeLessThan(1e-5);
    expect(g.resolutionsDegPerPx[7]! / g.resolutionsDegPerPx[0]!).toBeCloseTo(1 / 128, 12);
    expect(g.urlTemplate).toContain("/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/");
  });

  it("produces real tile ranges despite Trek's decimal MatrixWidth (regression: all tiles were EMPTY)", () => {
    expect(MOLA_XML).toContain("<MatrixWidth>2.0</MatrixWidth>");
    const layer = getLayerConfig("mola-global-clrshade");
    const src = buildWmtsSource(parseCapabilities(MOLA_XML, layer.layerId), layer);
    const range = src.getTileGrid()!.getFullTileRange(1)!;
    expect([range.minX, range.maxX, range.minY, range.maxY]).toEqual([0, 3, 0, 1]); // MatrixWidth 4, MatrixHeight 2
    const tile = src.getTile(1, 1, 0, 1, src.getProjection()!);
    expect(tile.getState()).toBe(0); // TileState.IDLE: has a URL and will load; 4 would be EMPTY
  });

  it("rejects non-integral matrix sizes instead of guessing", () => {
    const bad = MOLA_XML.replace("<MatrixWidth>2.0</MatrixWidth>", "<MatrixWidth>2.5</MatrixWidth>");
    expect(() => parseCapabilities(bad, "x")).toThrowError(expect.objectContaining({ code: "CAPABILITIES_PARSE" }));
  });

  it("generates the documented example tile URL for level 0, row 0, col 0", () => {
    const layer = getLayerConfig("mola-global-clrshade");
    const src = buildWmtsSource(parseCapabilities(MOLA_XML, layer.layerId), layer);
    // OL tile coord: [z, x, y] with y counted from the top in OL >= 6.
    const url = src.getTileUrlFunction()([0, 0, 0], 1, src.getProjection()!);
    expect(url).toBe(
      "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0//default/default028mm/0/0/0.jpg",
    );
  });

  it("uses each layer's own matrices and extent (HiRISE: 18 levels, Jezero bbox)", () => {
    const layer = getLayerConfig("jezero-hirise-ortho");
    const src = buildWmtsSource(parseCapabilities(HIRISE_XML, layer.layerId), layer);
    const g = describeTileGrid(src);
    expect(g.matrixIds).toHaveLength(18);
    expect(g.format).toBe("image/png");
    expect(g.extent).not.toBeNull();
    const [w, s, e, n] = g.extent!;
    expect(w).toBeCloseTo(77.2229331, 6);
    expect(s).toBeCloseTo(18.3067994, 6);
    expect(e).toBeCloseTo(77.583964, 6);
    expect(n).toBeCloseTo(18.669315, 6);
  });

  it("fails with LAYER_NOT_FOUND when the identifier is not in the document", () => {
    const layer = { ...getLayerConfig("mola-global-clrshade"), layerId: "Not_A_Real_Layer" };
    expect(() => buildWmtsSource(parseCapabilities(MOLA_XML, layer.layerId), layer)).toThrowError(
      expect.objectContaining({ code: "LAYER_NOT_FOUND" }),
    );
  });

  it("refuses a TileMatrixSet in another CRS instead of overlaying it", () => {
    const xml = MOLA_XML.replaceAll("urn:ogc:def:crs:EPSG::104905", "urn:ogc:def:crs:EPSG::4326");
    const layer = getLayerConfig("mola-global-clrshade");
    expect(() => buildWmtsSource(parseCapabilities(xml, layer.layerId), layer)).toThrowError(
      expect.objectContaining({ code: "UNSUPPORTED_CRS" }),
    );
  });
});

describe("unavailable WMTS service", () => {
  const layer = getLayerConfig("mola-global-clrshade");

  it("reports a network error with a typed code", async () => {
    const f = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }) as unknown as typeof fetch;
    await expect(fetchCapabilities(layer.capabilitiesUrl!, layer.layerId, f)).rejects.toMatchObject({
      code: "CAPABILITIES_NETWORK",
    });
  });

  it("reports HTTP errors", async () => {
    const f = vi.fn(async () => new Response("down", { status: 503 })) as unknown as typeof fetch;
    const err = await loadWmtsLayer(layer, f).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(WmtsLayerError);
    expect((err as WmtsLayerError).code).toBe("CAPABILITIES_HTTP");
    expect((err as WmtsLayerError).message).toContain("503");
  });

  it("reports unparseable XML", async () => {
    const f = okFetch("<html>maintenance</html>");
    await expect(loadWmtsLayer(layer, f)).rejects.toMatchObject({ code: "CAPABILITIES_PARSE" });
  });

  it("does not cache failures, so Retry fetches again", async () => {
    const bad = vi.fn(async () => new Response("", { status: 500 })) as unknown as typeof fetch;
    await expect(loadWmtsLayer(layer, bad)).rejects.toBeInstanceOf(WmtsLayerError);
    const good = okFetch(MOLA_XML);
    const { tileLayer } = await loadWmtsLayer(layer, good);
    expect(tileLayer.getSource()).toBeTruthy();
    expect(good).toHaveBeenCalledTimes(1);
  });
});

describe("map initialization", () => {
  it("creates a map in the Mars CRS with vector overlays", () => {
    const div = document.createElement("div");
    document.body.appendChild(div);
    const h = createMarsMap(div);
    expect(h.view.getProjection().getCode()).toBe(TREK_DECLARED_CRS);
    expect(h.view.getCenter()).toEqual([0, 0]);
    expect(h.view.getMaxResolution()).toBeCloseTo(0.703125, 9);
    const roles = h.map.getLayers().getArray().map((l) => l.get("role"));
    expect(roles).toEqual(["hazards", "waypoints", "marker"]);
    h.map.setTarget(undefined);
  });
});
