import { type TerrainProduct, useAppStore } from "../../store/useAppStore";

const PRODUCTS: { id: TerrainProduct; label: string; legend: string }[] = [
  { id: "elevation", label: "Elevation map", legend: "low → high (stretched to the visible range)" },
  { id: "hillshade", label: "Hillshade", legend: "sun azimuth 315°, altitude 45°" },
  { id: "slope", label: "Slope map", legend: "green 0° → yellow 10° → orange 20° → red 30° → dark red ≥ 45°" },
  { id: "aspect", label: "Aspect map", legend: "hue = downslope direction, clockwise from north" },
  { id: "roughness", label: "Roughness map", legend: "TRI, dark → bright (98th percentile scale)" },
];

/** Controls for terrain visualization layers rendered from the numeric DEM. */
export default function TerrainLayers() {
  const overlay = useAppStore((s) => s.terrainOverlay);
  const datasets = useAppStore((s) => s.datasets.data);
  const setTerrainOverlay = useAppStore((s) => s.setTerrainOverlay);
  const dem = datasets?.find((d) => d.status === "VALID" && d.data_type === "DEM" && (d.planet ?? "MARS") === "MARS");
  const current = PRODUCTS.find((p) => p.id === overlay.product);

  return (
    <div className="card">
      <strong>Terrain layers (from DEM)</strong>
      <p className="hint small">
        Visual products computed from numeric DEM values. Colours are not measurements: use the point tools for values.
      </p>
      {!dem && <div className="empty">No validated Mars DEM registered — import one in Data Manager.</div>}
      {dem && (
        <>
          <div className="hint small">
            Source: {dem.name} ({dem.resolution_meters ? `${(dem.resolution_meters / 1000).toFixed(2)} km/cell` : "resolution n/a"})
          </div>
          <label className="check">
            <input type="radio" checked={overlay.product === null} onChange={() => setTerrainOverlay({ product: null, meta: null, status: "idle" })} />
            None
          </label>
          {PRODUCTS.map((p) => (
            <label className="check" key={p.id}>
              <input type="radio" checked={overlay.product === p.id} onChange={() => setTerrainOverlay({ product: p.id })} />
              {p.label}
            </label>
          ))}
          <div className="layer-card__row">
            <span className="label">Opacity</span>
            <input type="range" min={0} max={1} step={0.05} value={overlay.opacity} onChange={(e) => setTerrainOverlay({ opacity: Number(e.target.value) })} aria-label="Terrain layer opacity" />
            <span className="mono">{Math.round(overlay.opacity * 100)}%</span>
          </div>
          {current && <div className="hint small">Legend: {current.legend}</div>}
          {overlay.status === "loading" && <div className="hint">Rendering…</div>}
          {overlay.status === "error" && <div className="error-text">{overlay.error}</div>}
          {overlay.status === "ready" && overlay.meta && (
            <div className="hint small mono">
              range {overlay.meta.min?.toFixed(1)} … {overlay.meta.max?.toFixed(1)} {overlay.meta.units}; valid{" "}
              {overlay.meta.validFraction !== null ? `${(overlay.meta.validFraction * 100).toFixed(0)}%` : "?"}
            </div>
          )}
        </>
      )}
    </div>
  );
}
