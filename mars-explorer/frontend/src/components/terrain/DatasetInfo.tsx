import { getLayerConfig } from "../../config/mapLayers";
import { MARS_2000_PROJ4 } from "../../config/marsProjection";
import { useAppStore } from "../../store/useAppStore";

const DOC_LINKS = [
  { href: "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars", label: "NASA Mars Trek WMTS API" },
  { href: "https://pds-geosciences.wustl.edu/missions/mgs/mola.html", label: "PDS Geosciences — MGS MOLA" },
  { href: "https://hirise.lpl.arizona.edu/dtm/about.php", label: "HiRISE DTM — about" },
];

/** Scientific metadata of the active map layer, including what was read from GetCapabilities. */
export default function DatasetInfo() {
  const activeLayerId = useAppStore((s) => s.activeLayerId);
  const st = useAppStore((s) => s.layers[activeLayerId]);
  const cfg = getLayerConfig(activeLayerId);
  const grid = st?.grid;
  const b = cfg.bbox;
  return (
    <div className="panel-section">
      <h4 className="subhead">{cfg.name}</h4>
      <p className="hint">{cfg.description}</p>
      <dl className="dl">
        <dt>Trek layer ID</dt>
        <dd className="mono wrap">{cfg.layerId}</dd>
        <dt>Mission / instrument</dt>
        <dd>
          {cfg.mission} / {cfg.instrument}
        </dd>
        <dt>Data kind</dt>
        <dd>{cfg.dataKind === "COLOR_HILLSHADE" ? "Colour hillshade (visualization)" : cfg.dataKind === "THERMAL_IR_MOSAIC" ? "Thermal-infrared mosaic" : "Orthoimage"} — not elevation data</dd>
        <dt>Stated resolution</dt>
        <dd>{cfg.resolution ?? "not stated"}</dd>
        <dt>Coverage (W, S, E, N)</dt>
        <dd className="mono">
          {b.west.toFixed(4)}, {b.south.toFixed(4)}, {b.east.toFixed(4)}, {b.north.toFixed(4)}
        </dd>
        <dt>CRS (as declared)</dt>
        <dd className="mono wrap">{cfg.crs}</dd>
        <dt>Interpreted with</dt>
        <dd className="mono wrap">ESRI:104905 — {MARS_2000_PROJ4}</dd>
        <dt>Longitude</dt>
        <dd>East-positive, −180…180</dd>
        <dt>Latitude</dt>
        <dd>As declared by source (ocentric/ographic not stated in capabilities)</dd>
        <dt>Vertical datum</dt>
        <dd>Not applicable (image layer)</dd>
        <dt>Format</dt>
        <dd>{cfg.format}</dd>
        <dt>GetCapabilities</dt>
        <dd>
          <a href={cfg.capabilitiesUrl} target="_blank" rel="noreferrer">
            open XML
          </a>
        </dd>
      </dl>
      <h4 className="subhead">Tile grid (from GetCapabilities)</h4>
      {grid ? (
        <dl className="dl">
          <dt>TileMatrixSet</dt>
          <dd className="mono">{grid.matrixSet}</dd>
          <dt>TileMatrix IDs</dt>
          <dd className="mono">
            {grid.matrixIds[0]} … {grid.matrixIds[grid.matrixIds.length - 1]} ({grid.matrixIds.length} levels)
          </dd>
          <dt>Resolution range</dt>
          <dd className="mono">
            {grid.resolutionsDegPerPx[0]?.toExponential(4)} … {grid.resolutionsDegPerPx[grid.resolutionsDegPerPx.length - 1]?.toExponential(4)} °/px
          </dd>
          <dt>Origin</dt>
          <dd className="mono">{grid.origin.join(", ")}</dd>
          <dt>Projection</dt>
          <dd className="mono wrap">{grid.projection}</dd>
        </dl>
      ) : (
        <p className="hint">Not loaded yet — enable the layer to read its capabilities.</p>
      )}
      <h4 className="subhead">References</h4>
      <ul className="plain-list">
        {DOC_LINKS.map((l) => (
          <li key={l.href}>
            <a href={l.href} target="_blank" rel="noreferrer">
              {l.label}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
