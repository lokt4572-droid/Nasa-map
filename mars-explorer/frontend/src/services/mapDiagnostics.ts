/**
 * Map diagnostics: per-tile events and per-layer health, measured (never assumed).
 *
 * Events: TILE_REQUESTED, TILE_LOADED, TILE_FAILED, TILE_ABORTED, LAYER_INITIALIZED,
 * LAYER_FAILED, CAPABILITIES_LOADED, COVERAGE_MISSING, TIMEOUT, SERVER_ERROR, CORS_ERROR.
 *
 * Only the tile path is stored (no headers, no credentials). Aborted requests (tiles the map
 * no longer needs) are counted separately and never as server failures. Listeners are
 * notified at most every NOTIFY_MS so tile traffic cannot cause a React re-render storm.
 */
export type DiagEventType =
  | "TILE_REQUESTED"
  | "TILE_LOADED"
  | "TILE_FAILED"
  | "TILE_ABORTED"
  | "LAYER_INITIALIZED"
  | "LAYER_FAILED"
  | "CAPABILITIES_LOADED"
  | "COVERAGE_MISSING"
  | "TIMEOUT"
  | "SERVER_ERROR"
  | "CORS_ERROR";

export type ErrorCategory =
  | "NO_COVERAGE"
  | "HTTP_ERROR"
  | "SERVER_ERROR"
  | "RATE_LIMITED"
  | "TIMEOUT"
  | "CORS_OR_NETWORK"
  | "OFFLINE"
  | "INVALID_CONFIGURATION"
  | "UNSUPPORTED_ZOOM";

export type LayerHealth =
  | "INITIALIZING"
  | "LOADING"
  | "LOADED"
  | "PARTIALLY_LOADED"
  | "NO_COVERAGE"
  | "DEGRADED"
  | "FAILED"
  | "IDLE";

export interface TileEvent {
  type: DiagEventType;
  layerId: string;
  planetId: string;
  matrix?: string;
  z?: number;
  row?: number;
  col?: number;
  requestedAt?: number; // performance.now()
  respondedAt?: number;
  durationMs?: number;
  httpStatus?: number | null;
  category?: ErrorCategory;
  retry?: number; // attempt index (0 = first try)
  path?: string; // URL path only
  note?: string;
  at: number;
}

export interface LayerStats {
  layerId: string;
  planetId: string;
  requested: number;
  loaded: number;
  failed: number;
  aborted: number;
  noCoverage: number;
  serverErrors: number;
  timeouts: number;
  corsOrNetwork: number;
  rateLimited: number;
  retries: number;
  inFlight: number;
  durations: number[]; // successful tiles, ms (bounded)
  capabilities: "PENDING" | "LOADED" | "FAILED" | "NOT_APPLICABLE";
  lastError: string | null;
}

const MAX_EVENTS = 3000;
const MAX_DURATIONS = 1000;
const NOTIFY_MS = 300;

const events: TileEvent[] = [];
const stats = new Map<string, LayerStats>();
const listeners = new Set<() => void>();
let notifyTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleNotify() {
  if (notifyTimer) return;
  notifyTimer = setTimeout(() => {
    notifyTimer = null;
    listeners.forEach((l) => l());
  }, NOTIFY_MS);
}

export function subscribeDiagnostics(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function layerStats(layerId: string, planetId: string): LayerStats {
  let s = stats.get(layerId);
  if (!s) {
    s = {
      layerId, planetId, requested: 0, loaded: 0, failed: 0, aborted: 0, noCoverage: 0, serverErrors: 0, timeouts: 0,
      corsOrNetwork: 0, rateLimited: 0, retries: 0, inFlight: 0, durations: [], capabilities: "NOT_APPLICABLE", lastError: null,
    };
    stats.set(layerId, s);
  }
  return s;
}

export function recordEvent(e: Omit<TileEvent, "at">): void {
  const ev: TileEvent = { ...e, at: Date.now() };
  events.push(ev);
  if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS);
  const s = layerStats(e.layerId, e.planetId);
  switch (e.type) {
    case "TILE_REQUESTED":
      if (!e.retry) {
        s.requested += 1;
        s.inFlight += 1;
      } else s.retries += 1;
      break;
    case "TILE_LOADED":
      s.loaded += 1;
      s.inFlight = Math.max(0, s.inFlight - 1);
      if (e.durationMs !== undefined) {
        s.durations.push(e.durationMs);
        if (s.durations.length > MAX_DURATIONS) s.durations.shift();
      }
      break;
    case "TILE_ABORTED":
      s.aborted += 1;
      s.inFlight = Math.max(0, s.inFlight - 1);
      break;
    case "COVERAGE_MISSING":
      s.noCoverage += 1;
      s.inFlight = Math.max(0, s.inFlight - 1);
      break;
    case "TILE_FAILED":
      s.failed += 1;
      s.inFlight = Math.max(0, s.inFlight - 1);
      if (e.category === "SERVER_ERROR") s.serverErrors += 1;
      if (e.category === "TIMEOUT") s.timeouts += 1;
      if (e.category === "CORS_OR_NETWORK" || e.category === "OFFLINE") s.corsOrNetwork += 1;
      if (e.category === "RATE_LIMITED") s.rateLimited += 1;
      s.lastError = `${e.category}${e.httpStatus ? ` HTTP ${e.httpStatus}` : ""} ${e.path ?? ""}`.trim();
      break;
    case "CAPABILITIES_LOADED":
    case "LAYER_INITIALIZED":
      s.capabilities = "LOADED";
      break;
    case "LAYER_FAILED":
      s.capabilities = "FAILED";
      s.lastError = e.note ?? "layer failed";
      break;
    default:
      break;
  }
  scheduleNotify();
}

