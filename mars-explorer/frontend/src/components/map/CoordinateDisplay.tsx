import { layersForPlanet, bboxContains, getLayerConfig } from "../../config/mapLayers";
import { formatDistance, formatLat, formatLon, groundResolutionM, niceScaleBar } from "../../config/marsProjection";
import { PLANETS, planetE2 } from "../../config/planetRegistry";
import { nativeResolutionDeg, shownAtCenter, viewScale } from "../../services/adaptiveLayers";
import { useAppStore } from "../../store/useAppStore";

/** Bottom status bar: scale, cursor position, current layer, coverage, loading status. */
export default function CoordinateDisplay() {
  const planet = useAppStore((s) => s.planet);
  const planetLayers = layersForPlanet(planet);
  const cursor = useAppStore((s) => s.cursor);
  const view = useAppStore((s) => s.view);
  const layers = useAppStore((s) => s.layers);
  const activeLayerId = useAppStore((s) => s.activeLayerId);
  const lonMode = useAppStore((s) => s.settings.lonMode);
  const active = activeLayerId ? getLayerConfig(activeLayerId) : null;

  const body = PLANETS[planet];
  // Scale on the current body's own reference figure (never Earth's).
  const ground = groundResolutionM(view.resolution, view.centerLat, body.radiusEquatorial, planetE2(body));
  const bar = niceScaleBar(ground.ew);

  const loading = planetLayers.reduce((n, l) => n + (layers[l.id]?.visible ? (layers[l.id]?.tiles.loading ?? 0) : 0), 0);
  const anyLoadingCaps = planetLayers.some((l) => layers[l.id]?.status === "loading");
  const anyError = planetLayers.some((l) => layers[l.id]?.visible && layers[l.id]?.status === "error");
  const loadStatus = anyError ? "ERROR" : anyLoadingCaps ? "CAPABILITIES…" : loading > 0 ? `TILES ${loading}` : "IDLE";

  const covered = cursor && active ? bboxContains(active.bbox, cursor.lon, cursor.lat) : null;

  // What is drawn at the view centre, and whether finer data exists there (Phase 2).
  const states = Object.fromEntries(
    planetLayers.map((l) => [l.id, layers[l.id] && { ...layers[l.id]!, gridResolutions: layers[l.id]!.grid?.resolutionsDegPerPx ?? null }]),
  );
  const center = shownAtCenter(planetLayers, states, view.centerLon ?? 0, view.centerLat, view.resolution);
  const scale = viewScale(view.resolution, body.radiusEquatorial);
  const finerHidden = center.finest && center.shown && center.finest.id !== center.shown.id
    && nativeResolutionDeg(center.finest, states[center.finest.id]?.gridResolutions) < nativeResolutionDeg(center.shown, states[center.shown.id]?.gridResolutions);

  return (
    <footer className="statusbar">
      <div className="statusbar__item" title={`Scale on the ${body.name} reference figure (east-west, at view centre latitude)`}>
        <span className="label">Scale</span>
        <span className="scalebar" style={{ width: `${bar.px}px` }} />
        <span className="mono">{formatDistance(bar.meters)}</span>
        <span className="muted mono">({formatDistance(ground.ew)}/px)</span>
      </div>
      <div className="statusbar__item">
        <span className="label">Cursor</span>
        <span className="mono">{cursor ? `${formatLat(cursor.lat)}  ${formatLon(cursor.lon, lonMode)}` : "—"}</span>
      </div>
      <div className="statusbar__item">
        <span className="label">Layer</span>
        <span>{active?.name ?? "—"}</span>
      </div>
      <div className="statusbar__item" data-testid="status-shown" title="Top-most visible layer at the view centre. Different instruments are different measurements, never substitutes.">
        <span className="label">View</span>
        <span className="mono">{scale}</span>
        <span>
          {center.shown ? `${center.shown.instrument} ${center.shown.resolution ?? ""}` : "no layer"}
        </span>
        {center.overzoomed && <span className="warn-text">· beyond native resolution (pixels enlarged)</span>}
        {finerHidden && center.finest && <span className="muted">· finer here: {center.finest.instrument} {center.finest.resolution}</span>}
      </div>
      <div className="statusbar__item">
        <span className="label">Coverage</span>
        <span className={covered === false ? "warn-text" : ""}>
          {covered === null ? "—" : covered ? "inside layer extent" : "outside layer extent"}
        </span>
      </div>
      <div className="statusbar__item">
        <span className="label">Map</span>
        <span className={`mono ${anyError ? "error-text" : ""}`}>{loadStatus}</span>
      </div>
    </footer>
  );
}
