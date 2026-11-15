import { useEffect } from "react";

import { describeError } from "../../services/api";
import { type GibsLayer, dateAvailable, getGibsLayers, stepDate, subDailyTimes, timeValue } from "../../services/earthService";
import { useAppStore } from "../../store/useAppStore";

const GROUP_LABEL = { SATELLITE: "Satellite imagery", ATMOSPHERE: "Atmosphere", PRECIPITATION: "Precipitation", REFERENCE: "Reference", GEOSTATIONARY: "Geostationary (10-minute, regional discs)" };

/** Loads the GIBS discovery once per session (backend caches the capabilities for 24 h). */
export function useGibsDiscovery() {
  const gibs = useAppStore((s) => s.earth.gibs);
  const setEarth = useAppStore((s) => s.setEarth);
  useEffect(() => {
    if (gibs.status !== "idle") return;
    setEarth({ gibs: { status: "loading", data: null, error: null } });
    getGibsLayers()
      .then((data) => setEarth({ gibs: { status: "ready", data, error: null } }))
      .catch((err) => setEarth({ gibs: { status: "error", data: null, error: describeError(err) } }));
  }, [gibs.status, setEarth]);
}

function DateControl({ layer }: { layer: GibsLayer }) {
  const dates = useAppStore((s) => s.earth.dates);
  const setEarth = useAppStore((s) => s.setEarth);
  const t = layer.time;
  if (!t) return <div className="hint small">Static layer (no time dimension).</div>;
  if (!t.daily) return <SubDailyControl layer={layer} />;
  const latest = (t.latest ?? "").slice(0, 10);
  const date = (dates[layer.id] ?? latest).slice(0, 10);
  const ok = dateAvailable(t, date);
  const setDate = (d: string | null) => d && setEarth({ dates: { ...dates, [layer.id]: d } });
  return (
    <div className="date-control">
      <div className="layer-card__row">
        <button className="btn btn--small btn--ghost" onClick={() => setDate(stepDate(t, date, -1))} title="Previous available day">
          ◀
        </button>
        <input type="date" value={date} min={(t.first ?? "").slice(0, 10)} max={latest} onChange={(e) => setDate(e.target.value)} aria-label={`Date for ${layer.title}`} />
        <button className="btn btn--small btn--ghost" onClick={() => setDate(stepDate(t, date, 1))} disabled={date >= latest} title="Next available day">
          ▶
        </button>
        <button className="btn btn--small btn--ghost" onClick={() => setDate(latest)}>
          Latest
        </button>
      </div>
      <div className="hint small">
        Showing <span className="mono">{date}</span> (UTC day). Latest published: <span className="mono">{latest}</span> — from
        GetCapabilities; recent days may be partial. Not live.
      </div>
      {!ok && <div className="warn-text small">No imagery published for {date} (gap in the time domain). Layer hidden.</div>}
    </div>
  );
}

/** Time picker for sub-daily layers: only the timestamps GIBS publishes (UTC). */
function SubDailyControl({ layer }: { layer: GibsLayer }) {
  const dates = useAppStore((s) => s.earth.dates);
  const setEarth = useAppStore((s) => s.setEarth);
  const times = subDailyTimes(layer.time, 144);
  const current = timeValue(layer, dates[layer.id]);
  const i = current ? times.indexOf(current) : -1;
  const set = (v: string | undefined) => v && setEarth({ dates: { ...dates, [layer.id]: v } });
  if (!times.length) return <div className="warn-text small">No sub-daily times are published for this layer right now.</div>;
  const period = layer.time?.intervals[layer.time.intervals.length - 1]?.period ?? "";
  return (
    <div className="date-control" data-testid={`subdaily-${layer.id}`}>
      <div className="layer-card__row">
        <button className="btn btn--small btn--ghost" onClick={() => set(times[i + 1])} disabled={i < 0 || i >= times.length - 1} title="Earlier published time">
          ◀
        </button>
        <select value={current ?? ""} onChange={(e) => set(e.target.value)} aria-label={`Time for ${layer.title}`}>
          {times.map((t) => (
            <option key={t} value={t}>
              {t.replace("T", " ").replace(":00Z", " UTC")}
            </option>
          ))}
        </select>
        <button className="btn btn--small btn--ghost" onClick={() => set(times[i - 1])} disabled={i <= 0} title="Later published time">
          ▶
        </button>
        <button className="btn btn--small btn--ghost" onClick={() => set(times[0])}>
          Latest
        </button>
      </div>
      <div className="hint small">
        Published every {period.replace("PT", "").toLowerCase()} (GetCapabilities); only listed times exist. Latest: {times[0]!.replace("T", " ").replace(":00Z", " UTC")}. Not live.
        {layer.coverage ? ` Coverage: ${layer.coverage}; no data outside this disc.` : ""}
      </div>
    </div>
  );
}

