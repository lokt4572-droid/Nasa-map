import { bboxContains, getLayerConfig } from "../../config/mapLayers";
import { MAP_COORDINATE_CONVENTION, formatLat, formatLon } from "../../config/marsProjection";
import { useAppStore } from "../../store/useAppStore";
import TerrainInfo from "../terrain/TerrainInfo";

export default function RightPanel() {
  const point = useAppStore((s) => s.selectedPoint);
  const coverage = useAppStore((s) => s.pointInfo.coverage);
  const lonMode = useAppStore((s) => s.settings.lonMode);
  const selectPoint = useAppStore((s) => s.selectPoint);

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
        <dt>Convention</dt>
        <dd className="small">
          Longitude east-positive −180…180, degrees. Latitude: as declared by source (planetocentric vs planetographic not
          stated by NASA Trek capabilities). Interpreted with {MAP_COORDINATE_CONVENTION.interpretedAs} parameters.
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
        <dt>DEM availability</dt>
        <dd>
          {coverage.status === "loading" && "checking…"}
          {coverage.status === "error" && <span className="error-text">{coverage.error}</span>}
          {coverage.status === "ready" && (demNames.length ? demNames.join(", ") : "no validated DEM covers this point")}
        </dd>
      </dl>
      <h4 className="subhead">Terrain</h4>
      <TerrainInfo />
    </aside>
  );
}
