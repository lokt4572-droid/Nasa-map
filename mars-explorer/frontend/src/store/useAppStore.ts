import { create } from "zustand";

import { ALL_LAYERS, layersForPlanet } from "../config/mapLayers";
import type { GibsDiscovery } from "../services/earthService";
import { DEFAULT_PLANET, type PlanetId } from "../config/planetRegistry";
import type { TileGridInfo, TileStats } from "../services/marsMapService";
import type {
  CoverageResponse,
  Dataset,
  Hazard,
  HealthResponse,
  Mission,
  RoutePlanResponse,
  RoutePoint,
  RouteProfileId,
  SampleResponse,
  SlopeResponse,
} from "../types/api";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

export interface LayerRuntimeState {
  visible: boolean;
  opacity: number;
  status: LoadStatus;
  error: string | null;
  errorCode: string | null;
  tiles: TileStats;
  grid: TileGridInfo | null;
  /** bump to force a reload (Retry) */
  attempt: number;
}

export type SidebarSection =
  | "layers" | "terrain" | "science" | "missions" | "routes" | "hazards" | "data"
  | "e-layers" | "e-sat" | "e-weather" | "e-location" | "e-terrain" | "e-3d";

export interface EarthState {
  gibs: Remote<GibsDiscovery>;
  base: string; // "OSM" or a GIBS SATELLITE layer id
  overlays: string[]; // GIBS overlay ids, bottom -> top
  dates: Record<string, string>; // selected YYYY-MM-DD per time-enabled layer
  overlayOpacity: number;
  measure: { active: boolean; points: [number, number][] };
  view: "2D" | "3D";
  flyTo: { lon: number; lat: number; zoom?: number; bbox?: [number, number, number, number]; seq: number } | null;
}

export type TerrainProduct = "elevation" | "hillshade" | "slope" | "aspect" | "roughness";

export interface TerrainOverlayState {
  product: TerrainProduct | null;
  opacity: number;
  status: LoadStatus;
  error: string | null;
  meta: { min: number | null; max: number | null; units: string; validFraction: number | null; dataset: string } | null;
}

export interface RouteDraft {
  start: RoutePoint | null;
  end: RoutePoint | null;
  waypoints: RoutePoint[];
  profile: RouteProfileId;
}

export interface SelectedPoint {
  lon: number;
  lat: number;
  crs: string;
  layerId: string; // active layer when picked
  pickedAt: string;
}

export interface Remote<T> {
  status: LoadStatus;
  data: T | null;
  error: string | null;
  errorCode?: string | null;
}

const idle = <T,>(): Remote<T> => ({ status: "idle", data: null, error: null, errorCode: null });

export interface PointInfo {
  coverage: Remote<CoverageResponse>;
  sample: Remote<SampleResponse>;
  slope: Remote<SlopeResponse>;
}

interface AppState {
  layers: Record<string, LayerRuntimeState>;
  activeLayerId: string;
  planet: PlanetId;
  section: SidebarSection;
  cursor: { lon: number; lat: number } | null;
  view: { resolution: number; centerLat: number; zoom: number };
  selectedPoint: SelectedPoint | null;
  pointInfo: PointInfo;
  backend: { status: "unknown" | "online" | "offline"; health: HealthResponse | null; error: string | null };
  missions: Remote<Mission[]>;
  hazards: Remote<Hazard[]>;
  datasets: Remote<Dataset[]>;
  activeMissionId: number | null;
  settings: { lonMode: "180" | "360"; showSettings: boolean };
  terrainOverlay: TerrainOverlayState;
  routeDraft: RouteDraft;
  routeResult: Remote<RoutePlanResponse>;
  earth: EarthState;

  setLayerVisible: (id: string, visible: boolean) => void;
  setLayerOpacity: (id: string, opacity: number) => void;
  patchLayer: (id: string, patch: Partial<LayerRuntimeState>) => void;
  retryLayer: (id: string) => void;
  setActiveLayer: (id: string) => void;
  setPlanet: (planet: PlanetId) => void;
  setSection: (s: SidebarSection) => void;
  setCursor: (c: { lon: number; lat: number } | null) => void;
  setView: (v: AppState["view"]) => void;
  selectPoint: (p: SelectedPoint | null) => void;
  setPointInfo: (patch: Partial<PointInfo>) => void;
  setBackend: (b: AppState["backend"]) => void;
  setMissions: (r: Remote<Mission[]>) => void;
  setHazards: (r: Remote<Hazard[]>) => void;
  setDatasets: (r: Remote<Dataset[]>) => void;
  setActiveMission: (id: number | null) => void;
  setSettings: (s: Partial<AppState["settings"]>) => void;
  setTerrainOverlay: (patch: Partial<TerrainOverlayState>) => void;
  setRouteDraft: (patch: Partial<RouteDraft>) => void;
  setRouteResult: (r: Remote<RoutePlanResponse>) => void;
  setEarth: (patch: Partial<EarthState>) => void;
  flyTo: (target: { lon: number; lat: number; zoom?: number; bbox?: [number, number, number, number] }) => void;
}

