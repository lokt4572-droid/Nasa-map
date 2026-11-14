/** MARS EXPLORER - API Service */
import type {
  Mission,
  Waypoint,
  ExpeditionLog,
  Hazard,
  HazardReport,
  Dataset,
  DatasetLayer,
  TerrainAnalysis,
  ElevationProfile,
  Route,
  RouteSegment,
  PaginatedResponse,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const response = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

// Missions API
export const missionsApi = {
  list: (params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params).toString()}` : '';
    return request<PaginatedResponse<Mission>>(`/missions/missions/${query}`);
  },
  get: (id: string) => request<Mission>(`/missions/missions/${id}/`),
  create: (data: Partial<Mission>) => request<Mission>('/missions/missions/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Partial<Mission>) => request<Mission>(`/missions/missions/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/missions/missions/${id}/`, { method: 'DELETE' }),
  
  waypoints: {
    list: (missionId: string) => request<Waypoint[]>(`/missions/missions/${missionId}/waypoints/`),
    create: (missionId: string, data: Partial<Waypoint>) => request<Waypoint>(`/missions/missions/${missionId}/waypoints/`, { method: 'POST', body: JSON.stringify(data) }),
    update: (id: string, data: Partial<Waypoint>) => request<Waypoint>(`/missions/waypoints/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: string) => request<void>(`/missions/waypoints/${id}/`, { method: 'DELETE' }),
    reorder: (missionId: string, waypointIds: string[]) => request<void>(`/missions/missions/${missionId}/waypoints/reorder/`, { method: 'POST', body: JSON.stringify({ waypoint_ids: waypointIds }) }),
  },
  
  logs: {
    list: (missionId: string) => request<ExpeditionLog[]>(`/missions/missions/${missionId}/logs/`),
    create: (missionId: string, data: Partial<ExpeditionLog>) => request<ExpeditionLog>(`/missions/missions/${missionId}/logs/`, { method: 'POST', body: JSON.stringify(data) }),
  },
  
  routes: {
    list: (missionId: string) => request<Route[]>(`/missions/missions/${missionId}/routes/`),
  },
};

// Hazards API
export const hazardsApi = {
  list: (params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params).toString()}` : '';
    return request<PaginatedResponse<Hazard>>(`/hazards/hazards/${query}`);
  },
  get: (id: string) => request<Hazard>(`/hazards/hazards/${id}/`),
  create: (data: Partial<Hazard>) => request<Hazard>('/hazards/hazards/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Partial<Hazard>) => request<Hazard>(`/hazards/hazards/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/hazards/hazards/${id}/`, { method: 'DELETE' }),
  nearby: (lon: number, lat: number, radiusKm: number) => request<Hazard[]>(`/hazards/hazards/nearby/?lon=${lon}&lat=${lat}&radius=${radiusKm}`),
  
  reports: {
    list: (hazardId: string) => request<HazardReport[]>(`/hazards/hazards/${hazardId}/reports/`),
    create: (hazardId: string, data: Partial<HazardReport>) => request<HazardReport>(`/hazards/hazards/${hazardId}/reports/`, { method: 'POST', body: JSON.stringify(data) }),
  },
};

// Datasets API
export const datasetsApi = {
  list: (params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params).toString()}` : '';
    return request<PaginatedResponse<Dataset>>(`/datasets/datasets/${query}`);
  },
  get: (id: string) => request<Dataset>(`/datasets/datasets/${id}/`),
  layers: {
    list: (params?: Record<string, string>) => {
      const query = params ? `?${new URLSearchParams(params).toString()}` : '';
      return request<PaginatedResponse<DatasetLayer>>(`/datasets/layers/${query}`);
    },
    get: (id: string) => request<DatasetLayer>(`/datasets/layers/${id}/`),
  },
};

// Terrain API
export const terrainApi = {
  list: (params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params).toString()}` : '';
    return request<PaginatedResponse<TerrainAnalysis>>(`/terrain/analyses/${query}`);
  },
  get: (id: string) => request<TerrainAnalysis>(`/terrain/analyses/${id}/`),
  create: (data: Partial<TerrainAnalysis>) => request<TerrainAnalysis>('/terrain/analyses/', { method: 'POST', body: JSON.stringify(data) }),
  profile: (data: { coordinates: Array<{ longitude: number; latitude: number }>; dem_source?: string }) => request<ElevationProfile>('/terrain/profile/', { method: 'POST', body: JSON.stringify(data) }),
};

// Routing API
export const routingApi = {
  list: (params?: Record<string, string>) => {
    const query = params ? `?${new URLSearchParams(params).toString()}` : '';
    return request<PaginatedResponse<Route>>(`/routing/routes/${query}`);
  },
  get: (id: string) => request<Route>(`/routing/routes/${id}/`),
  create: (data: Partial<Route>) => request<Route>('/routing/routes/', { method: 'POST', body: JSON.stringify(data) }),
  update: (id: string, data: Partial<Route>) => request<Route>(`/routing/routes/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  delete: (id: string) => request<void>(`/routing/routes/${id}/`, { method: 'DELETE' }),
  calculate: (id: string) => request<{ total_distance_km: number; estimated_duration_hours: number; segment_count: number }>(`/routing/routes/${id}/calculate/`, { method: 'POST' }),
  approve: (id: string) => request<{ status: string }>(`/routing/routes/${id}/approve/`, { method: 'POST' }),
  
  segments: {
    list: (routeId: string) => request<RouteSegment[]>(`/routing/routes/${routeId}/segments/`),
  },
};

// Generic export
export const api = {
  missions: missionsApi,
  hazards: hazardsApi,
  datasets: datasetsApi,
  terrain: terrainApi,
  routing: routingApi,
};
