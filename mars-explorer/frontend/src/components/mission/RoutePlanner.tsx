import { useEffect, useState } from "react";

import { formatDistance, formatLat, formatLon } from "../../config/marsProjection";
import { constraintsToForm, explainRoute, interpretInstruction, type Explanation, type Interpretation } from "../../services/aiService";
import { ApiError, describeError } from "../../services/api";
import { deleteRoute, getRouteProfiles, planRoute } from "../../services/datasetService";
import { mapController } from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";
import type { ComparisonTable, RouteClassification, RouteComparison, RoutePlanResponse, RoutePoint, RouteProfile, RouteSummary, UnknownDataPolicy } from "../../types/api";
import LineChart from "../common/LineChart";

function pointLabel(p: RoutePoint | null): string {
  return p ? `${formatLat(p.lat_deg, 3)} ${formatLon(p.lon_east_deg, "180", 3)}` : "not set";
}

const CLASS_LABEL: Record<RouteClassification, string> = {
  KNOWN_TERRAIN_ROUTE: "KNOWN TERRAIN ROUTE",
  PARTIALLY_UNVERIFIED_ROUTE: "PARTIALLY UNVERIFIED ROUTE",
  NO_VALID_ROUTE: "NO VALID ROUTE",
};

function ClassChip({ c }: { c?: RouteClassification }) {
  if (!c) return null;
  const cls = c === "KNOWN_TERRAIN_ROUTE" ? "ready" : c === "PARTIALLY_UNVERIFIED_ROUTE" ? "loading" : "error";
  return <span className={`status-chip status-chip--${cls}`} data-testid="route-classification">{CLASS_LABEL[c]}</span>;
}

function Comparison({ c }: { c: RouteComparison }) {
  const rows: [string, (b: RouteComparison["route_a"]) => string][] = [
    ["Distance", (b) => formatDistance(b.distance_m)],
    ["Terrain cost", (b) => b.terrain_cost.toFixed(0)],
    ["Total cost", (b) => b.cost.toFixed(0)],
    ["Elevation gain", (b) => `${b.elevation_gain_m.toFixed(0)} m`],
    ["Max cell slope", (b) => `${b.max_cell_slope_deg.toFixed(1)}°`],
    ["Known terrain", (b) => `${b.known_terrain_pct.toFixed(1)}%`],
  ];
  const d = c.difference_b_minus_a;
  return (
    <div className="card" data-testid="route-comparison">
      <strong>Route comparison</strong>
      <table className="cmp-table">
        <thead>
          <tr>
            <th />
            <th>A — lowest cost</th>
            <th>B — alternative</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, f]) => (
            <tr key={label}>
              <td>{label}</td>
              <td className="mono">{f(c.route_a)}</td>
              <td className="mono">{c.route_b ? f(c.route_b) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {d && (
        <div className="hint small">
          B vs A: {d.distance_m >= 0 ? "+" : "−"}
          {formatDistance(Math.abs(d.distance_m))} distance, {d.terrain_cost >= 0 ? "+" : "−"}
          {Math.abs(d.terrain_cost).toFixed(0)} terrain cost.
        </div>
      )}
      <div className="hint small">{c.note} Terrain cost = penalty above the 3-D distance (slope, roughness, hazard proximity, unknown terrain).</div>
    </div>
  );
}

export function fmtCell(key: string, v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  if (key.endsWith("_m") && key.startsWith("distance")) return formatDistance(v);
  if (key.endsWith("_deg")) return `${v.toFixed(1)}°`;
  if (key.endsWith("_pct") || key.startsWith("nodata")) return `${v.toFixed(1)}%`;
  if (key.endsWith("_m")) return v >= 1000 ? formatDistance(v) : `${v.toFixed(v < 10 ? 1 : 0)} m`;
  return v.toFixed(Math.abs(v) < 10 ? 1 : 0);
}

