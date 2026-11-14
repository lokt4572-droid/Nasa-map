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
  created_at: string;
  updated_at: string;
}

export type HazardInput = Omit<Hazard, "id" | "created_at" | "updated_at" | "verification" | "observed_at"> & {
  verification?: HazardVerification;
};
