/** MARS EXPLORER - Type Definitions */

// Base coordinate type
export interface Coordinate {
  longitude: number;
  latitude: number;
}

export interface MarsCoordinate extends Coordinate {
  elevation?: number;
}

// Map layer types
export type LayerType = 'wmts' | 'xyz' | 'geojson' | 'vector' | 'image';

export interface BaseLayerConfig {
  id: string;
  name: string;
  type: LayerType;
  attribution?: string;
  opacity?: number;
  visible?: boolean;
  zIndex?: number;
  minZoom?: number;
  maxZoom?: number;
}

export interface WMTSLayerConfig extends BaseLayerConfig {
  type: 'wmts';
  url: string;
  layerId: string;
  matrixSet: string;
  style: string;
  format: string;
}

export interface XYZLayerConfig extends BaseLayerConfig {
  type: 'xyz';
  urlTemplate: string;
}

export interface GeoJSONLayerConfig extends BaseLayerConfig {
  type: 'geojson';
  url: string;
  style?: any;
}

export type LayerConfig = WMTSLayerConfig | XYZLayerConfig | GeoJSONLayerConfig;

// NASA Mars Trek layer metadata
export interface NasaLayerMeta {
  key: string;
  name: string;
  description: string;
  type: 'hillshade' | 'orthoimage' | 'dem' | 'vector';
  identifier: string;
  resolutionM: number;
  coverage: 'global' | 'regional' | { west: number; south: number; east: number; north: number };
  attribution: string;
  wmtsUrl: string;
  wmtsLayerId: string;
  wmtsStyle: string;
  wmtsFormat: string;
}

// Mission types
export interface Mission {
  id: string;
  name: string;
  description: string;
  status: 'planned' | 'active' | 'completed' | 'archived';
  missionType: 'exploration' | 'science' | 'survey' | 'emergency' | 'logistics';
  launchWindowStart?: string;
  launchWindowEnd?: string;
  landingSite?: Coordinate;
  baseCamp?: Coordinate;
  createdAt: string;
  updatedAt: string;
}

export interface Waypoint {
  id: string;
  missionId: string;
  name: string;
  coordinate: Coordinate;
  elevation?: number;
  order: number;
  type: 'landing' | 'base_camp' | 'science' | 'navigation' | 'emergency' | 'departure';
  description?: string;
  estimatedArrival?: string;
  estimatedDeparture?: string;
}

export interface ExpeditionLog {
  id: string;
  missionId: string;
  authorId: string;
  authorName: string;
  timestamp: string;
  type: 'status' | 'observation' | 'sample' | 'incident' | 'milestone';
  coordinate?: Coordinate;
  content: string;
  attachments?: string[];
}

// Hazard types
export type HazardType = 
  | 'dust_storm' 
  | 'steep_slope' 
  | 'rockfall' 
  | 'crater' 
  | 'radiation' 
  | 'temperature' 
  | 'communication' 
  | 'power' 
  | 'unknown';

export type HazardSeverity = 1 | 2 | 3 | 4 | 5;

export interface Hazard {
  id: string;
  name: string;
  type: HazardType;
  severity: HazardSeverity;
  geometry: GeoJSON.Polygon | GeoJSON.MultiPolygon;
  coordinate?: Coordinate;
  radiusKm?: number;
  description: string;
  detectedAt: string;
  expiresAt?: string;
  source: 'orbital' | 'rover' | 'station' | 'predicted' | 'manual';
  isActive: boolean;
  metadata?: Record<string, any>;
}

export interface HazardReport {
  id: string;
  hazardId: string;
  reporterId: string;
  reporterName: string;
  timestamp: string;
  coordinate: Coordinate;
  observations: string;
  severity?: HazardSeverity;
  photos?: string[];
  verified: boolean;
}

// Dataset types
export type DatasetType = 'dem' | 'orthoimage' | 'thermal' | 'spectral' | 'gravity' | 'magnetic' | 'composition' | 'atmospheric' | 'other';

export type DatasetSource = 'nasa_trek' | 'pds' | 'esa' | 'custom' | 'derived';