/** v0.4 comparison: every value is copied from the planner's metrics; labels are neutral. */
function ComparisonTableView({ t }: { t: ComparisonTable }) {
  if (t.routes.length < 2) return null;
  return (
    <div className="card" data-testid="route-comparison-table">
      <strong>Route comparison</strong>
      <table className="cmp-table">
        <thead>
          <tr>
            <th />
            {t.routes.map((r) => (
              <th key={r.name}>{r.name}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {t.criteria.map((c) => (
            <tr key={c.key}>
              <td>{c.title}</td>
              {t.routes.map((r) => (
                <td key={r.name} className="mono">
                  {fmtCell(c.key, r.values[c.key])}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <td>Label</td>
            {t.routes.map((r) => (
              <td key={r.name} className="small">
                {r.label}
              </td>
            ))}
          </tr>
          <tr>
            <td>Compared</td>
            {t.routes.map((r) => (
              <td key={r.name} className="small">
                {r.descriptors.length ? r.descriptors.join("; ") : "—"}
              </td>
            ))}
          </tr>
        </tbody>
      </table>
      <div className="hint small">
        Same DEM ({t.shared.dem}, {t.shared.dem_resolution_m ? formatDistance(t.shared.dem_resolution_m) : "?"}) and profile for every candidate. {t.note}
      </div>
    </div>
  );
}

function ExplanationView({ e }: { e: Explanation }) {
  const x = e.explanation;
  const list = (title: string, items: string[]) =>
    items.length > 0 && (
      <>
        <dt>{title}</dt>
        <dd>
          <ul className="plain-list">
            {items.map((i) => (
              <li key={i}>{i}</li>
            ))}
          </ul>
        </dd>
      </>
    );
  return (
    <div className="card" data-testid="route-explanation">
      <strong>Why this route</strong>{" "}
      <span className="muted small">
        {e.generator.is_language_model ? `written by ${e.generator.name} ${e.generator.model ?? ""}, checked against the route numbers` : "generated from the route numbers (no AI model)"}
      </span>
      <p className="small">{x.summary}</p>
      <dl className="dl small">
        {list("Cost factors", x.cost_factors)}
        {list("Uncertain data", x.uncertain_data)}
        {list("Alternatives", x.alternatives)}
        {list("Limitations", x.limitations)}
      </dl>
      {!e.validation.accepted && e.validation.reason && <div className="warn-text small">Model text rejected ({e.validation.reason}); deterministic text shown.</div>}
      <div className="hint small">{e.note}</div>
    </div>
  );
}

function Summary({ title, r }: { title: string; r: RouteSummary }) {
  return (
    <div className="card">
      <strong>{title}</strong> <ClassChip c={r.classification} />
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
        {r.max_cell_slope_deg !== undefined && (
          <>
            <dt>Max cell slope</dt>
            <dd className="mono">{r.max_cell_slope_deg.toFixed(2)}°</dd>
          </>
        )}
        {r.metrics && (
          <>
            <dt>Cost (terrain)</dt>
            <dd className="mono">
              {r.metrics.cost.toFixed(0)} ({r.metrics.terrain_cost.toFixed(0)})
            </dd>
          </>
        )}
        {r.overlap_with_primary !== undefined && (
          <>
            <dt>Overlap w/ primary</dt>
            <dd className="mono">{(r.overlap_with_primary * 100).toFixed(0)}%</dd>
          </>
        )}
      </dl>
      {!!r.unverified_segments?.length && (
        <div className="warn-text small" data-testid="unverified-segments">
          UNVERIFIED (no DEM data):{" "}
          {r.unverified_segments.map((s) => `${formatDistance(s.from_m)}–${formatDistance(s.to_m)}`).join(", ")} along the route
        </div>
      )}
    </div>
  );
}

function DataQuality({ q }: { q: RoutePlanResponse["data_quality"] }) {
  const a = q.resolution_assessment;
  return (
    <div className="card">
      {a.astronaut_scale_route_safety === "NOT_SUITABLE" && (
        <div className="map-error" style={{ position: "static", marginBottom: 6 }} role="alert">
          <strong>NOT SUITABLE FOR ASTRONAUT-SCALE ROUTE SAFETY.</strong> {a.reason}
        </div>
      )}
      {q.planning_scope?.scope === "REGIONAL_PLANNING_ONLY" && (
        <div className="warn-text small" style={{ marginBottom: 4 }}>
          <strong>REGIONAL PLANNING ONLY.</strong> {q.planning_scope.reason}
        </div>
      )}
      <strong>Input data quality</strong>
      <dl className="dl small">
        <dt>Use class</dt>
        <dd>
          <span className="status-chip status-chip--t-no-data">{a.class}</span> {a.allowed_use}
        </dd>
        <dt>DEM</dt>
        <dd>
          {q.dem.name} ({q.dem.instrument}) — dataset {q.dem.resolution_m ? formatDistance(q.dem.resolution_m) : "?"}/cell
        </dd>
        <dt>Routing grid cell</dt>
        <dd className="mono">
          E–W {formatDistance(q.grid_cell_size_m.dx_min)}…{formatDistance(q.grid_cell_size_m.dx_max)}, N–S {formatDistance(q.grid_cell_size_m.dy_mean)}
          {q.grid_decimation_factor > 1 ? ` (decimated ×${q.grid_decimation_factor})` : ""}
        </dd>
        <dt>Smallest resolvable</dt>
        <dd className="mono">≈ {formatDistance(a.smallest_resolvable_feature_m)}</dd>
        <dt>Astronaut-scale safety</dt>
        <dd className="error-text">{a.astronaut_scale_route_safety.replaceAll("_", " ")}</dd>
        <dt>NoData in window</dt>
        <dd className="mono">{(q.window_nodata_fraction * 100).toFixed(1)}%</dd>
        <dt>Latitude handling</dt>
        <dd className={q.latitude_handling === "NOT_VERIFIED" ? "warn-text" : ""}>{q.latitude_handling}</dd>
        <dt>Vertical datum</dt>
        <dd>{q.dem.vertical_datum}</dd>
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
  const [unknownPolicy, setUnknownPolicy] = useState<UnknownDataPolicy>("ALLOW_MARKED");
  const planet = useAppStore((s) => s.planet);
  // v0.4 mission configuration (empty = profile default). These can only tighten the plan.
  const [limits, setLimits] = useState<{ maxSlope: number | null; requiredResolution: number | null; maxRoughness: number | null; hazardBuffer: number | null; connectivity: 4 | 8; preferSmooth: boolean; remote: boolean }>({
    maxSlope: null, requiredResolution: null, maxRoughness: null, hazardBuffer: null, connectivity: 8, preferSmooth: false, remote: false,
  });
  const [instruction, setInstruction] = useState("");
  const [interp, setInterp] = useState<{ busy: boolean; data: Interpretation | null; error: string | null }>({ busy: false, data: null, error: null });
  const [expl, setExpl] = useState<{ busy: boolean; data: Explanation | null; error: string | null }>({ busy: false, data: null, error: null });
  const [failure, setFailure] = useState<{ calc: string | null; warnings: string[] } | null>(null);

  const interpret = async () => {
    setInterp({ busy: true, data: null, error: null });
    try {
      setInterp({ busy: false, data: await interpretInstruction(instruction), error: null });
    } catch (err) {
      setInterp({ busy: false, data: null, error: describeError(err) });
    }
  };
  const applyConstraints = (d: Interpretation) => {
    if (!d.constraints) return;
    const f = constraintsToForm(d.constraints);
    setRouteDraft({ profile: f.profile });
    setOpts({ ret: f.ret, alt: f.alt });
    setLimits((l) => ({ ...l, maxSlope: f.maxSlope, requiredResolution: f.requiredResolution, maxRoughness: f.maxRoughness, hazardBuffer: f.hazardBuffer, connectivity: f.connectivity, preferSmooth: f.preferSmooth }));
    if (f.profile === "STANDARD") setUnknownPolicy("REJECT"); // the assistant never enables unknown terrain
  };
  const explain = async (id: number) => {
    setExpl({ busy: true, data: null, error: null });
    try {
      setExpl({ busy: false, data: await explainRoute(id), error: null });
    } catch (err) {
      setExpl({ busy: false, data: null, error: describeError(err) });
    }
  };

  useEffect(() => {
    if (!backendOnline) return;
    getRouteProfiles().then(setProfiles).catch(() => setProfiles([]));
  }, [backendOnline]);

  const fromSelected = (): RoutePoint | null =>
    point ? { lon_east_deg: point.lon, lat_deg: point.lat, crs: point.crs, latitude_convention: "AS_DECLARED_BY_SOURCE", planet } : null;

  const run = async () => {
    if (!draft.start || !draft.end) return;
    setRouteResult({ status: "loading", data: null, error: null });
    setFailure(null);
    setExpl({ busy: false, data: null, error: null });
    try {
      const data = await planRoute({
        start: draft.start,
        end: draft.end,
        waypoints: draft.waypoints,
        profile: draft.profile,
        include_return: opts.ret,
        include_alternative: opts.alt,
        // unknown terrain can only be crossed with STANDARD (marked UNVERIFIED)
        ...(draft.profile === "STANDARD" ? { unknown_data_policy: unknownPolicy } : {}),
        ...(activeMissionId ? { mission: activeMissionId } : {}),
        ...(limits.maxSlope ? { max_slope_deg: limits.maxSlope } : {}),
        ...(limits.requiredResolution ? { required_resolution_m: limits.requiredResolution } : {}),
        ...(limits.maxRoughness ? { max_roughness_m: limits.maxRoughness } : {}),
        ...(limits.hazardBuffer ? { hazard_buffer_m: limits.hazardBuffer } : {}),
        ...(limits.connectivity === 4 ? { connectivity: 4 as const } : {}),
        ...(limits.preferSmooth ? { prefer_lower_roughness: true } : {}),
        terrain_source: limits.remote ? "auto" : "local",
      });
      setRouteResult({ status: "ready", data, error: null });
    } catch (err) {
      const body = err instanceof ApiError ? (err.body as { calculation_status?: string; warnings?: string[] } | undefined) : undefined;
      setFailure({ calc: body?.calculation_status ?? null, warnings: body?.warnings ?? [] });
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

      <details className="route-assistant" data-testid="route-assistant">
        <summary>Describe preferences (assistant, optional)</summary>
        <textarea
          rows={3}
          maxLength={2000}
          value={instruction}
          placeholder="e.g. Prefer smooth terrain, avoid slopes above 15 degrees and keep a return path to the base."
          onChange={(e) => setInstruction(e.target.value)}
        />
        <div className="layer-card__actions">
          <button className="btn btn--small" disabled={!instruction.trim() || interp.busy || !backendOnline} onClick={() => void interpret()}>
            {interp.busy ? "Reading…" : "Interpret"}
          </button>
        </div>
        {interp.error && <div className="error-text small">{interp.error}</div>}
        {interp.data && (
          <div className="card small" data-testid="route-interpretation">
            <div className="muted">
              {interp.data.provider.is_language_model
                ? `Interpreted by ${interp.data.provider.name} ${interp.data.provider.model}`
                : `Interpreted by the rule-based parser (${interp.data.provider.name}) — not an AI model`}
            </div>
            {interp.data.accepted && interp.data.constraints ? (
              <>
                <dl className="dl">
                  {Object.entries(interp.data.constraints)
                    .filter(([k]) => k !== "notes")
                    .map(([k, v]) => (
                      <span key={k} style={{ display: "contents" }}>
                        <dt>{k.replaceAll("_", " ")}</dt>
                        <dd className="mono">{String(v)}</dd>
                      </span>
                    ))}
                </dl>
                <button className="btn btn--small" onClick={() => applyConstraints(interp.data!)}>
                  Apply to the planner
                </button>
                <div className="hint">{interp.data.note}</div>
              </>
            ) : (
              <div className="error-text">
                Not applied ({interp.data.code}): {interp.data.problems.join("; ")}
              </div>
            )}
          </div>
        )}
      </details>

      <div className="form">
        <label>
          Movement profile
          <select value={draft.profile} onChange={(e) => setRouteDraft({ profile: e.target.value as "CONSERVATIVE" | "STANDARD" })}>
            <option value="CONSERVATIVE">CONSERVATIVE</option>
            <option value="STANDARD">STANDARD — exploratory, not conservative</option>
          </select>
        </label>
        {profile && (
          <div className="hint small">
            {profile.description} Max slope {profile.max_slope_deg}°, hazard buffer {profile.hazard_buffer_m} m, unknown terrain{" "}
            {profile.allow_unknown_terrain ? `≤ ${profile.max_unknown_fraction * 100}% at ×${profile.unknown_multiplier} cost` : "forbidden"}.
          </div>
        )}
        {draft.profile === "STANDARD" ? (
          <label>
            Terrain without DEM data
            <select value={unknownPolicy} onChange={(e) => setUnknownPolicy(e.target.value as UnknownDataPolicy)}>
              <option value="ALLOW_MARKED">Allow, marked UNVERIFIED</option>
              <option value="REJECT">Reject</option>
            </select>
          </label>
        ) : (
          <div className="hint small">CONSERVATIVE never enters terrain without DEM data.</div>
        )}
        <details className="route-limits">
          <summary>Mission limits (optional; they only tighten the profile)</summary>
          <label>
            Max slope, deg
            <input type="number" min={1} max={45} step={0.5} value={limits.maxSlope ?? ""} placeholder={profile ? String(profile.max_slope_deg) : ""}
              onChange={(e) => setLimits({ ...limits, maxSlope: e.target.value ? Number(e.target.value) : null })} />
          </label>
          <label>
            Required DEM resolution, m (finer or equal)
            <input type="number" min={0.1} step={1} value={limits.requiredResolution ?? ""} placeholder="any"
              onChange={(e) => setLimits({ ...limits, requiredResolution: e.target.value ? Number(e.target.value) : null })} />
          </label>
          <label>
            Max roughness (TRI), m
            <input type="number" min={0} step={1} value={limits.maxRoughness ?? ""} placeholder="no limit"
              onChange={(e) => setLimits({ ...limits, maxRoughness: e.target.value ? Number(e.target.value) : null })} />
          </label>
          <label>
            Hazard buffer, m (≥ profile)
            <input type="number" min={0} step={50} value={limits.hazardBuffer ?? ""} placeholder={profile ? String(profile.hazard_buffer_m) : ""}
              onChange={(e) => setLimits({ ...limits, hazardBuffer: e.target.value ? Number(e.target.value) : null })} />
          </label>
          <label className="check">
            <input type="checkbox" checked={limits.connectivity === 4} onChange={(e) => setLimits({ ...limits, connectivity: e.target.checked ? 4 : 8 })} /> 4-direction moves only
          </label>
          <label className="check">
            <input type="checkbox" checked={limits.preferSmooth} onChange={(e) => setLimits({ ...limits, preferSmooth: e.target.checked })} /> Prefer lower roughness
          </label>
        </details>
        <label className="check" title="Also use DTMs from the USGS catalogue covering all points (read remotely, first use can take 10–30 s)">
          <input type="checkbox" checked={limits.remote} onChange={(e) => setLimits({ ...limits, remote: e.target.checked })} /> Use catalogue DTMs (CTX / HiRISE / Kaguya)
        </label>
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
          <span className="status-chip status-chip--error" data-testid="route-calc-status">{failure?.calc ?? result.errorCode ?? "ERROR"}</span>{" "}
          {result.errorCode && ["NO_PASSABLE_ROUTE", "INSUFFICIENT_TERRAIN_DATA"].includes(result.errorCode) && <ClassChip c="NO_VALID_ROUTE" />}
          <div className="error-text">{result.error}</div>
          {failure && failure.warnings.length > 0 && (
            <ul className="plain-list small">
              {failure.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          <div className="hint">No route is shown: the planner never draws a line it could not compute on real DEM data.</div>
        </div>
      )}
      {r && (
        <>
          <div className="kv">
            <span className="label">Status</span>
            <span className="status-chip status-chip--ready" data-testid="route-calc-status">{r.calculation_status ?? r.status}</span> <ClassChip c={r.route_classification} />
          </div>
          {r.route_label && (
            <div className="kv">
              <span className="label">Result</span>
              <span className="small">
                {r.route_label}
                {r.planning_level ? ` · planning level ${r.planning_level.level} (${r.planning_level.name})` : ""}
                {r.route.source_validation
                  ? r.route.source_validation.status === "VALIDATED"
                    ? ` · VALIDATED on ${r.route.source_validation.source.dataset} every ${r.route.source_validation.source.sample_spacing_m.toFixed(1)} m`
                    : " · VALIDATION FAILED"
                  : ""}
              </span>
            </div>
          )}
          {!!r.warnings?.length && (
            <ul className="plain-list small warn-text" data-testid="route-warnings">
              {r.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}
          <div className="hint small">
            DEM {r.dataset.name} ({r.dataset.resolution_m ? formatDistance(r.dataset.resolution_m) : "?"}/cell), grid {r.grid.rows}×{r.grid.cols}
            {r.grid.decimation_factor > 1 ? `, decimated ×${r.grid.decimation_factor}` : ""}; {r.hazards_considered} hazard report(s) considered.
          </div>
          <DataQuality q={r.data_quality} />
          <Summary title="Route" r={r.route} />
          <h5 className="subhead">Elevation profile</h5>
          <LineChart
            x={r.route.elevation_profile.map((p) => p.distance_m / 1000)}
            series={[{ label: "Elevation", color: "#f2a33a", values: r.route.elevation_profile.map((p) => p.elevation_m) }]}
            xLabel="distance along route, km"
            yLabel={`elevation, m (${r.dataset.vertical_datum})`}
            formatX={(v) => v.toFixed(0)}
          />
          {r.comparison_table && r.comparison_table.routes.length > 1 ? <ComparisonTableView t={r.comparison_table} /> : r.comparison && <Comparison c={r.comparison} />}
          {r.return_route && <Summary title="Return route" r={r.return_route} />}
          {r.alternative_route ? <Summary title="Alternative route" r={r.alternative_route} /> : r.alternative_note && <div className="hint">{r.alternative_note}</div>}
          <div className="hint small">{r.disclaimer}</div>
          {expl.data && <ExplanationView e={expl.data} />}
          {expl.error && <div className="error-text small">Explanation failed: {expl.error}</div>}
          <div className="layer-card__actions">
            <button
              className="btn btn--small btn--ghost"
              title="Local 3D terrain covering the whole route (one bounded patch; Route A orange, Route B blue)"
              onClick={() => {
                const pts = [...r.route.geometry.coordinates, ...(r.alternative_route?.geometry.coordinates ?? [])];
                const lons = pts.map((p) => p[0]);
                const lats = pts.map((p) => p[1]);
                const lon = (Math.min(...lons) + Math.max(...lons)) / 2;
                const lat = (Math.min(...lats) + Math.max(...lats)) / 2;
                const R = planet === "EARTH" ? 6_371_000 : planet === "MOON" ? 1_737_400 : planet === "MERCURY" ? 2_439_400 : 3_389_500;
                const halfDeg = Math.max((Math.max(...lats) - Math.min(...lats)) / 2, ((Math.max(...lons) - Math.min(...lons)) / 2) * Math.cos((lat * Math.PI) / 180));
                const radius = Math.min(500_000, Math.max(250, halfDeg * (Math.PI / 180) * R * 1.15));
                const st = useAppStore.getState();
                st.selectPoint({ lon, lat, crs: draft.start?.crs ?? "", layerId: st.activeLayerId, pickedAt: new Date().toISOString() });
                st.setTerrainRadiusRequest({ radiusM: Math.round(radius), seq: Date.now() });
                st.setTerrainView("split");
              }}
            >
              Route in 3D
            </button>
            <button className="btn btn--small btn--ghost" disabled={expl.busy} onClick={() => void explain(r.id)}>
              {expl.busy ? "Explaining…" : "Explain this route"}
            </button>
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
