/** Earth-mode API calls (all external providers are reached through the Django backend). */
import { apiRequest } from "./api";

export interface GibsInterval {
  start: string;
  end: string;
  period: string;
}

export interface GibsLayer {
  id: string;
  group: "SATELLITE" | "ATMOSPHERE" | "PRECIPITATION" | "REFERENCE" | "GEOSTATIONARY";
  /** Regional coverage statement for layers that are not global (e.g. geostationary discs). */
  coverage?: string;
  title: string;
  instrument: string;
  platform: string;
  status: "AVAILABLE" | "NOT_IN_CAPABILITIES";
  crs: string;
  source: string;
  attribution: string;
  tile_matrix_set?: string;
  max_zoom?: number | null;
  pixel_size_at_equator_m?: number | null;
  format?: string;
  template?: string;
  time?: { default: string | null; intervals: GibsInterval[]; first: string | null; latest: string | null; daily: boolean } | null;
  temporal?: string | null;
}

export interface GibsDiscovery {
  capabilities_url: string;
  capabilities_fetched_at: string | null;
  layers: GibsLayer[];
  note: string;
}

export const getGibsLayers = (refresh = false) =>
  apiRequest<GibsDiscovery>("/earth/gibs/layers/", { query: refresh ? { refresh: 1 } : {}, timeoutMs: 90_000 });

export interface PlaceResult {
  name: string;
  lat: number;
  lon: number;
  category: string | null;
  type: string | null;
  bbox: { south: number; north: number; west: number; east: number } | null;
}

export const searchPlaces = (q: string, signal?: AbortSignal) =>
  apiRequest<{ query: string; provider: string; attribution: string; results: PlaceResult[]; from_cache: boolean }>(
    "/geocoding/search/",
    { query: { q }, signal, timeoutMs: 15_000 },
  );

export interface WeatherEnvelope<D> {
  provider: string;
  data_type: string;
  coordinates: { latitude: number; longitude: number };
  valid_time: string | null;
  retrieved_at: string;
  cache_age_s: number;
  from_cache: boolean;
  timezone: string | null;
  units: Record<string, unknown>;
  data: D;
  attribution: string;
  missing_variables?: string[];
  model_grid_cell?: { latitude: number; longitude: number; elevation_m: number | null };
  today?: { sunrise: string | null; sunset: string | null; precipitation_probability_max: number | null };
  note?: string;
  sources?: string[];
  long_names?: Record<string, string>;
}

type Series = Record<string, (number | string | null)[]>;

export const getCurrentWeather = (lat: number, lon: number, signal?: AbortSignal) =>
  apiRequest<WeatherEnvelope<Record<string, number | null>>>("/weather/current/", { query: { lat, lon }, signal });
export const getForecast = (lat: number, lon: number, signal?: AbortSignal) =>
  apiRequest<WeatherEnvelope<{ hourly: Series & { time: string[] }; daily: Series & { time: string[] } }>>("/weather/forecast/", {
    query: { lat, lon },
    signal,
  });
export const getHistorical = (lat: number, lon: number, start: string, end: string, signal?: AbortSignal) =>
  apiRequest<WeatherEnvelope<{ dates: string[]; series: Record<string, (number | null)[]> }>>("/weather/historical/", {
    query: { lat, lon, start, end },
    signal,
    timeoutMs: 60_000,
  });

/** Is a YYYY-MM-DD date inside one of the published daily intervals? */
export function dateAvailable(time: GibsLayer["time"], date: string): boolean {
  if (!time) return true;
  if (!time.daily && date.length > 10) {
    const t = Date.parse(date); // a sub-daily timestamp must be one of the published steps
    return time.intervals.some((i) => {
      const step = subDailyStepMs(i.period);
      const a = Date.parse(i.start);
      return step !== null && t >= a && t <= Date.parse(i.end) && (t - a) % step === 0;
    });
  }
  const d = date.slice(0, 10);
  return time.intervals.some((i) => i.start.slice(0, 10) <= d && d <= i.end.slice(0, 10));
}

/** Next/previous available day, skipping gaps between published intervals. */
export function stepDate(time: GibsLayer["time"], date: string, dir: 1 | -1): string | null {
  if (!time) return null;
  const d = new Date(`${date}T00:00:00Z`);
  for (let k = 0; k < 4000; k++) {
    d.setUTCDate(d.getUTCDate() + dir);
    const s = d.toISOString().slice(0, 10);
    if (time.first && s < time.first.slice(0, 10)) return null;
    if (time.latest && s > time.latest.slice(0, 10)) return null;
    if (dateAvailable(time, s)) return s;
  }
  return null;
}

/** ISO-8601 duration with time part only (e.g. PT10M, PT1H) -> milliseconds; null if not sub-daily. */
export function subDailyStepMs(period: string): number | null {
  const m = /^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$/.exec(period);
  if (!m || (!m[1] && !m[2] && !m[3])) return null;
  return ((Number(m[1] ?? 0) * 60 + Number(m[2] ?? 0)) * 60 + Number(m[3] ?? 0)) * 1000;
}

const isoZ = (ms: number) => new Date(ms).toISOString().replace(/\.\d{3}Z$/, "Z");

/** Published sub-daily times (newest first), at most `limit`. Only times inside published intervals. */
export function subDailyTimes(time: GibsLayer["time"], limit = 144): string[] {
  if (!time) return [];
  const out: string[] = [];
  for (const iv of [...time.intervals].reverse()) {
    const step = subDailyStepMs(iv.period);
    const start = Date.parse(iv.start);
    const end = Date.parse(iv.end);
    if (!step || !Number.isFinite(start) || !Number.isFinite(end)) continue;
    for (let t = end; t >= start && out.length < limit; t -= step) out.push(isoZ(t));
    if (out.length >= limit) break;
  }
  return out;
}

/** Value for the {Time} placeholder: a published timestamp for sub-daily layers, a day otherwise. */
export function timeValue(layer: GibsLayer, selected: string | undefined): string | null {
  const t = layer.time;
  if (!t) return null;
  if (!t.daily) {
    const times = subDailyTimes(t, 100_000);
    if (selected && times.includes(selected)) return selected;
    return times[0] ?? null; // latest published step
  }
  return (selected ?? t.latest)?.slice(0, 10) ?? null;
}

/** Build the XYZ template for OpenLayers from the published WMTS REST template. */
export function gibsXyzTemplate(layer: GibsLayer, date: string | null): string {
  if (!layer.template || !layer.tile_matrix_set) throw new Error(`${layer.id} has no ResourceURL template`);
  let t = layer.template.replace("{TileMatrixSet}", layer.tile_matrix_set).replace("{TileMatrix}", "{z}").replace("{TileRow}", "{y}").replace("{TileCol}", "{x}");
  if (t.includes("{Time}")) {
    if (!date) throw new Error(`${layer.id} needs a date`);
    t = t.replace("{Time}", date);
  }
  return t;
}
