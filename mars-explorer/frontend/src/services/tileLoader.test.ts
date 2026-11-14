/**
 * Map reliability tests: fetch-based tile loading, error categories, retries, cancellation,
 * coverage handling and diagnostics accounting. No network: fetch is a stub.
 */
import TileState from "ol/TileState";
import WMTSTileGrid from "ol/tilegrid/WMTS";
import type Tile from "ol/Tile";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getLayerConfig } from "../config/mapLayers";
import { getEvents, getLayerSummary, healthOf, percentile, resetDiagnostics, type LayerStats } from "./mapDiagnostics";
import { attachTileStats, regionalMaxResolution } from "./marsMapService";
import { backoffMs, coverageRelation, createTileLoader, MAX_RETRIES, pathOf, retryAfterMs } from "./tileLoader";

// Decimal-degree grid like NASA Trek: level 0 = 2x1 tiles of 180 deg.
const grid = new WMTSTileGrid({
  origin: [-180, 90],
  resolutions: [180 / 256, 90 / 256, 45 / 256],
  matrixIds: ["0", "1", "2"],
  tileSize: 256,
});
const GLOBAL = { west: -180, south: -90, east: 180, north: 90 };
const SRC = "https://trek.nasa.gov/tiles/Mars/EQ/X/1.0.0/default/default028mm/2/1/3.jpg";

class FakeTile {
  state: number = TileState.LOADING;
  image = { src: "", addEventListener: vi.fn() };
  listeners = new Set<() => void>();
  constructor(public coord: [number, number, number]) {}
  getTileCoord() {
    return this.coord;
  }
  getState() {
    return this.state;
  }
  setState(s: number) {
    if (this.state === TileState.EMPTY) return; // OL: no more changes once released
    this.state = s;
    this.listeners.forEach((l) => l());
  }
  getImage() {
    return this.image;
  }
  addEventListener(_t: string, l: () => void) {
    this.listeners.add(l);
  }
  removeEventListener(_t: string, l: () => void) {
    this.listeners.delete(l);
  }
  release() {
    this.setState(TileState.EMPTY);
  }
}

const res = (status: number, headers: Record<string, string> = {}) =>
  ({ ok: status >= 200 && status < 300, status, headers: new Headers(headers), blob: async () => new Blob(["x"]) }) as unknown as Response;

