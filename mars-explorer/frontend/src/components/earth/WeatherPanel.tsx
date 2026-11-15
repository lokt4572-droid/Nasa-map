import { useEffect, useState } from "react";

import { describeError } from "../../services/api";
import { type WeatherEnvelope, getCurrentWeather, getForecast, getHistorical } from "../../services/earthService";
import { useAppStore } from "../../store/useAppStore";
import LineChart from "../common/LineChart";

type Tab = "CURRENT" | "HOURLY" | "7 DAYS" | "HISTORICAL";
type R<T> = { status: "idle" | "loading" | "ready" | "error"; data: T | null; error: string | null };
const idle = { status: "idle" as const, data: null, error: null };

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
const compass = (deg: number | null | undefined) => (deg === null || deg === undefined ? "" : COMPASS[Math.round(deg / 45) % 8]);
const isoDay = (d: Date) => d.toISOString().slice(0, 10);

function Row({ label, value, unit }: { label: string; value: unknown; unit?: unknown }) {
  return (
    <div className="kv">
      <span className="label">{label}</span>
      <span className="mono">{value === null || value === undefined ? "—" : `${String(value)}${unit ? ` ${String(unit)}` : ""}`}</span>
    </div>
  );
}

function Source({ env }: { env: WeatherEnvelope<unknown> }) {
  return (
    <div className="hint small">
      {env.provider} · <strong>{env.data_type.replace("_", " ")}</strong>
      {env.valid_time ? ` · valid ${env.valid_time} (${env.timezone})` : ""} · retrieved {new Date(env.retrieved_at).toLocaleString()}
      {env.from_cache ? ` (cached ${Math.round(env.cache_age_s / 60)} min)` : ""}
      {env.model_grid_cell ? ` · model grid cell ${env.model_grid_cell.latitude.toFixed(3)}, ${env.model_grid_cell.longitude.toFixed(3)}` : ""}
      {env.missing_variables?.length ? <div className="warn-text">Missing in response: {env.missing_variables.join(", ")}</div> : null}
      <div>
        {env.provider === "Open-Meteo" ? (
          <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">
            Weather data by Open-Meteo.com (CC BY 4.0)
          </a>
        ) : (
          env.attribution
        )}
      </div>
    </div>
  );
}

