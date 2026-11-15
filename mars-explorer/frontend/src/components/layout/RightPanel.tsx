import { bboxContains, getLayerConfig } from "../../config/mapLayers";
import { MAP_COORDINATE_CONVENTION, formatLat, formatLon } from "../../config/marsProjection";
import { PLANETS } from "../../config/planetRegistry";
import { useEffect, useState } from "react";

import { ApiError, describeError } from "../../services/api";
import { type DerivedHazards, type PointCoverage, analyseTerrain, formatResolution, getPointCoverage } from "../../services/datasetDiscoveryService";
import { useAppStore } from "../../store/useAppStore";
import LocalTerrain3D from "../terrain/LocalTerrain3D";
import TerrainInfo from "../terrain/TerrainInfo";

export default function RightPanel() {
  const point = useAppStore((s) => s.selectedPoint);
  const body = PLANETS[useAppStore((s) => s.planet)];
  const coverage = useAppStore((s) => s.pointInfo.coverage);
  const lonMode = useAppStore((s) => s.settings.lonMode);
  const selectPoint = useAppStore((s) => s.selectPoint);
  const planet = useAppStore((s) => s.planet);
  const backendOnline = useAppStore((s) => s.backend.status === "online");
  const [cat, setCat] = useState<{ status: "idle" | "loading" | "ready" | "error"; data: PointCoverage | null; error: string | null }>({ status: "idle", data: null, error: null });
  const [analysis, setAnalysis] = useState<{ status: "idle" | "loading" | "ready" | "error"; data: DerivedHazards | null; error: string | null }>({ status: "idle", data: null, error: null });

  // Catalogue coverage in the background (the provider can take a few seconds).
  useEffect(() => {
    setAnalysis({ status: "idle", data: null, error: null });
    if (!point || !backendOnline) return setCat({ status: "idle", data: null, error: null });
    const ctrl = new AbortController();
    setCat({ status: "loading", data: null, error: null });
    getPointCoverage(planet, point.lon, point.lat, ctrl.signal)
      .then((data) => setCat({ status: "ready", data, error: null }))
      .catch((err: unknown) => !ctrl.signal.aborted && setCat({ status: "error", data: null, error: describeError(err) }));
    return () => ctrl.abort();
  }, [planet, point?.lon, point?.lat, backendOnline]);

  const runAnalysis = async () => {
    if (!point) return;
    const res = cat.data?.best?.resolution_m ?? 1000;
    const radius = Math.min(50_000, Math.max(500, res * 64)); // about 128 DEM cells across
    setAnalysis({ status: "loading", data: null, error: null });
    try {
      setAnalysis({ status: "ready", data: await analyseTerrain(planet, point, radius), error: null });
    } catch (err) {
      const body = err instanceof ApiError ? (err.body as DerivedHazards | undefined) : undefined;
      if (body?.status === "NO_DATA_COVERAGE") setAnalysis({ status: "ready", data: body, error: null });
      else setAnalysis({ status: "error", data: null, error: describeError(err) });
    }
  };
  const planRoute = () => {
    if (!point) return;
    const st = useAppStore.getState();
    st.setRouteDraft({ start: { lon_east_deg: point.lon, lat_deg: point.lat, crs: point.crs, latitude_convention: "AS_DECLARED_BY_SOURCE", planet } });
    st.setSection("routes");
  };

  if (!point) {
    return (
      <aside className="rightpanel rightpanel--empty">
        <h3 className="panel-title">Point Information</h3>
        <div className="empty">Click on the map to inspect a location.</div>
      </aside>
    );
  }
  const layer = getLayerConfig(point.layerId);
  const inLayer = bboxContains(layer.bbox, point.lon, point.lat);
  const demNames = coverage.data?.datasets.map((d) => d.name) ?? [];

  return (
    <aside className="rightpanel">
      <div className="layer-card__head">
        <h3 className="panel-title">Point Information</h3>
        <button className="btn btn--icon" title="Clear selection" onClick={() => selectPoint(null)}>
          ×
        </button>
      </div>
      <dl className="dl dl--wide">
        <dt>Latitude</dt>
        <dd className="mono big">{formatLat(point.lat, 5)}</dd>
        <dt>Longitude</dt>
        <dd className="mono big">{formatLon(point.lon, lonMode, 5)}</dd>
        <dt>Raw (lon, lat)</dt>
        <dd className="mono">
          {point.lon.toFixed(6)}, {point.lat.toFixed(6)}
        </dd>
        <dt>CRS</dt>
        <dd className="mono wrap">{point.crs}</dd>
        <dt>Planet</dt>
        <dd>{body.name}</dd>
        <dt>Convention</dt>
        <dd className="small">
          Longitude {body.longitudeConvention.toLowerCase()}, −180…180, degrees. Latitude: {body.id === "MARS"
            ? `as declared by source (planetocentric vs planetographic not stated by NASA Trek capabilities). Interpreted with ${MAP_COORDINATE_CONVENTION.interpretedAs} parameters.`
            : `${body.latitudeType.toLowerCase()}; reference ${body.coordinateSystem}.`}
        </dd>
        <dt>Active layer</dt>
        <dd>{layer.name}</dd>
        <dt>Source</dt>
        <dd>
          NASA Mars Trek WMTS — {layer.mission}, {layer.instrument}
        </dd>
        <dt>Layer resolution</dt>
        <dd>{layer.resolution ?? "not stated"}</dd>
        <dt>Inside layer coverage</dt>
        <dd className={inLayer ? "" : "warn-text"}>{inLayer ? "yes" : "no — no imagery from this layer here"}</dd>
        <dt>Registered DEMs</dt>
        <dd>
          {coverage.status === "loading" && "checking…"}
          {coverage.status === "error" && <span className="error-text">{coverage.error}</span>}
          {coverage.status === "ready" && (demNames.length ? demNames.join(", ") : "none registered here")}
        </dd>
        <dt>Coverage status</dt>
        <dd data-testid="point-coverage-status">
          {cat.status === "loading" && <span className="muted">searching the catalogue…</span>}
          {cat.status === "error" && <span className="error-text">{cat.error}</span>}
          {cat.data && (
            <span className={`status-chip ${cat.data.coverage_status === "AVAILABLE" ? "status-chip--ready" : "status-chip--t-no-data"}`}>
              {cat.data.coverage_status.replaceAll("_", " ")}
            </span>
          )}
        </dd>
        {cat.data?.best && (
          <>
            <dt>Best DEM</dt>
            <dd>
              {cat.data.best.instrument} · {formatResolution(cat.data.best.resolution_m)}{" "}
              <span className="muted small">({cat.data.datasets.length} product{cat.data.datasets.length === 1 ? "" : "s"} cover this point)</span>
            </dd>
            <dt>Dataset quality</dt>
            <dd className="small">
              {cat.data.best.quality_status.replaceAll("_", " ")}
              {typeof cat.data.best.quality?.valid_percent === "number" ? ` · ${cat.data.best.quality.valid_percent.toFixed(0)}% valid cells` : ""} · accuracy{" "}
              {cat.data.best.effective_accuracy.replaceAll("_", " ").toLowerCase()}
            </dd>
          </>
        )}
      </dl>
      <div className="loc-actions">
        <button className="btn btn--small" onClick={() => useAppStore.getState().setTerrainView("split")} title="Local 3D terrain beside the 2D map">
          OPEN LOCAL 3D
        </button>
        <button className="btn btn--small btn--ghost" onClick={() => void runAnalysis()} disabled={!backendOnline || analysis.status === "loading"} title="Slope, roughness and no-data areas derived from the best DEM around this point">
          {analysis.status === "loading" ? "ANALYSING…" : "ANALYSE TERRAIN"}
        </button>
        <button className="btn btn--small btn--ghost" onClick={planRoute} title="Use this point as the route start">
          PLAN ROUTE
        </button>
      </div>
      {analysis.status === "error" && <div className="error-text small">{analysis.error}</div>}
      {analysis.data && <TerrainAnalysis a={analysis.data} />}
      <h4 className="subhead">Terrain</h4>
      <TerrainInfo />
      <LocalTerrain3D />
    </aside>
  );
}