function setup(responses: Array<Response | Error | "hang">, extra: Partial<Parameters<typeof createTileLoader>[0]> = {}) {
  const queue = [...responses];
  const fetchImpl = vi.fn((_url: RequestInfo | URL, init?: RequestInit) => {
    const next = queue.length > 1 ? queue.shift()! : queue[0]!;
    if (next === "hang") {
      return new Promise<Response>((_r, reject) => {
        init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    }
    return next instanceof Error ? Promise.reject(next) : Promise.resolve(next);
  });
  const sleep = vi.fn(async () => {});
  const loader = createTileLoader({
    layerId: "test-layer",
    planetId: "MARS",
    grid,
    bbox: GLOBAL,
    fetchImpl: fetchImpl as unknown as typeof fetch,
    sleep,
    random: () => 0.5,
    isOnline: () => true,
    createObjectURL: () => "blob:tile",
    revokeObjectURL: () => {},
    ...extra,
  });
  return { loader, fetchImpl, sleep };
}

async function load(loader: ReturnType<typeof createTileLoader>, coord: [number, number, number] = [2, 3, 1], src = SRC) {
  const tile = new FakeTile(coord);
  loader.loadFunction(tile as unknown as Tile, src);
  await vi.waitFor(() => expect(loader.inFlight()).toBe(0));
  await new Promise((r) => setTimeout(r, 0));
  return tile;
}

const summary = () => getLayerSummary("test-layer")!;

beforeEach(() => resetDiagnostics());

describe("tile loader: success and HTTP errors", () => {
  it("loads a tile via fetch, records timing and status", async () => {
    const { loader, fetchImpl } = setup([res(200)]);
    const tile = await load(loader);
    expect(tile.image.src).toBe("blob:tile");
    expect(fetchImpl.mock.calls[0]![1]).toMatchObject({ mode: "cors", credentials: "omit" });
    const s = summary();
    expect([s.requested, s.loaded, s.failed, s.successPct]).toEqual([1, 1, 0, 100]);
    const ev = getEvents().find((e) => e.type === "TILE_LOADED")!;
    expect(ev).toMatchObject({ matrix: "2", z: 2, row: 1, col: 3, httpStatus: 200, retry: 0, planetId: "MARS" });
    expect(ev.durationMs).toBeGreaterThanOrEqual(0);
  });

  it("404 for a tile fully inside coverage is an HTTP_ERROR (possible broken URL), not 'no coverage'", async () => {
    const { loader, fetchImpl } = setup([res(404)]);
    const tile = await load(loader);
    expect(tile.state).toBe(TileState.ERROR);
    expect(fetchImpl).toHaveBeenCalledTimes(1); // 404 is not retried
    expect(summary()).toMatchObject({ failed: 1, noCoverage: 0, health: "FAILED" });
    expect(summary().lastError).toContain("HTTP_ERROR HTTP 404");
  });

  it("404 for a tile straddling the coverage edge is NO_COVERAGE and not a failure", async () => {
    const { loader } = setup([res(404)], { bbox: { west: 0, south: 0, east: 50, north: 50 } });
    const tile = await load(loader, [2, 4, 1]); // lon 0..45, lat 0..45 -> inside; use a straddling one below
    expect(tile.state).toBe(TileState.ERROR);
    resetDiagnostics();
    const t2 = await load(loader, [2, 5, 1]); // lon 45..90 straddles east=50
    expect(t2.state).toBe(TileState.EMPTY);
    expect(summary()).toMatchObject({ failed: 0, noCoverage: 1, health: "NO_COVERAGE" });
  });

  it("never requests a tile entirely outside the declared bbox", async () => {
    const { loader, fetchImpl } = setup([res(200)], { bbox: { west: 77.1, south: 18.2, east: 77.7, north: 18.8 } });
    const tile = await load(loader, [2, 0, 0]);
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(tile.state).toBe(TileState.EMPTY);
    expect(summary()).toMatchObject({ noCoverage: 1, failed: 0 });
  });

  it("other 4xx are HTTP_ERROR without retry", async () => {
    const { loader, fetchImpl } = setup([res(403)]);
    await load(loader);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(summary().lastError).toContain("HTTP 403");
  });
});

describe("tile loader: retries", () => {
  it("500 then 200: retried once with backoff, counted as one request", async () => {
    const { loader, fetchImpl, sleep } = setup([res(500), res(200)]);
    const tile = await load(loader);
    expect(tile.image.src).toBe("blob:tile");
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(sleep).toHaveBeenCalledWith(500, expect.anything()); // 500 * 2^0 * (0.5 + 0.5)
    expect(summary()).toMatchObject({ requested: 1, loaded: 1, failed: 0, retries: 1, successPct: 100 });
    expect(getEvents().some((e) => e.type === "SERVER_ERROR" && e.httpStatus === 500)).toBe(true);
  });

  it("503 forever: at most MAX_RETRIES retries, then SERVER_ERROR", async () => {
    const { loader, fetchImpl, sleep } = setup([res(503)]);
    const tile = await load(loader);
    expect(fetchImpl).toHaveBeenCalledTimes(MAX_RETRIES + 1);
    expect(sleep.mock.calls.map((c) => (c as unknown as [number])[0])).toEqual([500, 1000, 2000]);
    expect(tile.state).toBe(TileState.ERROR);
    expect(summary()).toMatchObject({ requested: 1, failed: 1, serverErrors: 1, retries: 3 });
  });

  it("429 honours Retry-After and is reported as RATE_LIMITED when it persists", async () => {
    const { loader, fetchImpl, sleep } = setup([res(429, { "Retry-After": "2" })]);
    await load(loader);
    expect(fetchImpl).toHaveBeenCalledTimes(4);
    expect(sleep.mock.calls.map((c) => (c as unknown as [number])[0])).toEqual([2000, 2000, 2000]);
    expect(summary()).toMatchObject({ rateLimited: 1, failed: 1 });
  });

  it("timeout: retried, then TIMEOUT", async () => {
    const { loader, fetchImpl } = setup(["hang"], { timeoutMs: 5, maxRetries: 1 });
    const tile = await load(loader);
    expect(fetchImpl).toHaveBeenCalledTimes(2);
    expect(tile.state).toBe(TileState.ERROR);
    expect(summary()).toMatchObject({ timeouts: 1, failed: 1 });
    expect(getEvents().filter((e) => e.type === "TIMEOUT").length).toBeGreaterThanOrEqual(2);
  });
});

describe("tile loader: network, CORS, offline", () => {
  it("fetch TypeError -> CORS_OR_NETWORK (the browser cannot tell them apart), no retry", async () => {
    const { loader, fetchImpl } = setup([new TypeError("Failed to fetch")]);
    await load(loader);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(summary()).toMatchObject({ corsOrNetwork: 1, failed: 1 });
    expect(getEvents().some((e) => e.type === "CORS_ERROR")).toBe(true);
  });

  it("offline: no request is sent", async () => {
    const { loader, fetchImpl } = setup([res(200)], { isOnline: () => false });
    const tile = await load(loader);
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(tile.state).toBe(TileState.ERROR);
    expect(summary().lastError).toContain("OFFLINE");
  });
});

describe("tile loader: cancellation", () => {
  it("released tile aborts its request; aborted is not a failure", async () => {
    const { loader, fetchImpl } = setup(["hang"]);
    const tile = new FakeTile([2, 3, 1]);
    loader.loadFunction(tile as unknown as Tile, SRC);
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    tile.release();
    await vi.waitFor(() => expect(loader.inFlight()).toBe(0));
    await new Promise((r) => setTimeout(r, 0));
    expect(summary()).toMatchObject({ requested: 1, aborted: 1, failed: 0, inFlight: 0, successPct: null });
    expect(tile.image.src).toBe(""); // never painted after cancellation
  });

  it("abortAll cancels every in-flight request of the layer (layer hidden / map disposed)", async () => {
    const { loader } = setup(["hang"]);
    const tiles = [new FakeTile([2, 0, 0]), new FakeTile([2, 1, 0]), new FakeTile([2, 2, 0])];
    tiles.forEach((t) => loader.loadFunction(t as unknown as Tile, SRC));
    await vi.waitFor(() => expect(summary().inFlight).toBe(3));
    loader.abortAll();
    await vi.waitFor(() => expect(summary().aborted).toBe(3));
    expect(summary().failed).toBe(0);
    // queue slot freed (ERROR was emitted) and tile back to IDLE so OL re-requests it when shown again
    tiles.forEach((t) => expect(t.state).toBe(TileState.IDLE));
  });

  it("pruneObsolete cancels tiles outside the view or at finer levels, keeps the rest", async () => {
    const { loader } = setup(["hang"]);
    const inView = new FakeTile([2, 4, 1]); // lon 0..45, lat 0..45
    const outside = new FakeTile([2, 0, 3]); // lon -180..-135, lat -90..-45
    const coarse = new FakeTile([1, 2, 0]); // lon 0..90, lat 0..90 (preload level)
    [inView, outside, coarse].forEach((t) => loader.loadFunction(t as unknown as Tile, SRC));
    await vi.waitFor(() => expect(loader.inFlight()).toBe(3));
    // view lon 10..30, lat 10..30 at level-2 resolution
    expect(loader.pruneObsolete([10, 10, 30, 30], 45 / 256)).toBe(1);
    await vi.waitFor(() => expect(loader.inFlight()).toBe(2));
    expect(outside.state).toBe(TileState.IDLE);
    // zoomed far out (level 0): level-2 tile is more than one level too fine
    expect(loader.pruneObsolete([-180, -90, 180, 90], 180 / 256)).toBe(1);
    await vi.waitFor(() => expect(loader.inFlight()).toBe(1));
    expect(summary()).toMatchObject({ aborted: 2, failed: 0, inFlight: 1 });
    loader.abortAll();
  });

  it("pruneObsolete treats wrapped (x +- 360) views as visible", async () => {
    const { loader } = setup(["hang"]);
    const t = new FakeTile([2, 0, 1]); // lon -180..-135
    loader.loadFunction(t as unknown as Tile, SRC);
    await vi.waitFor(() => expect(loader.inFlight()).toBe(1));
    expect(loader.pruneObsolete([190, 10, 210, 30], 45 / 256)).toBe(0); // 190..210 == -170..-150
    loader.abortAll();
  });

  it("cancellation during a retry wait stops further attempts", async () => {
    let release: () => void = () => {};
    const sleep = vi.fn(
      (_ms: number, signal: AbortSignal) =>
        new Promise<void>((_r, reject) => {
          release = () => reject(new Error("aborted"));
          signal.addEventListener("abort", () => release());
        }),
    );
    const { loader, fetchImpl } = setup([res(503)], { sleep });
    const tile = new FakeTile([2, 3, 1]);
    loader.loadFunction(tile as unknown as Tile, SRC);
    await vi.waitFor(() => expect(sleep).toHaveBeenCalled());
    tile.release();
    await vi.waitFor(() => expect(summary().aborted).toBe(1));
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });
});

describe("diagnostics and helpers", () => {
  it("logs only the URL path (no query string or credentials)", () => {
    expect(pathOf("https://user:pw@trek.nasa.gov/tiles/a/b.jpg?token=SECRET")).toBe("/tiles/a/b.jpg");
  });

  it("each tile is counted once, no duplicates from retries", async () => {
    const { loader } = setup([res(500), res(500), res(200)]);
    await load(loader);
    await load(loader, [2, 2, 1]);
    expect(summary()).toMatchObject({ requested: 2, loaded: 2, retries: 2 });
  });

  it("reset while tiles are in flight keeps them as requested (no load without a request)", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchImpl = vi.fn(() => new Promise<Response>((r) => (resolve = r)));
    const { loader } = setup([res(200)], { fetchImpl: fetchImpl as unknown as typeof fetch });
    const tile = new FakeTile([2, 3, 1]);
    loader.loadFunction(tile as unknown as Tile, SRC);
    await vi.waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    resetDiagnostics();
    resolve(res(200));
    await vi.waitFor(() => expect(loader.inFlight()).toBe(0));
    expect(summary()).toMatchObject({ requested: 1, loaded: 1, inFlight: 0, successPct: 100 });
  });

  it("Retry-After parsing and backoff bounds", () => {
    expect(retryAfterMs("3")).toBe(3000);
    expect(retryAfterMs("999")).toBe(30_000);
    expect(retryAfterMs(new Date(Date.now() + 5000).toUTCString())).toBeGreaterThan(3000);
    expect(retryAfterMs("soon")).toBeNull();
    for (let a = 0; a < 10; a++) {
      expect(backoffMs(a, () => 1)).toBeLessThanOrEqual(12_000);
      expect(backoffMs(a, () => 0)).toBeGreaterThanOrEqual(250);
    }
  });

  it("coverage relation", () => {
    const b = { west: 0, south: 0, east: 10, north: 10 };
    expect(coverageRelation([20, 20, 30, 30], b)).toBe(0);
    expect(coverageRelation([2, 2, 5, 5], b)).toBe(2);
    expect(coverageRelation([5, 5, 15, 15], b)).toBe(1);
  });

  it("health is derived from measured counters", () => {
    const base: LayerStats = {
      layerId: "x", planetId: "MARS", requested: 0, loaded: 0, failed: 0, aborted: 0, noCoverage: 0, serverErrors: 0, timeouts: 0,
      corsOrNetwork: 0, rateLimited: 0, retries: 0, inFlight: 0, durations: [], capabilities: "LOADED", lastError: null,
    };
    expect(healthOf({ ...base, capabilities: "PENDING" })).toBe("INITIALIZING");
    expect(healthOf({ ...base, capabilities: "FAILED" })).toBe("FAILED");
    expect(healthOf({ ...base, requested: 3, inFlight: 1 })).toBe("LOADING");
    expect(healthOf({ ...base, requested: 3, loaded: 3 })).toBe("LOADED");
    expect(healthOf({ ...base, requested: 3, loaded: 2, failed: 1 })).toBe("DEGRADED");
    expect(healthOf({ ...base, requested: 3, loaded: 2, noCoverage: 1 })).toBe("PARTIALLY_LOADED");
    expect(healthOf({ ...base, requested: 2, aborted: 2 })).toBe("IDLE");
    expect(percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95)).toBe(10);
    expect(percentile([], 95)).toBeNull();
  });
});

