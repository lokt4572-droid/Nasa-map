import { useEffect, useState, useSyncExternalStore } from "react";

import { getLayerConfig } from "../../config/mapLayers";
import {
  exportDiagnostics,
  getSummaries,
  resetDiagnostics,
  subscribeDiagnostics,
  type LayerHealth,
  type LayerSummary,
} from "../../services/mapDiagnostics";

const HEALTH_CLASS: Record<LayerHealth, string> = {
  IDLE: "dim",
  INITIALIZING: "info",
  LOADING: "info",
  LOADED: "ok",
  PARTIALLY_LOADED: "warn",
  NO_COVERAGE: "dim",
  DEGRADED: "warn",
  FAILED: "err",
};

let version = 0;
const subscribe = (fn: () => void) =>
  subscribeDiagnostics(() => {
    version += 1;
    fn();
  });
const getVersion = () => version;

function layerName(id: string): string {
  try {
    return getLayerConfig(id).name;
  } catch {
    return id;
  }
}

/**
 * Layer status panel + small loading indicator over the map. Everything shown is measured by
 * services/mapDiagnostics (updates at most every 300 ms). "Aborted" tiles are requests the map
 * no longer needed (pan/zoom/hide) and are not failures.
 */
export default function MapDiagnostics({ planetId }: { planetId: string }) {
  useSyncExternalStore(subscribe, getVersion);
  const [open, setOpen] = useState(false);
  const rows: LayerSummary[] = getSummaries(planetId);
  const inFlight = rows.reduce((n, r) => n + r.inFlight, 0);
  const initializing = rows.some((r) => r.health === "INITIALIZING");
  const problems = rows.filter((r) => r.health === "FAILED" || r.health === "DEGRADED").length;

  useEffect(() => {
    if (!import.meta.env.DEV) return;
    (window as unknown as { __mapDiagnostics?: unknown }).__mapDiagnostics = { getSummaries, exportDiagnostics, resetDiagnostics };
  }, []);

  const download = () => {
    const blob = new Blob([exportDiagnostics()], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `map-diagnostics-${new Date().toISOString().replace(/[:.]/g, "-")}.json`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };

  return (
    <div className={`map-diag ${open ? "map-diag--open" : ""}`} data-testid="map-diagnostics">
      <button className="map-diag__toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        {inFlight > 0 || initializing ? (
          <span className="map-diag__spinner" role="status" aria-label={`Loading ${inFlight} tile(s)`} />
        ) : (
          <span className={`map-diag__dot map-diag__dot--${problems ? "warn" : "ok"}`} />
        )}
        LAYER STATUS{inFlight > 0 ? ` · ${inFlight} loading` : ""}
        {problems > 0 ? ` · ${problems} issue${problems > 1 ? "s" : ""}` : ""} {open ? "▾" : "▸"}
      </button>
      {open && (
        <div className="map-diag__body">
          {rows.length === 0 && <div className="hint small">No layer has been requested yet.</div>}
          {rows.map((r) => (
            <div key={r.layerId} className="map-diag__row">
              <div className="map-diag__head">
                <span className="map-diag__name" title={r.layerId}>
                  {layerName(r.layerId)}
                </span>
                <span className={`badge badge--${HEALTH_CLASS[r.health]}`}>{r.health.replace("_", " ")}</span>
              </div>
              <div className="map-diag__stats">
                tiles {r.loaded}/{r.requested - r.aborted}
                {r.successPct !== null ? ` (${r.successPct}%)` : ""} · failed {r.failed} · aborted {r.aborted}
                {r.noCoverage ? ` · no coverage ${r.noCoverage}` : ""}
                {r.retries ? ` · retries ${r.retries}` : ""}
                <br />
                avg {r.avgMs ?? "–"} ms · P95 {r.p95Ms ?? "–"} ms
                {r.serverErrors ? ` · 5xx ${r.serverErrors}` : ""}
                {r.rateLimited ? ` · 429 ${r.rateLimited}` : ""}
                {r.timeouts ? ` · timeouts ${r.timeouts}` : ""}
                {r.corsOrNetwork ? ` · network/CORS ${r.corsOrNetwork}` : ""}
              </div>
              {r.lastError && r.health !== "LOADED" && <div className="map-diag__err">{r.lastError}</div>}
            </div>
          ))}
          <div className="map-diag__actions">
            <button className="btn btn--small" onClick={() => resetDiagnostics()}>
              Reset counters
            </button>
            <button className="btn btn--small" onClick={download}>
              Export JSON
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