export interface Dataset {
  id: string;
  name: string;
  identifier: string;
  source: DatasetSource;
  datasetType: DatasetType;
  description: string;
  resolutionMeters?: number;
  crs: string;
  coverage?: GeoJSON.Polygon;
  bounds?: [number, number, number, number]; // west, south, east, north
  attribution: string;
  filePath?: string;
  fileSize?: number;
  bands?: number;
  bitDepth?: number;
  nodataValue?: number;
  minValue?: number;
  maxValue?: number;
  metadata?: Record<string, any>;
  isPublic: boolean;
  isProcessed: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface DatasetLayer {
  id: string;
  datasetId: string;
  name: string;
  layerType: LayerType;
  wmtsLayerId?: string;
  wmtsMatrixSet?: string;
  wmtsStyle?: string;
  wmtsFormat?: string;
  urlTemplate?: string;
  attribution?: string;
  opacity: number;
  isBaseLayer: boolean;
  isVisible: boolean;
  zIndex: number;
  minZoom: number;
  maxZoom: number;
  colorRamp?: Record<string, any>;
}

// Terrain analysis
export type AnalysisType = 'slope' | 'aspect' | 'hillshade' | 'roughness' | 'curvature' | 'profile' | 'visibility';

export interface TerrainAnalysis {
  id: string;
  name: string;
  analysisType: AnalysisType;
  region?: GeoJSON.Polygon;
  coordinate?: Coordinate;
  radiusKm?: number;
  demSource?: string;
  parameters: Record<string, any>;
  resultPath?: string;
  statistics: Record<string, number>;
  status: 'pending' | 'running' | 'completed' | 'failed';
  createdAt: string;
  completedAt?: string;
}

export interface ElevationProfile {
  coordinates: Coordinate[];
  elevations: (number | null)[];
  distancesKm: number[];
  minElevation?: number;
  maxElevation?: number;
  totalGain: number;
  totalLoss: number;
  maxSlope?: number;
}

// Route planning
export type RouteType = 'driving' | 'walking' | 'flight' | 'emergency';
export type RouteStatus = 'draft' | 'planned' | 'approved' | 'active' | 'completed' | 'aborted';

export interface Route {
  id: string;
  name: string;
  routeType: RouteType;
  status: RouteStatus;
  path: GeoJSON.LineString;
  waypoints: Coordinate[];
  missionId?: string;
  totalDistanceKm?: number;
  estimatedDurationHours?: number;
  maxSlope?: number;
  elevationGain?: number;
  elevationLoss?: number;
  minElevation?: number;
  maxElevation?: number;
  avoidsHazards: boolean;
  hazardBufferMeters: number;
  energyEstimateKwh?: number;
  notes?: string;
  createdAt: string;
  updatedAt: string;
  approvedAt?: string;
}

export interface RouteSegment {
  id: string;
  routeId: string;
  order: number;
  startPoint: Coordinate;
  endPoint: Coordinate;
  distanceKm: number;
  slope: number;
  elevationStart: number;
  elevationEnd: number;
  estimatedTimeHours: number;
  terrainType?: string;
  hazardCrossings?: any[];
}

// Map state
export interface MapState {
  center: Coordinate;
  zoom: number;
  rotation: number;
  projection: string;
  baseLayerId: string;
  overlayLayerIds: string[];
  selectedFeature?: any;
  measureMode: boolean;
  measurePoints: Coordinate[];
}

// UI state
export interface UIState {
  sidebarOpen: boolean;
  rightPanelOpen: boolean;
  activeTab: 'missions' | 'hazards' | 'datasets' | 'terrain' | 'routes';
  theme: 'light' | 'dark';
  loading: boolean;
  error?: string;
}

// API response types
export interface ApiResponse<T> {
  data: T;
  meta?: {
    page?: number;
    pageSize?: number;
    totalCount?: number;
    totalPages?: number;
  };
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// WebSocket message types
export type WSMessageType = 
  | 'mission_update' 
  | 'hazard_alert' 
  | 'route_update' 
  | 'terrain_result' 
  | 'system_status';

export interface WSMessage<T = any> {
  type: WSMessageType;
  payload: T;
  timestamp: string;
}
