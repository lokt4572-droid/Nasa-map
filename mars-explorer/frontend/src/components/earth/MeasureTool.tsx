import { getLength } from "ol/sphere";
import LineString from "ol/geom/LineString";
import { fromLonLat } from "ol/proj";

import { formatDistance } from "../../config/marsProjection";
import { useAppStore } from "../../store/useAppStore";

export default function MeasureTool() {
  const m = useAppStore((s) => s.earth.measure);
  const setEarth = useAppStore((s) => s.setEarth);
  const len = m.points.length > 1 ? getLength(new LineString(m.points.map((p) => fromLonLat(p)))) : 0;
  return (
    <div className="card">
      <strong>Measure distance</strong>
      <div className="layer-card__actions">
        <button className="btn btn--small btn--ghost" onClick={() => setEarth({ measure: { active: !m.active, points: m.active ? m.points : [] } })}>
          {m.active ? "Finish" : "Start measuring"}
        </button>
        <button className="btn btn--small btn--ghost" onClick={() => setEarth({ measure: { active: m.active, points: [] } })} disabled={!m.points.length}>
          Clear
        </button>
      </div>
      <div className="mono">{m.points.length > 1 ? formatDistance(len) : "—"}</div>
      <div className="hint small">Geodesic length on a sphere of radius 6 371 008.8 m (ol/sphere); error vs. the WGS 84 ellipsoid ≲ 0.5 %.</div>
    </div>
  );
}
