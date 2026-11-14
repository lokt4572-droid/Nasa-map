import { useEffect, useState } from "react";

import { formatDistance, formatLat, formatLon } from "../../config/marsProjection";
import { ApiError, describeError } from "../../services/api";
import { deleteRoute, getRouteProfiles, planRoute } from "../../services/datasetService";
import { mapController } from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";
import type { RoutePoint, RouteProfile, RouteSummary } from "../../types/api";
import LineChart from "../common/LineChart";

function pointLabel(p: RoutePoint | null): string {
  return p ? `${formatLat(p.lat_deg, 3)} ${formatLon(p.lon_east_deg, "180", 3)}` : "not set";
}

function Summary({ title, r }: { title: string; r: RouteSummary }) {
  return (
    <div className="card">
      <strong>{title}</strong>
      <dl className="dl">
        <dt>Distance</dt>
        <dd className="mono">{formatDistance(r.distance_m)} (3-D {formatDistance(r.distance_3d_m)})</dd>
        <dt>Ascent / descent</dt>
        <dd className="mono">
          +{r.total_ascent_m.toFixed(0)} m / −{r.total_descent_m.toFixed(0)} m
        </dd>
        <dt>Max step grade</dt>
        <dd className="mono">{r.max_step_grade_deg.toFixed(2)}°</dd>
        <dt>Without DEM data</dt>
        <dd className={`mono ${r.unknown_terrain_fraction > 0 ? "warn-text" : ""}`}>
          {(r.unknown_terrain_fraction * 100).toFixed(1)}% ({formatDistance(r.unknown_terrain_distance_m)})
        </dd>
        {r.overlap_with_primary !== undefined && (
          <>
            <dt>Overlap w/ primary</dt>
            <dd className="mono">{(r.overlap_with_primary * 100).toFixed(0)}%</dd>
          </>
        )}
      </dl>
    </div>
  );
}

