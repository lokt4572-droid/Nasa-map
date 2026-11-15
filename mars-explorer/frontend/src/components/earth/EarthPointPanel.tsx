import { useEffect, useState } from "react";

import { formatLat, formatLon } from "../../config/marsProjection";
import { describeError } from "../../services/api";
import { type WeatherEnvelope, getCurrentWeather } from "../../services/earthService";
import { useAppStore } from "../../store/useAppStore";
import LocalTerrain3D from "../terrain/LocalTerrain3D";
import TerrainInfo from "../terrain/TerrainInfo";

/** Right-hand details for a selected Earth point: coordinates, elevation, weather, local time. */
export default function EarthPointPanel() {
  const point = useAppStore((s) => s.selectedPoint);
  const coverage = useAppStore((s) => s.pointInfo.coverage);
  const selectPoint = useAppStore((s) => s.selectPoint);
  const [wx, setWx] = useState<{ data: WeatherEnvelope<Record<string, number | null>> | null; error: string | null }>({ data: null, error: null });

  useEffect(() => {
    if (!point || point.crs !== "EPSG:4326") return;
    const ctrl = new AbortController();
    setWx({ data: null, error: null });
    getCurrentWeather(point.lat, point.lon, ctrl.signal)
      .then((data) => setWx({ data, error: null }))
      .catch((err) => !ctrl.signal.aborted && setWx({ data: null, error: describeError(err) }));
    return () => ctrl.abort();
  }, [point]);

  if (!point) {
    return (
      <aside className="rightpanel rightpanel--empty">
        <h3 className="panel-title">Point Information</h3>
        <div className="empty">Click the Earth map or search a place.</div>
      </aside>
    );
  }
  const w = wx.data;
  return (
    <aside className="rightpanel">
      <div className="layer-card__head">
        <h3 className="panel-title">Point Information</h3>
        <button className="btn btn--icon" title="Clear selection" onClick={() => selectPoint(null)}>
          ×
        </button>
      </div>
      <dl className="dl dl--wide">
        <dt>Planet</dt>
        <dd>Earth</dd>
        <dt>Latitude</dt>
        <dd className="mono big">{formatLat(point.lat, 5)}</dd>
        <dt>Longitude</dt>
        <dd className="mono big">{formatLon(point.lon, "180", 5)}</dd>
        <dt>CRS</dt>
        <dd className="mono">EPSG:4326 (WGS 84, geodetic latitude)</dd>
        <dt>Dataset</dt>
        <dd>{coverage.data?.datasets.map((d) => d.name).join(", ") || "no Earth DEM covers this point"}</dd>
        <dt>Local time</dt>
        <dd className="mono">{w?.valid_time ? `${w.valid_time.replace("T", " ")} (${w.timezone}, model time step)` : "—"}</dd>
        <dt>Sunrise / sunset</dt>
        <dd className="mono">{w?.today?.sunrise ? `${w.today.sunrise.slice(11)} / ${w.today.sunset?.slice(11)}` : "—"}</dd>
        <dt>Weather</dt>
        <dd>
          {w ? (
            <span className="mono">
              {String(w.data.temperature_2m)} {String(w.units.temperature_2m)}, wind {String(w.data.wind_speed_10m)} {String(w.units.wind_speed_10m)}, cloud{" "}
              {String(w.data.cloud_cover)}%
            </span>
          ) : wx.error ? (
            <span className="error-text">{wx.error}</span>
          ) : (
            "loading…"
          )}
          {w && <div className="hint small">Open-Meteo forecast model (not a measurement). Weather data by Open-Meteo.com</div>}
        </dd>
      </dl>
      <h4 className="subhead">Elevation</h4>
      <TerrainInfo compact />
      <LocalTerrain3D />
    </aside>
  );
}
