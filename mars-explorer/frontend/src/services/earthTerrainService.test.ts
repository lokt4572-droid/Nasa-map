import { describe, expect, it, vi } from "vitest";

import { MAX_VIEW_SPAN_DEG, clipToTile, renderEarthTerrain, renderSize } from "./earthTerrainService";

describe("Earth terrain colours", () => {
  it("re-renders multi-tile elevation with one shared range", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce({ products: [
        { dataset_id: "c", product_id: "A", bbox: [7, 45, 8, 46] },
        { dataset_id: "c", product_id: "B", bbox: [7, 46, 8, 47] },
      ] })
      .mockResolvedValueOnce({ registered_dataset_id: 1 })
      .mockResolvedValueOnce({ registered_dataset_id: 2 });
    const render = vi.fn()
      .mockResolvedValueOnce({ url: "u1", min: 1013, max: 4542, units: "m", dataset: "a", validFraction: 1 })
      .mockResolvedValueOnce({ url: "u2", min: 1241, max: 4470, units: "m", dataset: "b", validFraction: 1 })
      .mockResolvedValue({ url: "shared", min: 0, max: 0, units: "m", dataset: "x", validFraction: 1 });
    const r = await renderEarthTerrain([7.5, 45.5, 7.9, 46.1], "elevation", { request: request as never, render: render as never });
    expect(render).toHaveBeenCalledTimes(4);
    expect(render.mock.calls[2]![0]).toMatchObject({ dataset: 1, range: [1013, 4542] });
    expect(render.mock.calls[3]![0]).toMatchObject({ dataset: 2, range: [1013, 4542] });
    expect(r.status === "ready" && r.images.map((i) => [i.url, i.min, i.max])).toEqual([["shared", 1013, 4542], ["shared", 1241, 4470]]);
  });

  it("legend gradient uses the renderer's stops", async () => {
    const { cssGradient, ELEVATION_STOPS, SLOPE_STOPS } = await import("./earthTerrainService");
    expect(cssGradient(ELEVATION_STOPS)).toBe("linear-gradient(to right, rgb(40,60,140) 0.0%, rgb(60,150,120) 25.0%, rgb(190,180,90) 50.0%, rgb(150,95,50) 75.0%, rgb(245,245,245) 100.0%)");
    expect(cssGradient(SLOPE_STOPS)).toContain("rgb(200,210,80) 22.2%");
  });

  it("clips the view to the DEM tile", () => {
    expect(clipToTile([7.5, 45.8, 8.2, 46.2], [7, 45, 8, 46])).toEqual([7.5, 45.8, 8, 46]);
    expect(clipToTile([9, 45, 9.5, 45.5], [7, 45, 8, 46])).toBeNull();
  });

  it("keeps the ground aspect ratio (longitude shrinks with cos latitude)", () => {
    expect(renderSize([0, 0, 1, 1])).toEqual({ width: 768, height: 768 });
    const hi = renderSize([7, 60, 8, 61]);
    expect(hi.height).toBe(768);
    expect(hi.width).toBeCloseTo(768 * Math.cos((60.5 * Math.PI) / 180), -1);
  });

  it("asks to zoom in instead of rendering a huge area", async () => {
    const request = vi.fn();
    const r = await renderEarthTerrain([0, 0, MAX_VIEW_SPAN_DEG + 1, 1], "hillshade", { request: request as never });
    expect(r.status).toBe("no-data");
    expect(request).not.toHaveBeenCalled();
  });

  it("reports no data over the ocean and never renders", async () => {
    const request = vi.fn().mockResolvedValue({ products: [] });
    const render = vi.fn();
    const r = await renderEarthTerrain([-30.6, 0.4, -30.4, 0.6], "elevation", { request: request as never, render: render as never });
    expect(r).toMatchObject({ status: "no-data" });
    expect(render).not.toHaveBeenCalled();
  });

  it("renders every tile in the view, clipped, in EPSG:4326; missing cells stay empty", async () => {
    const request = vi.fn()
      .mockResolvedValueOnce({ products: [
        { dataset_id: "copernicus_dem_glo30", product_id: "A", bbox: [7, 45, 8, 46] },
        { dataset_id: "copernicus_dem_glo30", product_id: "B", bbox: [7, 46, 8, 47] },
      ] })
      .mockResolvedValueOnce({ registered_dataset_id: 42 })
      .mockResolvedValueOnce({ registered_dataset_id: 43 });
    const render = vi.fn().mockResolvedValue({ url: "blob:x", min: 1, max: 2, units: "m", dataset: "d", validFraction: 1 });
    const r = await renderEarthTerrain([7.5, 45.5, 8.3, 46.1], "slope", { request: request as never, render: render as never });
    expect(r).toMatchObject({ status: "ready", missingTiles: 2 }); // the view also touches 8E cells with no tile
    expect(render.mock.calls.map((c) => c[0].bbox)).toEqual([[7.5, 45.5, 8, 46], [7.5, 46, 8, 46.1]]); // slope: absolute scale, one pass
    expect(render.mock.calls[0]![0]).toMatchObject({ dataset: 42, product: "slope", crs: "EPSG:4326" });
    expect(request.mock.calls[0]![1].query.bbox).toBe("7.50000,45.50000,8.30000,46.10000");
  });
});