describe("map loading limits", () => {
  afterEach(() => vi.useRealTimers());

  it("regional layers have a resolution limit, global ones do not", () => {
    expect(regionalMaxResolution(getLayerConfig("mola-global-clrshade"))).toBeUndefined();
    const ctx = getLayerConfig("jezero-ctx-ortho");
    const r = regionalMaxResolution(ctx)!;
    expect(r).toBeGreaterThan(0);
    // not rendered at the global view (0.35 deg/px), rendered when its bbox fills the map
    expect(r).toBeLessThan(0.3515625);
    expect(r).toBeGreaterThan((ctx.bbox.east - ctx.bbox.west) / 1000);
  });

  it("tile counters for the UI are throttled (no per-tile store write storm)", () => {
    vi.useFakeTimers();
    const handlers: Record<string, () => void> = {};
    const source = { on: (t: string, h: () => void) => (handlers[t] = h), un: vi.fn() };
    const onChange = vi.fn();
    attachTileStats(source as never, onChange, 250);
    for (let i = 0; i < 50; i++) {
      handlers["tileloadstart"]!();
      handlers["tileloadend"]!();
    }
    expect(onChange).toHaveBeenCalledTimes(0);
    vi.advanceTimersByTime(260);
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenLastCalledWith({ loading: 0, loaded: 50, errors: 0 });
  });
});
