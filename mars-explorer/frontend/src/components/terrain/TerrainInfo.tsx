import { useAppStore } from "../../store/useAppStore";
import type { TerrainAnalysisStatus } from "../../types/api";

const fmt = (v: number | null | undefined, digits: number, unit = "") =>
  v === null || v === undefined || !Number.isFinite(v) ? "—" : `${v.toFixed(digits)}${unit}`;

/** Derives the displayed Terrain Analysis Status from the backend responses. */
export function useTerrainStatus(): { status: TerrainAnalysisStatus | "NO POINT" | "BACKEND OFFLINE"; reason: string } {
  const point = useAppStore((s) => s.selectedPoint);
  const info = useAppStore((s) => s.pointInfo);
  const backend = useAppStore((s) => s.backend.status);
  if (!point) return { status: "NO POINT", reason: "Click the map to select a point." };
  if (backend === "offline") return { status: "BACKEND OFFLINE", reason: "Backend API is not reachable." };
  if (info.coverage.status === "loading" || info.sample.status === "loading" || info.slope.status === "loading")
    return { status: "PROCESSING", reason: "Querying the backend…" };
  if (info.coverage.status === "error") return { status: "ERROR", reason: info.coverage.error ?? "Unknown error" };
  const c = info.coverage.data;
  if (!c) return { status: "PROCESSING", reason: "Waiting…" };
  if (c.terrain_analysis_status === "ERROR")
    return { status: "ERROR", reason: c.raster_backend.error ?? "Raster backend (GDAL) unavailable" };
  if (c.terrain_analysis_status === "NO DATA")
    return { status: "NO DATA", reason: "No validated DEM covering this point is registered." };
  return { status: c.terrain_analysis_status, reason: `${c.datasets.length} DEM(s) cover this point.` };
}

export default function TerrainInfo({ compact = false }: { compact?: boolean }) {
  const info = useAppStore((s) => s.pointInfo);
  const { status, reason } = useTerrainStatus();
  const sample = info.sample.data;
  const slope = info.slope.data;
  const latWarn = sample?.latitude_handling.warning ?? slope?.latitude_handling.warning;

  return (
    <div className="terrain-info">
      <div className="kv">
        <span className="label">Terrain Analysis Status</span>
        <span className={`status-chip status-chip--t-${status.replace(/\s/g, "-").toLowerCase()}`}>{status}</span>
      </div>
      <div className="hint">{reason}</div>

      <div className="kv kv--big">
        <span className="label">Elevation</span>
        <span className="mono">
          {sample && sample.elevation_m !== null
            ? `${sample.elevation_m.toFixed(1)} ${sample.units}`
            : "DATA NOT AVAILABLE"}
        </span>
      </div>
      {sample && (
        <div className="hint">
          {sample.method}. Datum: {sample.vertical_datum}. Source: {sample.dataset.name}
          {sample.dataset.instrument ? ` (${sample.dataset.instrument})` : ""}, resolution{" "}
          {fmt(sample.dataset.resolution_meters, 1, " m")}.
        </div>
      )}
      {info.sample.status === "error" && <div className="error-text">{info.sample.error}</div>}

      {!compact && (
        <>
          <div className="kv">
            <span className="label">Slope</span>
            <span className="mono">{slope?.slope_deg != null ? fmt(slope.slope_deg, 2, "°") : "DATA NOT AVAILABLE"}</span>
          </div>
          <div className="kv">
            <span className="label">Aspect</span>
            <span className="mono">{fmt(slope?.aspect_deg, 1, "°")}</span>
          </div>
          <div className="kv">
            <span className="label">Roughness (TRI, 3×3)</span>
            <span className="mono">{fmt(slope?.terrain_ruggedness_index_m, 2, " m")}</span>
          </div>
          <div className="kv">
            <span className="label">NoData in window</span>
            <span className="mono">{slope ? `${Math.round(slope.nodata_fraction * 100)}%` : "—"}</span>
          </div>
          {slope && (
            <div className="hint">
              {slope.method}; cell {fmt(slope.cell_size_m.dx, 1)} × {fmt(slope.cell_size_m.dy, 1)} m (E–W × N–S). {slope.disclaimer}
            </div>
          )}
        </>
      )}
      {latWarn && <div className="warn-text">{latWarn}</div>}
    </div>
  );
}

export function TerrainSection() {
  return (
    <div className="panel-section">
      <TerrainInfo />
      <h4 className="subhead">Metrics and sources</h4>
      <ul className="plain-list">
        <li>Elevation — nearest cell of a registered, validated DEM (MOLA MEGDR, HiRISE DTM, …).</li>
        <li>Slope / aspect — Horn 3×3 on numeric DEM values; cell size from the DEM CRS ellipsoid and latitude.</li>
        <li>Roughness — terrain ruggedness index over 3×3 cells.</li>
        <li>Never derived from WMTS colours or hillshade pixels.</li>
        <li>No safety classification: no validated hazard model exists yet.</li>
      </ul>
    </div>
  );
}
