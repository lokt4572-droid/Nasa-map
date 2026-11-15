/**
 * Elevation-model discovery (v0.4): asks the backend which DTM products exist in an area.
 * The backend queries the provider catalogue (USGS Astrogeology STAC); footprints and metadata
 * are the provider's. Nothing here reads elevation values.
 */
import type { PlanetId } from "../config/planetRegistry";
import { apiRequest } from "./api";

export interface DemProduct {
  planet_id: string;
  dataset_id: string; // provider collection
  product_id: string;
  provider: string;
  instrument: string;
  data_type: string;
  level: "GLOBAL" | "REGIONAL" | "LOCAL_HIGH_RESOLUTION";
  format: string;
  resolution_m: number | null;
  effective_accuracy: string;
  footprint: { type: "Polygon"; coordinates: number[][][] } | { type: "MultiPolygon"; coordinates: number[][][][] } | null;
  bbox: [number, number, number, number] | null;
  crs: string;
  vertical_datum: string;
  units: string;
  license: string;
  attribution: string;
  time_range: { start?: string | null; end?: string | null; datetime?: string | null };
  title: string;
  quality_status: string;
  quality: { valid_percent?: number | null; qa_metrics_url?: string | null; note?: string };
  dem_available: boolean;
  imagery_available: boolean;
  product_kind?: string;
  source_imagery?: string;
  coverage?: string;
  source_url: string | null;
  docs_url?: string;
  registered_dataset_id?: number | null;
  status: string;
}

export interface DemSearchResult {
  planet: string;
  count: number;
  matched_by_provider: number;
  truncated: boolean;
  provider: { name: string; status: string };
  products: DemProduct[];
  note: string;
}

type Request = typeof apiRequest;

/** DTM products intersecting a lon/lat box (west, south, east, north; any longitude range). */
export function searchDemProducts(planet: PlanetId, bbox: [number, number, number, number], opts: { limit?: number; signal?: AbortSignal; request?: Request } = {}): Promise<DemSearchResult> {
  const [w, s, e, n] = bbox;
  const box = [w, Math.max(-90, s), e - w >= 360 ? w + 360 : e, Math.min(90, n)];
  return (opts.request ?? apiRequest)<DemSearchResult>("/datasets/search/", {
    query: { planet, data_type: "DEM", bbox: box.map((v) => v.toFixed(5)).join(","), limit: opts.limit ?? 25 },
    signal: opts.signal,
    timeoutMs: 75_000, // the provider catalogue can take 2-40 s per page
  });
}

/** Outer rings of a footprint as [lon, lat][] lists (GeoJSON order). */
export function footprintRings(fp: DemProduct["footprint"]): number[][][] {
  if (!fp) return [];
  return fp.type === "Polygon" ? [fp.coordinates[0]!] : fp.coordinates.map((poly) => poly[0]!);
}

/** Centre of the product's bbox (a point that is normally inside the footprint). */
export function productCenter(p: DemProduct): { lon: number; lat: number } | null {
  if (!p.bbox) return null;
  return { lon: (p.bbox[0] + p.bbox[2]) / 2, lat: (p.bbox[1] + p.bbox[3]) / 2 };
}

export function productKey(p: DemProduct): string {
  return `${p.dataset_id}/${p.product_id}`;
}

export function formatResolution(m: number | null): string {
  if (m === null) return "resolution not stated";
  return m >= 1000 ? `${(m / 1000).toFixed(1)} km` : m >= 10 ? `${Math.round(m)} m` : `${m.toFixed(2)} m`;
}

export interface PointCoverage {
  planet: string;
  coverage_status: "AVAILABLE" | "NO_DATA_COVERAGE" | "PROVIDER_ERROR";
  best: DemProduct | null;
  datasets: DemProduct[];
  provider: { name: string; status: string; error?: string };
}

/** Elevation data at a point: registered DEMs plus the provider catalogue (no values are read). */
export const getPointCoverage = (planet: PlanetId, lon: number, lat: number, signal?: AbortSignal, request: Request = apiRequest) =>
  request<PointCoverage>("/datasets/coverage/", { query: { planet, longitude: lon.toFixed(6), latitude: lat.toFixed(6) }, signal, timeoutMs: 60_000 });

export interface DerivedHazards {
  status: string;
  hazards: { category: string; lon_east_deg: number; lat_deg: number; radius_m: number; max_value: number | null; unit: string; cells: number }[];
  dataset?: { name: string; resolution_m: number | null; instrument: string };
  grid_cell_m?: number;
  region_totals?: Record<string, number>;
  not_derivable_from_dem?: Record<string, string>;
  note?: string;
  message?: string;
}

/** DEM-derived slope / roughness / no-data areas around a point (model estimates, not stored). */
export const analyseTerrain = (
  planet: PlanetId,
  center: { lon: number; lat: number; crs: string },
  radiusM: number,
  signal?: AbortSignal,
  request: Request = apiRequest,
) =>
  request<DerivedHazards>("/routes/hazards/derive/", {
    method: "POST",
    body: {
      center: { lon_east_deg: center.lon, lat_deg: center.lat, crs: center.crs, latitude_convention: "AS_DECLARED_BY_SOURCE", planet },
      radius_m: radiusM,
      slope_limit_deg: 15,
      terrain_source: "auto",
    },
    signal,
    timeoutMs: 120_000,
  });
