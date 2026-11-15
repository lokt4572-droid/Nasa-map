/**
 * Fetch-based WMTS tile loading (replaces OpenLayers' default <img src=...> loader).
 *
 * Why: with <img> the browser gives no HTTP status, no timing, no way to cancel, so a slow
 * NASA Trek tile (measured avg ~3 s, P95 up to 17 s, HTTP/1.1 with ~6 connections per host)
 * keeps a connection busy even after the user has panned away. With fetch we can:
 *   - abort obsolete requests (tile released by OL, layer hidden/removed, planet switched);
 *   - time every request and read its HTTP status;
 *   - classify failures: NO_COVERAGE, HTTP_ERROR, SERVER_ERROR, RATE_LIMITED, TIMEOUT,
 *     CORS_OR_NETWORK (the browser does not expose which of the two), OFFLINE;
 *   - retry only transient errors (429/500/502/503/504/timeout) with bounded exponential
 *     backoff + jitter, honouring Retry-After, at most MAX_RETRIES times.
 *
 * Responses go through the normal HTTP cache (fetch default mode), so NASA Trek tiles are reused
 * per their validators; failures are never cached by this code. Only the URL *path* is
 * recorded in diagnostics (no query string, no headers).
 */
import type ImageTile from "ol/ImageTile";
import type Tile from "ol/Tile";
import TileState from "ol/TileState";
import type WMTSTileGrid from "ol/tilegrid/WMTS";

import type { BBox } from "../config/mapLayers";
import { recordEvent, type ErrorCategory } from "./mapDiagnostics";

export const MAX_RETRIES = 3;
export const RETRY_STATUSES = new Set([408, 429, 500, 502, 503, 504]);

export interface TileLoaderOptions {
  layerId: string;
  planetId: string;
  grid: WMTSTileGrid;
  /** Declared coverage of the layer (from GetCapabilities / catalog). */
  bbox: BBox | null;
  timeoutMs?: number;
  maxRetries?: number;
  fetchImpl?: typeof fetch;
  sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
  random?: () => number;
  now?: () => number;
  isOnline?: () => boolean;
  createObjectURL?: (b: Blob) => string;
  revokeObjectURL?: (u: string) => void;
}

export interface TileLoaderHandle {
  loadFunction: (tile: Tile, src: string) => void;
  /** Abort every in-flight request of this layer (layer hidden/removed, map disposed). */
  abortAll: () => void;
  /**
   * Abort requests the current view no longer needs: tiles outside `viewExtent` (pass a
   * buffered extent) or more than one level finer than the level for `viewResolution`.
   * Returns the number of cancelled requests.
   */
  pruneObsolete: (viewExtent: number[], viewResolution: number, worldWidth?: number) => number;
  inFlight: () => number;
}

class Aborted extends Error {}

function defaultSleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new Aborted());
    const t = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(t);
      reject(new Aborted());
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export function pathOf(src: string): string {
  try {
    return new URL(src, "http://local").pathname;
  } catch {
    return src.split("?")[0] ?? "";
  }
}

/** Retry-After as seconds or HTTP date -> ms (capped). */
export function retryAfterMs(header: string | null, nowMs = Date.now(), capMs = 30_000): number | null {
  if (!header) return null;
  const secs = Number(header);
  if (Number.isFinite(secs) && secs >= 0) return Math.min(secs * 1000, capMs);
  const at = Date.parse(header);
  if (Number.isFinite(at)) return Math.min(Math.max(0, at - nowMs), capMs);
  return null;
}

/** Exponential backoff with +-50% jitter: 500 ms, 1 s, 2 s ... capped at 8 s. */
export function backoffMs(attempt: number, random: () => number = Math.random): number {
  const base = Math.min(500 * 2 ** attempt, 8000);
  return Math.round(base * (0.5 + random()));
}

export function categorizeStatus(status: number): ErrorCategory {
  if (status === 429) return "RATE_LIMITED";
  if (status >= 500) return "SERVER_ERROR";
  return "HTTP_ERROR";
}

/** 0 = tile fully outside coverage, 1 = partially inside, 2 = fully inside. */
export function coverageRelation(tileExtent: number[], bbox: BBox | null): 0 | 1 | 2 {
  if (!bbox) return 2;
  const [w, s, e, n] = tileExtent as [number, number, number, number];
  if (e <= bbox.west || w >= bbox.east || n <= bbox.south || s >= bbox.north) return 0;
  if (w >= bbox.west && e <= bbox.east && s >= bbox.south && n <= bbox.north) return 2;
  return 1;
}