function TerrainAnalysis({ a }: { a: DerivedHazards }) {
  if (a.status === "NO_DATA_COVERAGE") return <div className="warn-text small">{a.message}</div>;
  const by = (c: string) => a.hazards.filter((h) => h.category === c);
  const steep = by("STEEP_SLOPE");
  const rough = by("ROUGH_TERRAIN");
  const gaps = by("MISSING_DATA");
  const maxSlope = Math.max(0, ...steep.map((h) => h.max_value ?? 0));
  const total = (c: string, shown: number) => a.region_totals?.[c] ?? shown;
  return (
    <div className="card small" data-testid="terrain-analysis">
      <strong>Terrain analysis</strong> <span className="muted">{a.dataset?.name} · {a.grid_cell_m ? formatResolution(a.grid_cell_m) : "?"} cells</span>
      <ul className="plain-list">
        <li>
          {steep.length
            ? `${total("STEEP_SLOPE", steep.length)} area(s) steeper than 15° (max ${maxSlope.toFixed(1)}° in the ${steep.length} largest)`
            : "No cell steeper than 15° in the analysed area"}
        </li>
        <li>{rough.length ? `${total("ROUGH_TERRAIN", rough.length)} rough area(s)` : "No rough-terrain threshold set (roughness listed only when a limit is given)"}</li>
        <li>{gaps.length ? `${total("MISSING_DATA", gaps.length)} area(s) without DEM values` : "No missing DEM values in the analysed area"}</li>
      </ul>
      <div className="hint">
        MODEL_ESTIMATED, UNVERIFIED: thresholds on the DEM at its own resolution, not stored and not route constraints. Craters, boulders and
        dunes cannot be derived from a DEM threshold.
      </div>
    </div>
  );
}