function initialLayers(): Record<string, LayerRuntimeState> {
  return Object.fromEntries(
    ALL_LAYERS.map((l) => [
      l.id,
      {
        visible: l.defaultEnabled,
        opacity: l.opacity,
        status: "idle" as LoadStatus,
        error: null,
        errorCode: null,
        tiles: { loading: 0, loaded: 0, errors: 0 },
        grid: null,
        attempt: 0,
      },
    ]),
  );
}

// Settings persist in localStorage (fix for bug B8). Only non-sensitive UI preferences.
const SETTINGS_KEY = "mars-explorer.settings.v1";
type Settings = { lonMode: "180" | "360"; showSettings: boolean };

export function loadSettings(): Settings {
  const defaults: Settings = { lonMode: "180", showSettings: false };
  try {
    const raw = typeof localStorage !== "undefined" ? localStorage.getItem(SETTINGS_KEY) : null;
    if (!raw) return defaults;
    const parsed = JSON.parse(raw) as Partial<Settings>;
    return { ...defaults, lonMode: parsed.lonMode === "360" ? "360" : "180" };
  } catch {
    return defaults;
  }
}

function saveSettings(s: Settings): void {
  try {
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ lonMode: s.lonMode }));
  } catch {
    /* storage unavailable (private mode): settings stay in memory */
  }
}

/** Default layer of a body ("" for bodies without a map service). */
export function defaultLayerFor(planet: PlanetId): string {
  const ls = layersForPlanet(planet);
  return (ls.find((l) => l.defaultEnabled) ?? ls[0])?.id ?? "";
}

export const emptyPointInfo = (): PointInfo => ({ coverage: idle(), sample: idle(), slope: idle() });

export const useAppStore = create<AppState>((set) => ({
  layers: initialLayers(),
  activeLayerId: defaultLayerFor(DEFAULT_PLANET),
  planet: DEFAULT_PLANET,
  section: "layers",
  cursor: null,
  view: { resolution: 0.3515625, centerLat: 0, zoom: 1 },
  selectedPoint: null,
  pointInfo: emptyPointInfo(),
  backend: { status: "unknown", health: null, error: null },
  missions: idle(),
  hazards: idle(),
  datasets: idle(),
  activeMissionId: null,
  settings: loadSettings(),
  terrainOverlay: { product: null, opacity: 0.75, status: "idle", error: null, meta: null },
  routeDraft: { start: null, end: null, waypoints: [], profile: "CONSERVATIVE" },
  routeResult: idle(),
  earth: {
    gibs: idle(),
    base: "OSM",
    overlays: [],
    dates: {},
    overlayOpacity: 0.8,
    measure: { active: false, points: [] },
    view: "2D",
    flyTo: null,
  },

  setLayerVisible: (id, visible) =>
    set((s) => ({
      layers: { ...s.layers, [id]: { ...s.layers[id]!, visible } },
      activeLayerId: visible ? id : s.activeLayerId,
    })),
  setLayerOpacity: (id, opacity) =>
    set((s) => ({ layers: { ...s.layers, [id]: { ...s.layers[id]!, opacity: Math.min(1, Math.max(0, opacity)) } } })),
  patchLayer: (id, patch) => set((s) => ({ layers: { ...s.layers, [id]: { ...s.layers[id]!, ...patch } } })),
  retryLayer: (id) =>
    set((s) => ({
      layers: {
        ...s.layers,
        [id]: { ...s.layers[id]!, status: "idle", error: null, errorCode: null, attempt: s.layers[id]!.attempt + 1 },
      },
    })),
  setActiveLayer: (id) => set({ activeLayerId: id }),
  setPlanet: (planet) =>
    set((s) =>
      s.planet === planet
        ? {}
        : {
            planet,
            activeLayerId: defaultLayerFor(planet),
            selectedPoint: null,
            pointInfo: emptyPointInfo(),
            cursor: null,
            section: planet === "EARTH" ? "e-layers" : "layers",
            terrainOverlay: { ...s.terrainOverlay, product: null, meta: null, status: "idle" },
          },
    ),
  setSection: (section) => set({ section }),
  setCursor: (cursor) => set({ cursor }),
  setView: (view) => set({ view }),
  selectPoint: (selectedPoint) => set({ selectedPoint, pointInfo: emptyPointInfo() }),
  setPointInfo: (patch) => set((s) => ({ pointInfo: { ...s.pointInfo, ...patch } })),
  setBackend: (backend) => set({ backend }),
  setMissions: (missions) => set({ missions }),
  setHazards: (hazards) => set({ hazards }),
  setDatasets: (datasets) => set({ datasets }),
  setActiveMission: (activeMissionId) => set({ activeMissionId }),
  setSettings: (patch) =>
    set((s) => {
      const settings = { ...s.settings, ...patch };
      saveSettings(settings);
      return { settings };
    }),
  setTerrainOverlay: (patch) => set((s) => ({ terrainOverlay: { ...s.terrainOverlay, ...patch } })),
  setRouteDraft: (patch) => set((s) => ({ routeDraft: { ...s.routeDraft, ...patch } })),
  setRouteResult: (routeResult) => set({ routeResult }),
  setEarth: (patch) => set((s) => ({ earth: { ...s.earth, ...patch } })),
  flyTo: (target) => set((s) => ({ earth: { ...s.earth, flyTo: { ...target, seq: (s.earth.flyTo?.seq ?? 0) + 1 } } })),
}));
