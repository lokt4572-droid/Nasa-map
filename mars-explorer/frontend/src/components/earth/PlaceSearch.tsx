import { type FormEvent, useRef, useState } from "react";

import { describeError } from "../../services/api";
import { type PlaceResult, searchPlaces } from "../../services/earthService";
import { useAppStore } from "../../store/useAppStore";

/** Parse "lat, lon" (decimal degrees) typed by the user. Returns null if it is not coordinates. */
export function parseCoordinates(text: string): { lat: number; lon: number } | null {
  const m = text.trim().match(/^(-?\d+(?:\.\d+)?)\s*[,;\s]\s*(-?\d+(?:\.\d+)?)$/);
  if (!m) return null;
  const lat = Number(m[1]);
  const lon = Number(m[2]);
  if (!(lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180)) return null;
  return { lat, lon };
}

/**
 * Explicit search only (Enter / button): no autocomplete, as required by the Nominatim
 * usage policy. Coordinates work even when Nominatim is unavailable.
 */
export default function PlaceSearch() {
  const [q, setQ] = useState("");
  const [state, setState] = useState<{ busy: boolean; error: string | null; results: PlaceResult[]; note: string | null }>({ busy: false, error: null, results: [], note: null });
  const ctrl = useRef<AbortController | null>(null);
  const { flyTo, selectPoint } = useAppStore.getState();

  const pick = (lat: number, lon: number, bbox?: [number, number, number, number]) => {
    flyTo(bbox ? { lon, lat, bbox } : { lon, lat, zoom: 11 });
    selectPoint({ lon, lat, crs: "EPSG:4326", layerId: "", pickedAt: new Date().toISOString() });
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const coords = parseCoordinates(q);
    if (coords) {
      pick(coords.lat, coords.lon);
      setState({ busy: false, error: null, results: [], note: "Coordinates (WGS 84, lat, lon)." });
      return;
    }
    if (q.trim().length < 2 || state.busy) return;
    ctrl.current?.abort();
    ctrl.current = new AbortController();
    setState({ busy: true, error: null, results: [], note: null });
    try {
      const r = await searchPlaces(q.trim(), ctrl.current.signal);
      setState({ busy: false, error: null, results: r.results, note: `${r.attribution}${r.from_cache ? " · cached" : ""}` });
    } catch (err) {
      setState({ busy: false, error: `${describeError(err)} — you can still type coordinates, e.g. 48.8584, 2.2945`, results: [], note: null });
    }
  };

  return (
    <div className="panel-section">
      <form className="form form--inline" onSubmit={submit}>
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search location, city, country..." aria-label="Search location" />
        <button className="btn btn--small" disabled={state.busy}>
          {state.busy ? "…" : "Search"}
        </button>
      </form>
      <p className="hint small">Press Enter to search (no autocomplete). Or type coordinates: “lat, lon”.</p>
      {state.error && <div className="error-text">{state.error}</div>}
      {state.results.length === 0 && state.note === null && !state.error && !state.busy && <div className="empty">No search yet.</div>}
      <ul className="item-list">
        {state.results.map((r, i) => (
          <li key={i} className="item">
            <button className="item__main" onClick={() => pick(r.lat, r.lon, r.bbox ? [r.bbox.west, r.bbox.south, r.bbox.east, r.bbox.north] : undefined)}>
              <strong>{r.name}</strong>
              <div className="muted small mono">
                {r.lat.toFixed(4)}, {r.lon.toFixed(4)} · {r.category}/{r.type}
              </div>
            </button>
          </li>
        ))}
      </ul>
      {state.note && <div className="hint small">{state.note}</div>}
    </div>
  );
}
