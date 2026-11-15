/** Typed wrappers around backend endpoints. */
import { TREK_DECLARED_CRS } from "../config/marsProjection";
import { PLANETS, type PlanetId } from "../config/planetRegistry";
import type {
  CoverageResponse,
  Dataset,
  Hazard,
  HazardInput,
  HealthResponse,
  Mission,
  Paginated,
  SampleResponse,
  SlopeResponse,
  Waypoint,
} from "../types/api";
import { apiRequest } from "./api";

export const getHealth = () => apiRequest<HealthResponse>("/health/", { timeoutMs: 5_000 });

// --- datasets
export const listDatasets = () => apiRequest<Paginated<Dataset>>("/datasets/");
export const registerDataset = (body: {
  file_path: string;
  name: string;
  planet?: string;
  source?: string;
  instrument?: string;
  product_id?: string;
  vertical_datum?: string;
  units?: string;
}) => apiRequest<{ dataset: Dataset; warnings: string[]; steps: ImportStep[] }>("/datasets/register/", { method: "POST", body, timeoutMs: 600_000 });

// --- terrain (point given in the map's declared CRS; latitude type not asserted)
// Points are sent in the CRS of the body's map (as declared by its map service).
const pointQuery = (lon: number, lat: number, planet: PlanetId) => ({
  lon,
  lat,
  planet,
  // Earth points are geographic WGS84 degrees, not the Web Mercator map CRS.
  crs: planet === "EARTH" ? "EPSG:4326" : (PLANETS[planet].mapCrs ?? TREK_DECLARED_CRS),
});
export const getCoverage = (lon: number, lat: number, signal?: AbortSignal, planet: PlanetId = "MARS") =>
  apiRequest<CoverageResponse>("/terrain/coverage/", { query: pointQuery(lon, lat, planet), signal });
export const sampleElevation = (lon: number, lat: number, signal?: AbortSignal, planet: PlanetId = "MARS") =>
  apiRequest<SampleResponse>("/terrain/sample/", { query: pointQuery(lon, lat, planet), signal });
export const getSlope = (lon: number, lat: number, signal?: AbortSignal, planet: PlanetId = "MARS") =>
  apiRequest<SlopeResponse>("/terrain/slope/", { query: pointQuery(lon, lat, planet), signal });

// --- missions
export const listMissions = () => apiRequest<Paginated<Mission>>("/missions/");
export const createMission = (body: { name: string; description?: string }) =>
  apiRequest<Mission>("/missions/", { method: "POST", body });
export const updateMission = (id: number, body: Partial<Pick<Mission, "name" | "description" | "status">>) =>
  apiRequest<Mission>(`/missions/${id}/`, { method: "PATCH", body });
export const deleteMission = (id: number) => apiRequest<void>(`/missions/${id}/`, { method: "DELETE" });
export const createWaypoint = (body: Omit<Waypoint, "id" | "created_at" | "order" | "notes"> & { notes?: string }) =>
  apiRequest<Waypoint>("/waypoints/", { method: "POST", body });
export const deleteWaypoint = (id: number) => apiRequest<void>(`/waypoints/${id}/`, { method: "DELETE" });

// --- hazards
export const listHazards = () => apiRequest<Paginated<Hazard>>("/hazards/", { query: { limit: 500 } });
export const createHazard = (body: HazardInput) => apiRequest<Hazard>("/hazards/", { method: "POST", body });
export const updateHazard = (id: number, body: Partial<HazardInput>) =>
  apiRequest<Hazard>(`/hazards/${id}/`, { method: "PATCH", body });
export const deleteHazard = (id: number) => apiRequest<void>(`/hazards/${id}/`, { method: "DELETE" });

// --- routing (v0.2)
import type { RoutePlanResponse, RoutePoint, RouteProfile, RouteProfileId, UnknownDataPolicy } from "../types/api";
export const getRouteProfiles = () => apiRequest<RouteProfile[]>("/routes/profiles/");
export const planRoute = (body: {
  start: RoutePoint;
  end: RoutePoint;
  waypoints?: RoutePoint[];
  profile: RouteProfileId;
  include_return?: boolean;
  include_alternative?: boolean;
  unknown_data_policy?: UnknownDataPolicy;
  mission?: number;
  // v0.4 mission configuration (can only make the plan more restrictive)
  max_slope_deg?: number;
  required_resolution_m?: number;
  max_roughness_m?: number;
  hazard_buffer_m?: number;
  connectivity?: 4 | 8;
  prefer_lower_roughness?: boolean;
  terrain_source?: "local" | "auto";
}) => apiRequest<RoutePlanResponse>("/routes/plan/", { method: "POST", body, timeoutMs: 180_000 });
export const deleteRoute = (id: number) => apiRequest<void>(`/routes/${id}/`, { method: "DELETE" });

// --- terrain visualization (v0.2): PNG for a map bbox, metadata from response headers
import { API_BASE_URL, ApiError } from "./api";
export interface TerrainRender {
  url: string; // object URL — caller must revoke
  min: number | null;
  max: number | null;
  units: string;
  validFraction: number | null;
  dataset: string;
}
export async function fetchTerrainRender(
  params: { dataset: number; product: string; bbox: [number, number, number, number]; width: number; height: number; crs?: string; range?: [number, number] },
  signal?: AbortSignal,
): Promise<TerrainRender> {
  const q = new URLSearchParams({
    dataset: String(params.dataset),
    product: params.product,
    bbox: params.bbox.map((v) => v.toFixed(6)).join(","),
    width: String(params.width),
    height: String(params.height),
    crs: params.crs ?? TREK_DECLARED_CRS,
    ...(params.range ? { range: params.range.map((v) => v.toFixed(3)).join(",") } : {}),
  });
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/terrain/render/?${q}`, { signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_ERROR", "Backend unreachable for terrain render");
  }
  if (!res.ok) {
    let msg = `Terrain render failed (HTTP ${res.status})`;
    let code = `HTTP_${res.status}`;
    try {
      const body = (await res.json()) as { error?: { code: string; message: string } };
      if (body.error) ({ code, message: msg } = body.error);
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, msg);
  }
  const num = (h: string) => {
    const v = res.headers.get(h);
    return v === null || v === "" ? null : Number(v);
  };
  return {
    url: URL.createObjectURL(await res.blob()),
    min: num("X-Value-Min"),
    max: num("X-Value-Max"),
    units: res.headers.get("X-Value-Units") ?? "",
    validFraction: num("X-Valid-Fraction"),
    dataset: res.headers.get("X-Dataset") ?? "",
  };
}

// --- unified catalog (v0.2)
export interface CatalogEntry {
  key: string;
  planet: string;
  dataset: string;
  source: string;
  instrument: string;
  product_id: string;
  data_type: string;
  resolution: string;
  spatial_coverage: string;
  temporal_coverage: string;
  crs: string;
  units: string;
  vertical_datum: string;
  license: string;
  access: "ONLINE" | "DOWNLOAD";
  url: string;
  purpose: string;
  facts: string;
  status: string;
  local_datasets: { id: number; name: string; status: string }[];
}
export const getCatalog = (planet?: string, type?: string) =>
  apiRequest<{ types: string[]; results: CatalogEntry[] }>("/datasets/catalog/", { query: { planet, type } });
export type ImportStep = { step: string; status: string; detail: string };
