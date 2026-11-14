import { layersForPlanet } from "../../config/mapLayers";
import { mapController } from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";

const STATUS_LABEL = { idle: "NOT LOADED", loading: "LOADING", ready: "READY", error: "ERROR" } as const;

export default function LayerSelector() {
  const planet = useAppStore((s) => s.planet);
  const planetLayers = layersForPlanet(planet);
  const layers = useAppStore((s) => s.layers);
  const activeLayerId = useAppStore((s) => s.activeLayerId);
  const { setLayerVisible, setLayerOpacity, setActiveLayer, retryLayer } = useAppStore.getState();

  return (
    <div className="panel-section">
      <p className="hint">
        NASA Mars Trek WMTS layers. Tile grids are read from each layer's GetCapabilities. Pixels are imagery, never
        elevation values.
      </p>
      {planetLayers.map((cfg) => {
        const st = layers[cfg.id]!;
        return (
          <div key={cfg.id} className={`layer-card ${activeLayerId === cfg.id ? "layer-card--active" : ""}`}>
            <div className="layer-card__head">
              <label className="check">
                <input
                  type="checkbox"
                  checked={st.visible}
                  onChange={(e) => setLayerVisible(cfg.id, e.target.checked)}
                  aria-label={`Show ${cfg.name}`}
                />
                <span className="layer-card__name">{cfg.name}</span>
              </label>
              <span className={`status-chip status-chip--${st.status}`}>{STATUS_LABEL[st.status]}</span>
            </div>
            <div className="layer-card__meta">
              {cfg.instrument} · {cfg.resolution ?? "resolution n/a"} · {cfg.coverage === "global" ? "Global" : "Regional"} ·{" "}
              {cfg.category}
            </div>
            <div className="layer-card__row">
              <span className="label">Opacity</span>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={st.opacity}
                onChange={(e) => setLayerOpacity(cfg.id, Number(e.target.value))}
                aria-label={`Opacity of ${cfg.name}`}
              />
              <span className="mono">{Math.round(st.opacity * 100)}%</span>
            </div>
            <div className="layer-card__actions">
              <button className="btn btn--small btn--ghost" onClick={() => setActiveLayer(cfg.id)} disabled={activeLayerId === cfg.id}>
                {activeLayerId === cfg.id ? "Active" : "Set active"}
              </button>
              {cfg.coverage === "regional" && (
                <button className="btn btn--small btn--ghost" onClick={() => mapController.zoomToBBox(cfg.bbox)}>
                  Zoom to coverage
                </button>
              )}
              {st.status === "error" && (
                <button className="btn btn--small" onClick={() => retryLayer(cfg.id)}>
                  Retry
                </button>
              )}
            </div>
            {st.status === "ready" && st.tiles.errors > 0 && (
              <div className="warn-text">{st.tiles.errors} tile request(s) failed (missing tiles or network).</div>
            )}
            {st.error && <div className="error-text">{st.error}</div>}
          </div>
        );
      })}
    </div>
  );
}
