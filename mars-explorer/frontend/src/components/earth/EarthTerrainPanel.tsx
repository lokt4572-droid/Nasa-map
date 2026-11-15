import { describeError } from "../../services/api";
import { ELEVATION_STOPS, SLOPE_STOPS, cssGradient, renderEarthTerrain } from "../../services/earthTerrainService";
import { type EarthTerrainState, useAppStore } from "../../store/useAppStore";
import TerrainInfo from "../terrain/TerrainInfo";

const PRODUCTS = [
  { id: "hillshade", label: "Hillshade" },
  { id: "elevation", label: "Elevation colours" },
  { id: "slope", label: "Slope" },
] as const;

/** Terrain colours for the current view, rendered from Copernicus DEM GLO-30 (real values). */
function TerrainColours() {
  const terrain = useAppStore((s) => s.earth.terrain);
  const extent = useAppStore((s) => s.view.extent);
  const backendOnline = useAppStore((s) => s.backend.status === "online");
  const setEarth = useAppStore((s) => s.setEarth);
  const set = (t: Partial<EarthTerrainState>) => setEarth({ terrain: { ...useAppStore.getState().earth.terrain, ...t } });
  const run = async (product: EarthTerrainState["product"]) => {
    if (!extent || extent.length !== 4) return;
    const old = useAppStore.getState().earth.terrain.images;
    set({ product, status: "loading", message: null });
    try {
      const r = await renderEarthTerrain(extent as [number, number, number, number], product);
      old.forEach((i) => URL.revokeObjectURL(i.url));
      set(
        r.status === "ready"
          ? { status: "ready", images: r.images, missingTiles: r.missingTiles, message: r.missingTiles ? `${r.missingTiles} part(s) of the view have no DEM tile (ocean or unreleased) and stay empty.` : null }
          : { status: "no-data", images: [], missingTiles: 0, message: r.message },
      );
    } catch (err) {
      set({ status: "error", message: describeError(err) });
    }
  };
  const clear = () => {
    terrain.images.forEach((i) => URL.revokeObjectURL(i.url));
    set({ status: "idle", images: [], missingTiles: 0, message: null });
  };
  const imgs = terrain.images;
  const finite = (xs: (number | null)[]) => xs.filter((x): x is number => x !== null && Number.isFinite(x));
  const lo = Math.min(...finite(imgs.map((i) => i.min)));
  const hi = Math.max(...finite(imgs.map((i) => i.max)));
  const img = imgs[0];
  return (
    <div className="card" data-testid="earth-terrain-colours">
      <strong>Terrain colours from a DEM</strong>
      <p className="hint small">
        Copernicus DEM GLO-30 (≈30 m, a surface model: buildings and trees included), read for the current view. Land only — oceans have
        no tiles and stay empty.
      </p>
      <div className="layer-card__actions">
        {PRODUCTS.map((p) => (
          <button key={p.id} className={`btn btn--small ${terrain.product === p.id && img ? "" : "btn--ghost"}`} disabled={!backendOnline || terrain.status === "loading"} onClick={() => void run(p.id)}>
            {p.label}
          </button>
        ))}
        {img && (
          <button className="btn btn--small btn--ghost" onClick={clear}>
            Clear
          </button>
        )}
      </div>
      {terrain.status === "loading" && <div className="hint small">Reading the DEM window (a first read of a tile can take 10–30 s)…</div>}
      {terrain.message && <div className={terrain.status === "error" ? "error-text small" : "warn-text small"}>{terrain.message}</div>}
      {img && (
        <dl className="dl small">
          <dt>Tiles</dt>
          <dd className="mono">{imgs.map((i) => i.tile.replace("Copernicus_DSM_COG_10_", "").replace("_DEM", "")).join(", ")}</dd>
          <dt>{terrain.product === "hillshade" ? "Shading" : "Values"}</dt>
          <dd className="mono">
            {terrain.product === "hillshade"
              ? "relative illumination (visual product, not a measurement)"
              : Number.isFinite(lo) && Number.isFinite(hi)
                ? `${lo.toFixed(terrain.product === "slope" ? 1 : 0)} – ${hi.toFixed(terrain.product === "slope" ? 1 : 0)} ${terrain.product === "slope" ? "°" : img.units || "m"}`
                : "—"}
          </dd>
          <dt>Datum</dt>
          <dd>EGM2008 geoid (Copernicus specification)</dd>
          {terrain.product !== "hillshade" && (
            <>
              <dt>Legend</dt>
              <dd>
                <div className="lt3d__bar" style={{ background: cssGradient(terrain.product === "slope" ? SLOPE_STOPS : ELEVATION_STOPS) }} />
                <div className="lt3d__barlabels mono">
                  <span>{terrain.product === "slope" ? "0°" : Number.isFinite(lo) ? `${lo.toFixed(0)} m` : ""}</span>
                  <span>{terrain.product === "slope" ? "45°+" : Number.isFinite(hi) ? `${hi.toFixed(0)} m` : ""}</span>
                </div>
                <div className="hint small">
                  {terrain.product === "slope" ? "Fixed scale for every view." : imgs.length > 1 ? "One range shared by all tiles in the view." : "Stretched to this view's range."} Colours are a
                  visualisation; click the map for the value at a point.
                </div>
              </dd>
            </>
          )}
          <dt>Opacity</dt>
          <dd>
            <input type="range" min={0.2} max={1} step={0.05} value={terrain.opacity} onChange={(e) => set({ opacity: Number(e.target.value) })} aria-label="Terrain opacity" />
          </dd>
        </dl>
      )}
      <div className="hint small">Bathymetry: NO DATA COVERAGE — no keyless gridded bathymetry source is configured (a GEBCO tile can be imported with import_dem). The Blue Marble relief layer is imagery, not depth values.</div>
    </div>
  );
}

/** Earth terrain: real elevation from Copernicus GLO-30 tiles or a locally imported DEM. */
export default function EarthTerrainPanel() {
  const datasets = useAppStore((s) => s.datasets.data);
  const earthDems = (datasets ?? []).filter((d) => d.planet === "EARTH" && d.status === "VALID");
  return (
    <div className="panel-section">
      <TerrainColours />
      <h4 className="subhead">Imported elevation data</h4>
      {earthDems.length === 0 ? (
        <div className="empty">
          No local Earth DEM imported. Copernicus GLO-30 tiles are read remotely on demand (above, and in local 3D / routing with
          catalogue DTMs). For offline use or bathymetry, import a file: <code>python manage.py import_dem --planet EARTH --file … --name …</code>
        </div>
      ) : (
        <ul className="plain-list">
          {earthDems.map((d) => (
            <li key={d.id}>
              {d.name} — {d.resolution_meters ? `${d.resolution_meters.toFixed(0)} m` : "?"}, datum {d.vertical_datum}
            </li>
          ))}
        </ul>
      )}
      <TerrainInfo compact />
      <p className="hint small">
        Copernicus DEM is a surface model (buildings, vegetation). GEBCO bathymetry quality varies; parts are interpolated; not for
        navigation.
      </p>
    </div>
  );
}