export function createTileLoader(opts: TileLoaderOptions): TileLoaderHandle {
  const {
    layerId, planetId, grid, bbox,
    timeoutMs = 30_000,
    maxRetries = MAX_RETRIES,
    fetchImpl = (...a: Parameters<typeof fetch>) => fetch(...a),
    sleep = defaultSleep,
    random = Math.random,
    now = () => performance.now(),
    isOnline = () => (typeof navigator === "undefined" ? true : navigator.onLine !== false),
    createObjectURL = (b: Blob) => URL.createObjectURL(b),
    revokeObjectURL = (u: string) => URL.revokeObjectURL(u),
  } = opts;
  const controllers = new Map<AbortController, { tile: Tile; z: number; extent: number[] }>();

  const loadFunction = (tile: Tile, src: string) => {
    const imageTile = tile as ImageTile;
    const [z, col, row] = tile.getTileCoord() as [number, number, number];
    const matrix = grid.getMatrixId(z);
    const path = pathOf(src);
    const base = { layerId, planetId, matrix, z, row, col, path };

    // Tile entirely outside the declared coverage: never request it.
    const tileExtent = grid.getTileCoordExtent(tile.getTileCoord());
    const relation = coverageRelation(tileExtent, bbox);
    if (relation === 0) {
      recordEvent({ ...base, type: "TILE_REQUESTED", retry: 0 });
      recordEvent({ ...base, type: "COVERAGE_MISSING", category: "NO_COVERAGE", note: "outside declared bbox; not requested" });
      tile.setState(TileState.EMPTY);
      return;
    }

    const controller = new AbortController();
    controllers.set(controller, { tile, z, extent: tileExtent });
    // OL releases a tile (state -> EMPTY) when it drops it from its cache: cancel the download.
    const onChange = () => {
      if (tile.getState() === TileState.EMPTY) controller.abort();
    };
    tile.addEventListener("change", onChange);
    const finish = () => {
      controllers.delete(controller);
      tile.removeEventListener("change", onChange);
    };

    const fail = (category: ErrorCategory, httpStatus: number | null, t0: number, attempt: number, note?: string) => {
      const t1 = now();
      recordEvent({ ...base, type: "TILE_FAILED", category, httpStatus, requestedAt: t0, respondedAt: t1, durationMs: t1 - t0, retry: attempt, note });
      const extra = category === "TIMEOUT" ? "TIMEOUT" : category === "SERVER_ERROR" ? "SERVER_ERROR" : category === "CORS_OR_NETWORK" ? "CORS_ERROR" : null;
      if (extra) recordEvent({ ...base, type: extra, category, httpStatus, retry: attempt });
      finish();
      if (tile.getState() !== TileState.EMPTY) tile.setState(TileState.ERROR);
    };

    const run = async () => {
      let retryReason: string | undefined;
      for (let attempt = 0; ; attempt++) {
        if (!isOnline()) {
          recordEvent({ ...base, type: "TILE_REQUESTED", retry: attempt, note: retryReason });
          return fail("OFFLINE", null, now(), attempt, "browser reports offline");
        }
        const t0 = now();
        recordEvent({ ...base, type: "TILE_REQUESTED", requestedAt: t0, retry: attempt, note: retryReason });
        // Per-attempt controller, linked to the tile controller (cancellation) and the timeout.
        const attemptCtl = new AbortController();
        let timedOut = false;
        const timer = setTimeout(() => {
          timedOut = true;
          attemptCtl.abort();
        }, timeoutMs);
        const link = () => attemptCtl.abort();
        controller.signal.addEventListener("abort", link, { once: true });
        let res: Response;
        try {
          res = await fetchImpl(src, { signal: attemptCtl.signal, mode: "cors", credentials: "omit" });
        } catch (err) {
          clearTimeout(timer);
          controller.signal.removeEventListener("abort", link);
          if (controller.signal.aborted) throw new Aborted();
          if (timedOut) {
            if (attempt < maxRetries) {
              recordEvent({ ...base, type: "TIMEOUT", category: "TIMEOUT", retry: attempt, durationMs: now() - t0 });
              retryReason = `timeout after ${timeoutMs} ms`;
              await sleep(backoffMs(attempt, random), controller.signal);
              continue;
            }
            return fail("TIMEOUT", null, t0, attempt, `no response within ${timeoutMs} ms`);
          }
          // fetch() rejects with TypeError for CORS refusals and network failures alike.
          return fail(isOnline() ? "CORS_OR_NETWORK" : "OFFLINE", null, t0, attempt, String((err as Error)?.message ?? err));
        }
        if (!res.ok) {
          clearTimeout(timer);
          controller.signal.removeEventListener("abort", link);
          if (RETRY_STATUSES.has(res.status) && attempt < maxRetries) {
            const wait = retryAfterMs(res.headers.get("Retry-After")) ?? backoffMs(attempt, random);
            // Informational only (not counted as a failure): the tile is retried.
            if (res.status >= 500) recordEvent({ ...base, type: "SERVER_ERROR", category: "SERVER_ERROR", httpStatus: res.status, retry: attempt, note: `retrying in ${wait} ms` });
            retryReason = `HTTP ${res.status}, waited ${wait} ms`;
            await sleep(wait, controller.signal);
            continue;
          }
          if (res.status === 404) {
            const t1 = now();
            if (relation === 1) {
              // Tile straddles the coverage edge: the server simply has no data there.
              recordEvent({ ...base, type: "COVERAGE_MISSING", category: "NO_COVERAGE", httpStatus: 404, requestedAt: t0, respondedAt: t1, durationMs: t1 - t0 });
              finish();
              tile.setState(TileState.EMPTY);
              return;
            }
            return fail("HTTP_ERROR", 404, t0, attempt, "404 inside declared coverage (missing tile or wrong URL)");
          }
          return fail(categorizeStatus(res.status), res.status, t0, attempt);
        }
        let blob: Blob;
        try {
          blob = await res.blob();
        } catch (err) {
          clearTimeout(timer);
          controller.signal.removeEventListener("abort", link);
          if (controller.signal.aborted) throw new Aborted();
          if (timedOut) return fail("TIMEOUT", res.status, t0, attempt, "body not received in time");
          return fail("CORS_OR_NETWORK", res.status, t0, attempt, String(err));
        }
        clearTimeout(timer);
        controller.signal.removeEventListener("abort", link);
        if (controller.signal.aborted) throw new Aborted();
        const t1 = now();
        recordEvent({ ...base, type: "TILE_LOADED", httpStatus: res.status, requestedAt: t0, respondedAt: t1, durationMs: t1 - t0, retry: attempt });
        finish();
        const image = imageTile.getImage() as HTMLImageElement;
        const url = createObjectURL(blob);
        const revoke = () => revokeObjectURL(url);
        if (typeof image.addEventListener === "function") {
          image.addEventListener("load", revoke, { once: true });
          image.addEventListener("error", revoke, { once: true });
        }
        image.src = url; // ImageTile's own listeners move the tile to LOADED (or ERROR if undecodable)
        return;
      }
    };

    run().catch((err) => {
      finish();
      if (err instanceof Aborted || controller.signal.aborted) {
        recordEvent({ ...base, type: "TILE_ABORTED", note: "obsolete request cancelled" });
        if (tile.getState() === TileState.LOADING) resetToIdle(tile);
        return;
      }
      recordEvent({ ...base, type: "TILE_FAILED", category: "INVALID_CONFIGURATION", note: String(err) });
      if (tile.getState() !== TileState.EMPTY) tile.setState(TileState.ERROR);
    });
  };

  return {
    loadFunction,
    abortAll: () => {
      [...controllers.keys()].forEach((c) => c.abort());
    },
    pruneObsolete: (viewExtent: number[], viewResolution: number, worldWidth = 360) => {
      const zWanted = grid.getZForResolution(viewResolution);
      let n = 0;
      for (const [c, t] of [...controllers]) {
        const visible = [-worldWidth, 0, worldWidth].some((shift) => intersects(t.extent, viewExtent, shift));
        if (!visible || t.z > zWanted + 1) {
          c.abort();
          n += 1;
        }
      }
      return n;
    },
    inFlight: () => controllers.size,
  };
}

function intersects(tile: number[], view: number[], shift: number): boolean {
  return tile[0]! + shift < view[2]! && tile[2]! + shift > view[0]! && tile[1]! < view[3]! && tile[3]! > view[1]!;
}

/**
 * Cancelled (not released) tile: free its slot in OL's TileQueue (which listens for ERROR) and
 * then put it back to IDLE, so the renderer re-queues it if it becomes visible again. Without the
 * reset OpenLayers keeps the tile in ERROR in its cache and never requests it again.
 */
function resetToIdle(tile: Tile): void {
  tile.setState(TileState.ERROR);
  (tile as unknown as { state: number }).state = TileState.IDLE;
}

/** Buffer an extent by a fraction of its size on each side. */
export function bufferExtent(extent: number[], fraction: number): number[] {
  const dx = (extent[2]! - extent[0]!) * fraction;
  const dy = (extent[3]! - extent[1]!) * fraction;
  return [extent[0]! - dx, extent[1]! - dy, extent[2]! + dx, extent[3]! + dy];
}
