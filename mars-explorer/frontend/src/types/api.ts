/** Typed backend responses (mirror of backend serializers; see docs/API_ENDPOINTS.md). */

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface RasterBackendStatus {
  available: boolean;
  backend: string | null;
  gdal_version: string | null;
  planetary_drivers?: string[];
  error: string | null;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  service: string;
  version: string;
  time_utc: string;
  database: "ok" | "error";
  data_dir: { path: string; exists: boolean };
  raster_backend: RasterBackendStatus;
}

export type DatasetStatus = "AVAILABLE" | "DOWNLOADING" | "PROCESSING" | "VALID" | "INVALID" | "MISSING";

export interface Dataset {
  id: number;
  name: string;
  planet?: string;
  license?: string;
  download_url?: string;
  source: string;
  instrument: string;
  product_id: string;
  data_type: string;
  file_path: string;
  file_exists: boolean;
  driver: string;
  width: number | null;
  height: number | null;
  resolution_meters: number | null;
  pixel_size_x: number | null;
  pixel_size_y: number | null;
  crs_name: string;
  longitude_convention: string;
  latitude_convention: string;
  vertical_datum: string;
  units: string;
  nodata_value: number | null;
  coverage_bbox: { crs_units: string | null; left: number; bottom: number; right: number; top: number } | null;
  observation_date: string | null;
  download_date: string | null;
  file_size: number | null;
  checksum: string;
  is_validated: boolean;
  status: DatasetStatus;
  validation_messages: { level: string; message: string }[];
  created_at: string;
  updated_at: string;
}

export interface DatasetSummary {
  id: number;
  name: string;
  instrument: string;
  source: string;
  product_id: string;
  resolution_meters: number | null;
  crs_name: string;
  latitude_convention: string;
  vertical_datum: string;
  units: string;
}

export interface PointQuery {
  lon_east_deg: number;
  lat_deg: number;
  crs: string;
  latitude_convention: string;
  crs_resolution: { resolved_as: string; note: string | null };
}

export interface LatitudeHandling {
  status: string;
  dataset_latitude_convention: string;
  lat_query_deg: number;
  lat_used_deg: number;
  warning: string | null;
}

export type TerrainAnalysisStatus = "AVAILABLE" | "NO DATA" | "PROCESSING" | "ERROR";

export interface CoverageResponse {
  query: PointQuery;
  terrain_analysis_status: TerrainAnalysisStatus;
  raster_backend: RasterBackendStatus;
  datasets: DatasetSummary[];
}

export interface SampleResponse {
  status: "AVAILABLE" | "NODATA";
  query: PointQuery;
  elevation_m: number | null;
  elevation_display: string | null;
  units: string;
  vertical_datum: string;
  method: string;
  pixel: { row: number; col: number; x_dataset: number; y_dataset: number };
  latitude_handling: LatitudeHandling;
  dataset: DatasetSummary;
}

export interface SlopeResponse {
  status: "AVAILABLE" | "NODATA";
  query: PointQuery;
  slope_deg: number | null;
  aspect_deg: number | null;
  terrain_ruggedness_index_m: number | null;
  elevation_std_m: number | null;
  nodata_fraction: number;
  window: string;
  latitude_handling: LatitudeHandling;
  cell_size_m: { dx: number; dy: number; method: string };
  method: string;
  disclaimer: string;
  dataset: DatasetSummary;
}

export interface MarsPointFields {
  lon_east_deg: number;
  lat_deg: number;
  crs: string;
  latitude_convention: string;
}

export type WaypointKind = "BASE" | "CHECKPOINT" | "LANDING_SITE" | "POI";

export interface Waypoint extends MarsPointFields {
  id: number;
  mission: number;
  name: string;
  kind: WaypointKind;
  order: number;
  notes: string;
  created_at: string;
}

export type MissionStatus = "PLANNED" | "ACTIVE" | "COMPLETED" | "ABORTED";

export interface Mission {
  id: number;
  name: string;
  description: string;
  status: MissionStatus;
  demo_mode: boolean;
  waypoints: Waypoint[];
  hazard_count: number;
  client_id?: string | null;
  version?: number;
  created_at: string;
  updated_at: string;
}

export type HazardType =
  | "CRATER"
  | "STEEP_SLOPE"
  | "CLIFF"
  | "BOULDER_FIELD"
  | "SOFT_REGOLITH"
  | "DUNE"
  | "DUST"
  | "OTHER";
export type HazardSeverity = "UNKNOWN" | "LOW" | "MEDIUM" | "HIGH";
export type HazardSource = "FIELD_OBSERVATION" | "IMAGERY_INTERPRETATION" | "DEM_DERIVED" | "OTHER";
export type HazardVerification = "UNVERIFIED" | "CONFIRMED" | "REJECTED";

