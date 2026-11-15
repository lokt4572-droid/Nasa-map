import { useEffect, useState } from "react";

import { formatDistance, formatLat, formatLon } from "../../config/marsProjection";
import { type GeoSnapshot, POOR_ACCURACY_M, geolocation } from "../../services/geolocationService";
import { useAppStore } from "../../store/useAppStore";

export function useGeolocation(): GeoSnapshot {
  const [snap, setSnap] = useState(geolocation.snapshot);
  useEffect(() => geolocation.subscribe(setSnap), []);
  return snap;
}

export default function LocationPanel() {
  const g = useGeolocation();
  const planet = useAppStore((s) => s.planet);
  const flyTo = useAppStore((s) => s.flyTo);

  // Center the map on every new fix.
  useEffect(() => {
    if (g.fix) flyTo({ lon: g.fix.longitude, lat: g.fix.latitude, zoom: g.fix.accuracy_m > 5000 ? 9 : 14 });
  }, [g.fix, flyTo]);

  return (
    <div className="panel-section">
      <p className="hint">
        Uses your device's location via the browser, only after you press the button. Nothing is stored or sent to the server.
      </p>
      <div className="layer-card__actions">
        <button className="btn" onClick={() => geolocation.locateOnce(planet)} disabled={g.state === "LOCATING" || g.state === "REQUESTING_PERMISSION"}>
          MY LOCATION
        </button>
        {!g.tracking ? (
          <button className="btn btn--ghost" onClick={() => geolocation.startTracking(planet)}>
            START TRACKING
          </button>
        ) : (
          <button className="btn btn--danger" onClick={() => geolocation.stopTracking()}>
            STOP TRACKING
          </button>
        )}
      </div>
      <div className="kv">
        <span className="label">State</span>
        <span className={`status-chip ${g.state === "LOCATED" ? "status-chip--ready" : g.error ? "status-chip--error" : ""}`}>{g.state}</span>
      </div>
      {g.error && <div className="error-text">{g.error}</div>}
      {g.fix && (
        <dl className="dl dl--wide">
          <dt>Latitude</dt>
          <dd className="mono">{formatLat(g.fix.latitude, 6)}</dd>
          <dt>Longitude</dt>
          <dd className="mono">{formatLon(g.fix.longitude, "180", 6)}</dd>
          <dt>Accuracy</dt>
          <dd className={`mono ${g.poorAccuracy ? "warn-text" : ""}`}>± {formatDistance(g.fix.accuracy_m)} (95% radius drawn on map)</dd>
          <dt>Last update</dt>
          <dd className="mono">{new Date(g.fix.timestamp).toLocaleString()}</dd>
          <dt>Speed</dt>
          <dd className="mono">{g.fix.speed_mps !== null ? `${(g.fix.speed_mps * 3.6).toFixed(1)} km/h` : "not reported by the browser"}</dd>
          <dt>Location source</dt>
          <dd className="small">{g.fix.source}</dd>
          <dt>CRS</dt>
          <dd>WGS 84 (EPSG:4326)</dd>
        </dl>
      )}
      {g.poorAccuracy && <div className="warn-text">Accuracy worse than {POOR_ACCURACY_M} m — probably Wi-Fi/IP based, not GPS.</div>}
    </div>
  );
}
