import { useAppStore } from "../../store/useAppStore";
import TerrainInfo from "../terrain/TerrainInfo";

const LEGEND = [
  { label: "below sea level", color: "#2f5d8a" },
  { label: "0 – 500 m", color: "#5e9e5a" },
  { label: "500 – 2000 m", color: "#c8b468" },
  { label: "above 2000 m", color: "#9a6b4a" },
];

/** Earth terrain: real elevation only from a locally imported DEM (Copernicus / GEBCO). */
export default function EarthTerrainPanel() {
  const datasets = useAppStore((s) => s.datasets.data);
  const earthDems = (datasets ?? []).filter((d) => d.planet === "EARTH" && d.status === "VALID");
  return (
    <div className="panel-section">
      <h4 className="subhead">Elevation legend (visualization classes)</h4>
      <ul className="legend-list">
        {LEGEND.map((l) => (
          <li key={l.label}>
            <span className="sym" style={{ background: l.color }} /> {l.label}
          </li>
        ))}
      </ul>
      <p className="hint small">Colours are classes for display; the numeric value is always shown for a selected point.</p>
      <h4 className="subhead">Elevation data</h4>
      {earthDems.length === 0 ? (
        <div className="empty">
          No Earth DEM imported — status REQUIRES_USER_DATA. Download a Copernicus DEM tile (GLO-30/GLO-90, a DSM referenced to
          EGM2008) or a GEBCO_2026 tile, then: <code>python manage.py import_dem --planet EARTH --file … --name …</code>
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