export interface Hazard extends MarsPointFields {
  id: number;
  mission: number | null;
  title: string;
  hazard_type: HazardType;
  severity: HazardSeverity;
  source: HazardSource;
  verification: HazardVerification;
  radius_m: number | null;
  description: string;
  reference_layer: string;
  reported_by: string;
  observed_at: string | null;
  client_id?: string | null;
  version?: number;
  created_at: string;
  updated_at: string;
}

export type HazardInput = Omit<Hazard, "id" | "created_at" | "updated_at" | "verification" | "observed_at"> & {
  verification?: HazardVerification;
};

// ---------------------------------------------------------------- v0.2 routing
export type RouteProfileId = "CONSERVATIVE" | "STANDARD";

export interface RouteProfile {
  id: RouteProfileId;
  description: string;
  max_slope_deg: number;
  slope_weight: number;
  roughness_weight: number;
  roughness_ref_m: number;
  allow_unknown_terrain: boolean;
  unknown_multiplier: number | null;
  hazard_buffer_m: number;
  max_unknown_fraction: number;
  hazard_proximity_weight?: number;
  unknown_data_policy?: UnknownDataPolicy;
  disclaimer: string;
}

export type UnknownDataPolicy = "REJECT" | "ALLOW_MARKED";
export type RouteClassification = "KNOWN_TERRAIN_ROUTE" | "PARTIALLY_UNVERIFIED_ROUTE" | "NO_VALID_ROUTE";

export interface RouteMetrics {
  distance_m: number;
  distance_3d_m: number;
  elevation_gain_m: number;
  elevation_loss_m: number;
  max_step_grade_deg: number;
  max_cell_slope_deg: number;
  known_terrain_pct: number;
  nodata_pct_along_route: number;
  cost: number;
  terrain_cost: number;
  dem_source?: string;
  dem_name?: string;
  dem_instrument?: string;
  dem_resolution_m?: number | null;
  grid_cell_size_m?: { dx_min: number; dx_max: number; dy_mean: number };
  window_nodata_pct?: number;
  suitability_class?: string;
}

export interface RouteBrief {
  label: string;
  classification: RouteClassification;
  distance_m: number;
  cost: number;
  terrain_cost: number;
  elevation_gain_m: number;
  max_cell_slope_deg: number;
  known_terrain_pct: number;
}

export interface RouteComparison {
  route_a: RouteBrief;
  route_b: RouteBrief | null;
  difference_b_minus_a?: { distance_m: number; terrain_cost: number; cost: number };
  note: string;
}

export interface RouteSummary {
  geometry: { type: "LineString"; coordinates: [number, number][] };
  cells: number;
  distance_m: number;
  distance_3d_m: number;
  total_ascent_m: number;
  total_descent_m: number;
  max_step_grade_deg: number;
  unknown_terrain_distance_m: number;
  unknown_terrain_fraction: number;
  elevation_profile: { distance_m: number; elevation_m: number | null }[];
  overlap_with_primary?: number;
  // v0.3 (absent on routes saved by v0.2)
  classification?: RouteClassification;
  unverified_segments?: { from_m: number; to_m: number; status: "UNVERIFIED_NO_DEM_DATA" }[];
  max_cell_slope_deg?: number;
  geometry_simplified?: { type: "LineString"; coordinates: [number, number][] };
  metrics?: RouteMetrics;
}

export interface RoutePlanResponse {
  id: number;
  status: "ROUTE_FOUND";
  route_classification?: RouteClassification;
  comparison?: RouteComparison;
  route: RouteSummary;
  return_route?: RouteSummary | null;
  alternative_route?: RouteSummary | null;
  alternative_note?: string;
  grid: { rows: number; cols: number; decimation_factor: number; cell_size_m: { dx_min: number; dx_max: number; dy_mean: number }; window_scale?: number | string };
  profile: RouteProfile;
  dataset: { id: number; name: string; resolution_m: number | null; vertical_datum: string; source: string };
  hazards_considered: number;
  disclaimer: string;
  data_quality: RouteDataQuality;
}

export interface RouteDataQuality {
  dem: { id: number; name: string; instrument: string; product_id: string; resolution_m: number | null; vertical_datum: string; crs: string };
  grid_decimation_factor: number;
  grid_cell_size_m: { dx_min: number; dx_max: number; dy_mean: number };
  window_nodata_fraction: number;
  route_unknown_terrain_fraction: number | null;
  latitude_handling: string;
  resolution_assessment: {
    effective_cell_m: number;
    dataset_resolution_m: number | null;
    class: "DETAILED_TRAVERSE_STUDY" | "SITE_RECONNAISSANCE" | "REGIONAL_PLANNING_ONLY";
    allowed_use: string;
    smallest_resolvable_feature_m: number;
    suitable_for_astronaut_scale_route_safety: false;
    astronaut_scale_route_safety: "NOT_SUITABLE" | "NOT_ASSESSED_NO_VALIDATED_MODEL";
    reason: string;
  };
  planning_scope?: { scope: string; reason: string };
}

export interface RoutePoint extends MarsPointFields {
  planet?: string;
}
