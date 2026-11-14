import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import LineChart from "./components/common/LineChart";
import { ApiError } from "./services/api";
import { fetchTerrainRender } from "./services/datasetService";
import { loadSettings, useAppStore } from "./store/useAppStore";

afterEach(() => vi.unstubAllGlobals());

describe("settings persistence (bug B8)", () => {
  it("stores the longitude display mode and reloads it", () => {
    localStorage.clear();
    expect(loadSettings().lonMode).toBe("180");
    useAppStore.getState().setSettings({ lonMode: "360" });
    expect(JSON.parse(localStorage.getItem("mars-explorer.settings.v1")!)).toEqual({ lonMode: "360", autoHighRes: true });
    expect(loadSettings().lonMode).toBe("360");
  });

  it("ignores corrupted stored settings", () => {
    localStorage.setItem("mars-explorer.settings.v1", "{not json");
    expect(loadSettings().lonMode).toBe("180");
  });
});

describe("LineChart", () => {
  it("breaks the line at missing values instead of interpolating", () => {
    const html = renderToStaticMarkup(
      <LineChart x={[0, 1, 2, 3, 4]} series={[{ label: "z", color: "red", values: [1, 2, null, 4, 5] }]} xLabel="km" yLabel="m" />,
    );
    expect(html.match(/<path /g)).toHaveLength(2);
    expect(html).toContain("km");
  });

  it("shows an empty state without data", () => {
    const html = renderToStaticMarkup(<LineChart x={[0, 1]} series={[{ label: "z", color: "red", values: [null, null] }]} xLabel="x" yLabel="y" />);
    expect(html).toContain("No data to plot");
  });
});

describe("terrain render fetch", () => {
  it("reads value range and dataset from response headers", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(new Blob([new Uint8Array([137, 80])]), {
        status: 200,
        headers: { "X-Value-Min": "-2500.5", "X-Value-Max": "1200", "X-Value-Units": "m", "X-Valid-Fraction": "0.9", "X-Dataset": "mola-global" },
      }),
    ));
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => "blob:x" }));
    const r = await fetchTerrainRender({ dataset: 1, product: "slope", bbox: [70, 10, 80, 20], width: 100, height: 100 });
    expect(r).toMatchObject({ min: -2500.5, max: 1200, units: "m", validFraction: 0.9, dataset: "mola-global", url: "blob:x" });
  });

  it("maps backend errors to ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ error: { code: "DEM_NOT_AVAILABLE", message: "missing" } }), { status: 404 }),
    ));
    const err = await fetchTerrainRender({ dataset: 9, product: "slope", bbox: [0, 0, 1, 1], width: 16, height: 16 }).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).code).toBe("DEM_NOT_AVAILABLE");
  });
});

describe("route draft store", () => {
  it("keeps start, end and via points independently", () => {
    const p = { lon_east_deg: 77, lat_deg: 18, crs: "c", latitude_convention: "AS_DECLARED_BY_SOURCE" };
    const s = useAppStore.getState();
    s.setRouteDraft({ start: p });
    s.setRouteDraft({ waypoints: [p, p] });
    expect(useAppStore.getState().routeDraft).toMatchObject({ start: p, end: null, profile: "CONSERVATIVE" });
    expect(useAppStore.getState().routeDraft.waypoints).toHaveLength(2);
  });
});