export default function WeatherPanel() {
  const point = useAppStore((s) => s.selectedPoint);
  const [tab, setTab] = useState<Tab>("CURRENT");
  const [cur, setCur] = useState<R<Awaited<ReturnType<typeof getCurrentWeather>>>>(idle);
  const [fc, setFc] = useState<R<Awaited<ReturnType<typeof getForecast>>>>(idle);
  const [hist, setHist] = useState<R<Awaited<ReturnType<typeof getHistorical>>>>(idle);
  const today = new Date();
  const [range, setRange] = useState({ start: isoDay(new Date(today.getTime() - 37 * 864e5)), end: isoDay(new Date(today.getTime() - 7 * 864e5)) });

  const lat = point?.crs === "EPSG:4326" ? point.lat : null;
  const lon = point?.crs === "EPSG:4326" ? point.lon : null;

  // Requests only for the selected point and the active tab — never per map element.
  useEffect(() => {
    if (lat === null || lon === null) return;
    const ctrl = new AbortController();
    const run = async <T,>(set: (r: R<T>) => void, fn: () => Promise<T>) => {
      set({ status: "loading", data: null, error: null });
      try {
        set({ status: "ready", data: await fn(), error: null });
      } catch (err) {
        if (!ctrl.signal.aborted) set({ status: "error", data: null, error: describeError(err) });
      }
    };
    if (tab === "CURRENT") void run(setCur, () => getCurrentWeather(lat, lon, ctrl.signal));
    else if (tab === "HISTORICAL") void run(setHist, () => getHistorical(lat, lon, range.start, range.end, ctrl.signal));
    else void run(setFc, () => getForecast(lat, lon, ctrl.signal));
    return () => ctrl.abort();
  }, [lat, lon, tab, range.start, range.end]);

  if (lat === null || lon === null) return <div className="empty">Click a point on the Earth map (or search a place) to see its weather.</div>;

  const c = cur.data;
  const hourly = fc.data?.data.hourly;
  const daily = fc.data?.data.daily;
  const hu = (fc.data?.units as { hourly?: Record<string, string>; daily?: Record<string, string> } | undefined) ?? {};
  const num = (a: unknown[] | undefined) => (a ?? []).map((v) => (typeof v === "number" ? v : null));

  return (
    <div className="panel-section">
      <h4 className="subhead">WEATHER OVERVIEW</h4>
      <div className="mono small">
        {lat.toFixed(4)}, {lon.toFixed(4)} (WGS 84)
      </div>
      <div className="tabs" role="tablist">
        {(["CURRENT", "HOURLY", "7 DAYS", "HISTORICAL"] as Tab[]).map((t) => (
          <button key={t} role="tab" aria-selected={tab === t} className={`tab ${tab === t ? "tab--active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === "CURRENT" && (
        <>
          {cur.status === "loading" && <div className="hint">Loading…</div>}
          {cur.status === "error" && <div className="error-text">{cur.error}</div>}
          {c && (
            <>
              <Row label="Current temperature" value={c.data.temperature_2m} unit={c.units.temperature_2m} />
              <Row label="Feels like" value={c.data.apparent_temperature} unit={c.units.apparent_temperature} />
              <Row label="Humidity" value={c.data.relative_humidity_2m} unit={c.units.relative_humidity_2m} />
              <Row label="Pressure (MSL)" value={c.data.pressure_msl} unit={c.units.pressure_msl} />
              <Row label="Wind speed" value={c.data.wind_speed_10m} unit={c.units.wind_speed_10m} />
              <Row label="Wind direction" value={c.data.wind_direction_10m !== undefined ? `${c.data.wind_direction_10m}° ${compass(c.data.wind_direction_10m)}` : null} />
              <Row label="Wind gusts" value={c.data.wind_gusts_10m} unit={c.units.wind_gusts_10m} />
              <Row label="Cloud cover" value={c.data.cloud_cover} unit={c.units.cloud_cover} />
              <Row label="Precipitation" value={c.data.precipitation} unit={c.units.precipitation} />
              <Row label="Precip. probability (today max)" value={c.today?.precipitation_probability_max} unit="%" />
              <Row label="Sunrise" value={c.today?.sunrise?.slice(11)} unit={c.timezone ?? ""} />
              <Row label="Sunset" value={c.today?.sunset?.slice(11)} unit={c.timezone ?? ""} />
              <p className="hint small">{c.note}</p>
              <Source env={c} />
            </>
          )}
        </>
      )}

      {(tab === "HOURLY" || tab === "7 DAYS") && (
        <>
          {fc.status === "loading" && <div className="hint">Loading…</div>}
          {fc.status === "error" && <div className="error-text">{fc.error}</div>}
          {tab === "HOURLY" && hourly && (
            <>
              <LineChart
                x={hourly.time.map((t) => Date.parse(t))}
                series={[{ label: "Temperature", color: "#f2a33a", values: num(hourly.temperature_2m) }]}
                xLabel={`local time (${fc.data?.timezone})`}
                yLabel={`temperature, ${hu.hourly?.temperature_2m ?? ""}`}
                formatX={(v) => new Date(v).toISOString().slice(5, 13).replace("T", " ") + "h"}
              />
              <LineChart
                bars
                x={hourly.time.map((t) => Date.parse(t))}
                series={[{ label: "Precipitation", color: "#5fb3d9", values: num(hourly.precipitation) }]}
                xLabel="local time"
                yLabel={`precipitation, ${hu.hourly?.precipitation ?? ""}`}
                formatX={(v) => new Date(v).toISOString().slice(5, 10)}
              />
              <LineChart
                x={hourly.time.map((t) => Date.parse(t))}
                series={[
                  { label: "Wind", color: "#6fbf73", values: num(hourly.wind_speed_10m) },
                  { label: "Gusts", color: "#ef5a4c", values: num(hourly.wind_gusts_10m) },
                ]}
                xLabel="local time (green wind, red gusts)"
                yLabel={`wind, ${hu.hourly?.wind_speed_10m ?? ""}`}
                formatX={(v) => new Date(v).toISOString().slice(5, 10)}
              />
            </>
          )}
          {tab === "7 DAYS" && daily && (
            <>
              <table className="table">
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Min / max {hu.daily?.temperature_2m_max}</th>
                    <th>Precip {hu.daily?.precipitation_sum}</th>
                    <th>Prob %</th>
                  </tr>
                </thead>
                <tbody>
                  {daily.time.map((d, i) => (
                    <tr key={d}>
                      <td className="mono">{d}</td>
                      <td className="mono">
                        {String(daily.temperature_2m_min?.[i] ?? "—")} / {String(daily.temperature_2m_max?.[i] ?? "—")}
                      </td>
                      <td className="mono">{String(daily.precipitation_sum?.[i] ?? "—")}</td>
                      <td className="mono">{String(daily.precipitation_probability_max?.[i] ?? "—")}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <LineChart
                x={daily.time.map((t) => Date.parse(t))}
                series={[
                  { label: "max", color: "#ef5a4c", values: num(daily.temperature_2m_max) },
                  { label: "min", color: "#5fb3d9", values: num(daily.temperature_2m_min) },
                ]}
                xLabel="date (red max, blue min)"
                yLabel={`temperature, ${hu.daily?.temperature_2m_max ?? ""}`}
                formatX={(v) => new Date(v).toISOString().slice(5, 10)}
              />
            </>
          )}
          {fc.data && <Source env={fc.data} />}
        </>
      )}

      {tab === "HISTORICAL" && (
        <>
          <div className="form__row">
            <input type="date" value={range.start} min="1981-01-01" max={range.end} onChange={(e) => setRange({ ...range, start: e.target.value })} aria-label="Start date" />
            <input type="date" value={range.end} min={range.start} max={isoDay(today)} onChange={(e) => setRange({ ...range, end: e.target.value })} aria-label="End date" />
          </div>
          <p className="hint small">NASA POWER daily data (reanalysis / satellite-derived, coarse grid). Historical context — not a forecast, not station data.</p>
          {hist.status === "loading" && <div className="hint">Loading…</div>}
          {hist.status === "error" && <div className="error-text">{hist.error}</div>}
          {hist.data && (
            <>
              {(["T2M", "PRECTOTCORR", "WS10M", "RH2M"] as const).map((k) => (
                <LineChart
                  key={k}
                  bars={k === "PRECTOTCORR"}
                  x={hist.data!.data.dates.map((d) => Date.parse(d))}
                  series={[{ label: k, color: k === "PRECTOTCORR" ? "#5fb3d9" : "#f2a33a", values: hist.data!.data.series[k] ?? [] }]}
                  xLabel="date"
                  yLabel={`${hist.data!.long_names?.[k] ?? k}, ${String(hist.data!.units[k] ?? "")}`}
                  formatX={(v) => new Date(v).toISOString().slice(5, 10)}
                />
              ))}
              <div className="hint small">Sources reported: {hist.data.sources?.join(", ") ?? "—"}. Missing values (fill −999) are gaps, not zeros.</div>
              <Source env={hist.data} />
            </>
          )}
        </>
      )}
    </div>
  );
}