function LayerMeta({ layer }: { layer: GibsLayer }) {
  return (
    <dl className="dl small">
      <dt>Instrument</dt>
      <dd>{layer.instrument}</dd>
      <dt>Satellite</dt>
      <dd>{layer.platform}</dd>
      <dt>Source</dt>
      <dd>{layer.source}</dd>
      <dt>Pixel at max zoom</dt>
      <dd>{layer.pixel_size_at_equator_m ? `≈ ${layer.pixel_size_at_equator_m} m (equator, z${layer.max_zoom})` : "—"}</dd>
      <dt>Time resolution</dt>
      <dd>{layer.time ? (layer.time.daily ? "daily" : "sub-daily") : "static"}</dd>
      <dt>Temporal coverage</dt>
      <dd className="mono">
        {layer.time ? `${layer.time.first?.slice(0, 10)} … ${layer.time.latest?.slice(0, 10)} (${layer.time.intervals.length} interval${layer.time.intervals.length > 1 ? "s" : ""})` : "—"}
      </dd>
      <dt>CRS</dt>
      <dd>{layer.crs} ({layer.tile_matrix_set})</dd>
      <dt>Status</dt>
      <dd>{layer.status}</dd>
      <dt>Attribution</dt>
      <dd>{layer.attribution}</dd>
    </dl>
  );
}

export default function EarthLayersPanel({ groups }: { groups: GibsLayer["group"][] }) {
  useGibsDiscovery();
  const earth = useAppStore((s) => s.earth);
  const setEarth = useAppStore((s) => s.setEarth);
  const layers = earth.gibs.data?.layers ?? [];
  const showBase = groups.includes("SATELLITE");

  return (
    <div className="panel-section">
      {showBase && (
        <>
          <h4 className="subhead">Base map</h4>
          <label className="check">
            <input type="radio" checked={earth.base === "OSM"} onChange={() => setEarth({ base: "OSM" })} />
            Street map — OpenStreetMap (© OpenStreetMap contributors)
          </label>
          <p className="hint small">OSM tiles: viewing only, never downloaded for offline use (OSMF tile policy).</p>
        </>
      )}
      {earth.gibs.status === "loading" && <div className="hint">Reading NASA GIBS GetCapabilities…</div>}
      {earth.gibs.status === "error" && (
        <div className="error-text">
          NASA GIBS unavailable: {earth.gibs.error}. The street map keeps working.{" "}
          <button className="btn btn--small" onClick={() => setEarth({ gibs: { status: "idle", data: null, error: null } })}>
            Retry
          </button>
        </div>
      )}
      {earth.gibs.data && (
        <p className="hint small">
          Layers verified against GIBS GetCapabilities fetched {earth.gibs.data.capabilities_fetched_at ?? "?"} (EPSG:3857, "best").
        </p>
      )}
      {groups.map((g) => (
        <div key={g}>
          <h4 className="subhead">{GROUP_LABEL[g]}</h4>
          {layers
            .filter((l) => l.group === g)
            .map((l) => {
              const isBase = g === "SATELLITE";
              const active = isBase ? earth.base === l.id : earth.overlays.includes(l.id);
              return (
                <div key={l.id} className={`layer-card ${active ? "layer-card--active" : ""}`}>
                  <label className="check">
                    <input
                      type={isBase ? "radio" : "checkbox"}
                      checked={active}
                      disabled={l.status !== "AVAILABLE"}
                      onChange={(e) =>
                        isBase
                          ? setEarth({ base: l.id })
                          : setEarth({ overlays: e.target.checked ? [...earth.overlays, l.id] : earth.overlays.filter((x) => x !== l.id) })
                      }
                    />
                    <span className="layer-card__name">{l.title}</span>
                  </label>
                  {l.status !== "AVAILABLE" && <div className="warn-text small">Not present in GetCapabilities — not shown.</div>}
                  {active && (
                    <>
                      <DateControl layer={l} />
                      <LayerMeta layer={l} />
                    </>
                  )}
                </div>
              );
            })}
        </div>
      ))}
      {groups.some((g) => g !== "SATELLITE") && (
        <div className="layer-card__row">
          <span className="label">Overlay opacity</span>
          <input type="range" min={0} max={1} step={0.05} value={earth.overlayOpacity} onChange={(e) => setEarth({ overlayOpacity: Number(e.target.value) })} />
          <span className="mono">{Math.round(earth.overlayOpacity * 100)}%</span>
        </div>
      )}
      {groups.includes("PRECIPITATION") && (
        <p className="hint small">
          IMERG precipitation is a gridded multi-satellite estimate, not a rain-gauge measurement at a specific spot.
        </p>
      )}
    </div>
  );
}