export default function RoutePlanner() {
  const draft = useAppStore((s) => s.routeDraft);
  const result = useAppStore((s) => s.routeResult);
  const point = useAppStore((s) => s.selectedPoint);
  const activeMissionId = useAppStore((s) => s.activeMissionId);
  const backendOnline = useAppStore((s) => s.backend.status === "online");
  const { setRouteDraft, setRouteResult } = useAppStore.getState();
  const [profiles, setProfiles] = useState<RouteProfile[]>([]);
  const [opts, setOpts] = useState({ ret: true, alt: true });

  useEffect(() => {
    if (!backendOnline) return;
    getRouteProfiles().then(setProfiles).catch(() => setProfiles([]));
  }, [backendOnline]);

  const fromSelected = (): RoutePoint | null =>
    point ? { lon_east_deg: point.lon, lat_deg: point.lat, crs: point.crs, latitude_convention: "AS_DECLARED_BY_SOURCE", planet: "MARS" } : null;

  const run = async () => {
    if (!draft.start || !draft.end) return;
    setRouteResult({ status: "loading", data: null, error: null });
    try {
      const data = await planRoute({
        start: draft.start,
        end: draft.end,
        waypoints: draft.waypoints,
        profile: draft.profile,
        include_return: opts.ret,
        include_alternative: opts.alt,
        ...(activeMissionId ? { mission: activeMissionId } : {}),
      });
      setRouteResult({ status: "ready", data, error: null });
    } catch (err) {
      setRouteResult({ status: "error", data: null, error: describeError(err), errorCode: err instanceof ApiError ? err.code : null });
    }
  };

  const profile = profiles.find((p) => p.id === draft.profile);
  const r = result.data;

  return (
    <div className="panel-section">
      <p className="hint">
        A* on the registered DEM. Profiles are engineering heuristics, not validated traversability models. A found route is
        never "safe": obstacles smaller than a DEM cell are invisible.
      </p>
      <div className="kv">
        <span className="label">Start</span>
        <span className="mono small">{pointLabel(draft.start)}</span>
      </div>
      <div className="kv">
        <span className="label">End</span>
        <span className="mono small">{pointLabel(draft.end)}</span>
      </div>
      {draft.waypoints.map((w, i) => (
        <div className="kv" key={i}>
          <span className="label">Via {i + 1}</span>
          <span className="mono small">
            {pointLabel(w)}{" "}
            <button className="btn btn--icon" onClick={() => setRouteDraft({ waypoints: draft.waypoints.filter((_, k) => k !== i) })}>
              ×
            </button>
          </span>
        </div>
      ))}
      <div className="layer-card__actions">
        <button className="btn btn--small btn--ghost" disabled={!point} onClick={() => setRouteDraft({ start: fromSelected() })}>
          Set start
        </button>
        <button className="btn btn--small btn--ghost" disabled={!point} onClick={() => setRouteDraft({ end: fromSelected() })}>
          Set end
        </button>
        <button
          className="btn btn--small btn--ghost"
          disabled={!point || draft.waypoints.length >= 20}
          onClick={() => setRouteDraft({ waypoints: [...draft.waypoints, fromSelected()!] })}
        >
          Add via point
        </button>
        <button className="btn btn--small btn--ghost" onClick={() => { setRouteDraft({ start: null, end: null, waypoints: [] }); setRouteResult({ status: "idle", data: null, error: null }); }}>
          Clear
        </button>
      </div>
      {!point && <div className="hint">Click the map, then use the buttons to place route points.</div>}

      <div className="form">
        <label>
          Movement profile
          <select value={draft.profile} onChange={(e) => setRouteDraft({ profile: e.target.value as "CONSERVATIVE" | "STANDARD" })}>
            <option value="CONSERVATIVE">CONSERVATIVE</option>
            <option value="STANDARD">STANDARD</option>
          </select>
        </label>
        {profile && (
          <div className="hint small">
            {profile.description} Max slope {profile.max_slope_deg}°, hazard buffer {profile.hazard_buffer_m} m, unknown terrain{" "}
            {profile.allow_unknown_terrain ? `≤ ${profile.max_unknown_fraction * 100}% at ×${profile.unknown_multiplier} cost` : "forbidden"}.
          </div>
        )}
        <label className="check">
          <input type="checkbox" checked={opts.ret} onChange={(e) => setOpts({ ...opts, ret: e.target.checked })} /> Return path
        </label>
        <label className="check">
          <input type="checkbox" checked={opts.alt} onChange={(e) => setOpts({ ...opts, alt: e.target.checked })} /> Alternative route
        </label>
        <button className="btn" disabled={!draft.start || !draft.end || !backendOnline || result.status === "loading"} onClick={() => void run()}>
          {result.status === "loading" ? "Planning…" : "Plan route"}
        </button>
      </div>

      {result.status === "error" && (
        <div className="card">
          <span className="status-chip status-chip--error">{result.errorCode ?? "ERROR"}</span>
          <div className="error-text">{result.error}</div>
          <div className="hint">No route is shown: the planner never draws a line it could not compute on real DEM data.</div>
        </div>
      )}
      {r && (
        <>
          <div className="kv">
            <span className="label">Status</span>
            <span className="status-chip status-chip--ready">{r.status}</span>
          </div>
          <div className="hint small">
            DEM {r.dataset.name} ({r.dataset.resolution_m ? formatDistance(r.dataset.resolution_m) : "?"}/cell), grid {r.grid.rows}×{r.grid.cols}
            {r.grid.decimation_factor > 1 ? `, decimated ×${r.grid.decimation_factor}` : ""}; {r.hazards_considered} hazard report(s) considered.
          </div>
          <Summary title="Route" r={r.route} />
          <h5 className="subhead">Elevation profile</h5>
          <LineChart
            x={r.route.elevation_profile.map((p) => p.distance_m / 1000)}
            series={[{ label: "Elevation", color: "#f2a33a", values: r.route.elevation_profile.map((p) => p.elevation_m) }]}
            xLabel="distance along route, km"
            yLabel={`elevation, m (${r.dataset.vertical_datum})`}
            formatX={(v) => v.toFixed(0)}
          />
          {r.return_route && <Summary title="Return route" r={r.return_route} />}
          {r.alternative_route ? <Summary title="Alternative route" r={r.alternative_route} /> : r.alternative_note && <div className="hint">{r.alternative_note}</div>}
          <div className="hint small">{r.disclaimer}</div>
          <div className="layer-card__actions">
            <button
              className="btn btn--small btn--ghost"
              onClick={() => {
                const c = r.route.geometry.coordinates;
                const lons = c.map((p) => p[0]);
                const lats = c.map((p) => p[1]);
                mapController.zoomToBBox({ west: Math.min(...lons), south: Math.min(...lats), east: Math.max(...lons), north: Math.max(...lats) });
              }}
            >
              Zoom to route
            </button>
            <button
              className="btn btn--small btn--danger"
              onClick={() => void deleteRoute(r.id).then(() => setRouteResult({ status: "idle", data: null, error: null }))}
            >
              Delete saved route
            </button>
          </div>
        </>
      )}
    </div>
  );
}