export function markCapabilitiesPending(layerId: string, planetId: string): void {
  layerStats(layerId, planetId).capabilities = "PENDING";
  scheduleNotify();
}

export function percentile(values: number[], p: number): number | null {
  if (!values.length) return null;
  const s = [...values].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1)]!;
}

export interface LayerSummary {
  layerId: string;
  planetId: string;
  health: LayerHealth;
  requested: number;
  loaded: number;
  failed: number;
  aborted: number;
  noCoverage: number;
  serverErrors: number;
  timeouts: number;
  corsOrNetwork: number;
  rateLimited: number;
  retries: number;
  inFlight: number;
  successPct: number | null; // loaded / (requested - aborted), aborted never counted as failures
  avgMs: number | null;
  p95Ms: number | null;
  lastError: string | null;
}

/** Health from measured counters. A layer with missing tiles is never "LOADED". */
export function healthOf(s: LayerStats): LayerHealth {
  if (s.capabilities === "PENDING") return "INITIALIZING";
  if (s.capabilities === "FAILED") return "FAILED";
  if (s.inFlight > 0) return "LOADING";
  const settled = s.requested - s.aborted;
  if (settled <= 0) return "IDLE";
  if (s.loaded === 0 && s.noCoverage > 0 && s.failed === 0) return "NO_COVERAGE";
  if (s.loaded === 0 && s.failed > 0) return "FAILED";
  if (s.failed > 0) return "DEGRADED";
  if (s.noCoverage > 0) return "PARTIALLY_LOADED";
  return "LOADED";
}

export function summarize(s: LayerStats): LayerSummary {
  const settled = s.requested - s.aborted;
  const avg = s.durations.length ? s.durations.reduce((a, b) => a + b, 0) / s.durations.length : null;
  return {
    layerId: s.layerId, planetId: s.planetId, health: healthOf(s), requested: s.requested, loaded: s.loaded, failed: s.failed,
    aborted: s.aborted, noCoverage: s.noCoverage, serverErrors: s.serverErrors, timeouts: s.timeouts, corsOrNetwork: s.corsOrNetwork,
    rateLimited: s.rateLimited, retries: s.retries, inFlight: s.inFlight,
    successPct: settled > 0 ? Math.round((1000 * s.loaded) / settled) / 10 : null,
    avgMs: avg === null ? null : Math.round(avg), p95Ms: (() => { const p = percentile(s.durations, 95); return p === null ? null : Math.round(p); })(),
    lastError: s.lastError,
  };
}

export function getSummaries(planetId?: string): LayerSummary[] {
  return [...stats.values()].filter((s) => !planetId || s.planetId === planetId).map(summarize);
}

export function getLayerSummary(layerId: string): LayerSummary | null {
  const s = stats.get(layerId);
  return s ? summarize(s) : null;
}

export function getEvents(limit = 200): TileEvent[] {
  return events.slice(-limit);
}

/**
 * Reset counters (e.g. before a measurement run). Requests still in flight are carried over as
 * "requested", so their completion is not counted as a load without a request.
 */
export function resetDiagnostics(layerId?: string): void {
  const targets = layerId ? [stats.get(layerId)].filter((s): s is LayerStats => !!s) : [...stats.values()];
  for (const s of targets) {
    Object.assign(s, {
      requested: s.inFlight, loaded: 0, failed: 0, aborted: 0, noCoverage: 0, serverErrors: 0, timeouts: 0,
      corsOrNetwork: 0, rateLimited: 0, retries: 0, durations: [], lastError: null,
    });
  }
  if (!layerId) events.length = 0;
  scheduleNotify();
}

export function exportDiagnostics(): string {
  return JSON.stringify({ exported_at: new Date().toISOString(), layers: getSummaries(), events: getEvents(MAX_EVENTS) }, null, 2);
}
