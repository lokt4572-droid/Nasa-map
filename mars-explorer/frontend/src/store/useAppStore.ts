import { create } from "zustand";

import { MARS_LAYERS } from "../config/mapLayers";
import type { TileGridInfo, TileStats } from "../services/marsMapService";
import type {
  CoverageResponse,
  Dataset,
  Hazard,
  HealthResponse,
  Mission,
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

export type SidebarSection = "layers" | "terrain" | "science" | "missions" | "hazards" | "data";

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

  setLayerVisible: (id: string, visible: boolean) => void;
  setLayerOpacity: (id: string, opacity: number) => void;
  patchLayer: (id: string, patch: Partial<LayerRuntimeState>) => void;
  retryLayer: (id: string) => void;
  setActiveLayer: (id: string) => void;
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
}

function initialLayers(): Record<string, LayerRuntimeState> {
  return Object.fromEntries(
    MARS_LAYERS.map((l) => [
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

export const emptyPointInfo = (): PointInfo => ({ coverage: idle(), sample: idle(), slope: idle() });

export const useAppStore = create<AppState>((set) => ({
  layers: initialLayers(),
  activeLayerId: MARS_LAYERS.find((l) => l.defaultEnabled)?.id ?? MARS_LAYERS[0]!.id,
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
  settings: { lonMode: "180", showSettings: false },

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
  setSettings: (patch) => set((s) => ({ settings: { ...s.settings, ...patch } })),
}));
