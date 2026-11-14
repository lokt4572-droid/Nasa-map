/** Typed wrappers around backend endpoints. */
import { TREK_DECLARED_CRS } from "../config/marsProjection";
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
  source?: string;
  instrument?: string;
  product_id?: string;
  vertical_datum?: string;
  units?: string;
}) => apiRequest<{ dataset: Dataset; warnings: string[] }>("/datasets/register/", { method: "POST", body, timeoutMs: 600_000 });

// --- terrain (point given in the map's declared CRS; latitude type not asserted)
const pointQuery = (lon: number, lat: number) => ({ lon, lat, crs: TREK_DECLARED_CRS });
export const getCoverage = (lon: number, lat: number, signal?: AbortSignal) =>
  apiRequest<CoverageResponse>("/terrain/coverage/", { query: pointQuery(lon, lat), signal });
export const sampleElevation = (lon: number, lat: number, signal?: AbortSignal) =>
  apiRequest<SampleResponse>("/terrain/sample/", { query: pointQuery(lon, lat), signal });
export const getSlope = (lon: number, lat: number, signal?: AbortSignal) =>
  apiRequest<SlopeResponse>("/terrain/slope/", { query: pointQuery(lon, lat), signal });

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
