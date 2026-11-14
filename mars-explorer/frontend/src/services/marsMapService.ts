/**
 * Map initialisation and NASA Mars Trek WMTS layer loading.
 *
 * Algorithm for every layer (no tile matrices are hard-coded):
 *   1. fetch GetCapabilities XML, check the HTTP response;
 *   2. parse it with ol/format/WMTSCapabilities;
 *   3. find the layer identifier;
 *   4. build options with optionsFromCapabilities (TileMatrixSet, TileMatrix ids,
 *      resolutions, origin, extent, ResourceURL template, format, style);
 *   5. check the TileMatrixSet CRS is the registered Mars CRS;
 *   6. create the WMTS source and TileLayer, add it to the map;
 *   7. report tile load progress and errors.
 */
import OlMap from "ol/Map";
import View from "ol/View";
import { defaults as defaultControls } from "ol/control/defaults";
import type { Extent } from "ol/extent";
import WMTSCapabilities from "ol/format/WMTSCapabilities";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import WMTS, { optionsFromCapabilities } from "ol/source/WMTS";
import VectorSource from "ol/source/Vector";
import type WMTSTileGrid from "ol/tilegrid/WMTS";

import { type BBox, MARS_LAYERS, type MarsMapLayer } from "../config/mapLayers";
import { MARS_GEOGRAPHIC_EXTENT, TREK_DECLARED_CRS, registerMarsProjections } from "../config/marsProjection";

export type WmtsErrorCode =
  | "CAPABILITIES_NETWORK"
  | "CAPABILITIES_TIMEOUT"
  | "CAPABILITIES_HTTP"
  | "CAPABILITIES_PARSE"
  | "LAYER_NOT_FOUND"
  | "UNSUPPORTED_CRS"
  | "NO_CAPABILITIES_URL";

export class WmtsLayerError extends Error {
  constructor(
    public readonly code: WmtsErrorCode,
    message: string,
    public readonly layerId: string,
  ) {
    super(message);
    this.name = "WmtsLayerError";
  }
}

export interface TileGridInfo {
  matrixSet: string;
  matrixIds: string[];
  resolutionsDegPerPx: number[];
  origin: [number, number];
  extent: Extent | null;
  format: string;
  urlTemplate: string;
  projection: string;
}

const capabilitiesCache = new Map<string, Promise<unknown>>();

export function clearCapabilitiesCache(): void {
  capabilitiesCache.clear();
}

export async function fetchCapabilities(
  url: string,
  layerId: string,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = 20_000,
): Promise<unknown> {
  const cached = capabilitiesCache.get(url);
  if (cached) return cached;
  const promise = (async () => {
    const controller = new AbortController();
    const t = setTimeout(() => controller.abort(), timeoutMs);
    let res: Response;
    try {
      res = await fetchImpl(url, { signal: controller.signal });
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError";
      throw new WmtsLayerError(
        aborted ? "CAPABILITIES_TIMEOUT" : "CAPABILITIES_NETWORK",
        aborted
          ? `NASA Trek GetCapabilities timed out after ${timeoutMs / 1000}s`
          : "NASA Trek WMTS is unreachable (network error). Check the internet connection and retry.",
        layerId,
      );
    } finally {
      clearTimeout(t);
    }
    if (!res.ok) {
      throw new WmtsLayerError("CAPABILITIES_HTTP", `NASA Trek GetCapabilities returned HTTP ${res.status}`, layerId);
    }
    return parseCapabilities(await res.text(), layerId);
  })();
  capabilitiesCache.set(url, promise);
  // Do not cache failures: allow "Retry".
  promise.catch(() => capabilitiesCache.delete(url));
  return promise;
}

/**
 * NASA Trek writes MatrixWidth/MatrixHeight as decimals ("2.0"), while the OGC schema
 * types them as positiveInteger. OpenLayers' parser (ol/format/xsd readPositiveInteger)
 * then returns undefined, the tile grid gets no tile ranges, and every tile is EMPTY
 * (verified with OL 10.11 against the live service on 2026-11-12). We rewrite only
 * values that are exactly integral ("2.0" -> "2"); anything else is left untouched and
 * rejected by validateTileMatrices().
 */
export function normalizeTrekCapabilitiesXml(xml: string): string {
  return xml.replace(
    /<(MatrixWidth|MatrixHeight)>\s*([0-9]+(?:\.0+)?)\s*<\/\1>/g,
    (_m, tag: string, value: string) => `<${tag}>${parseInt(value, 10)}</${tag}>`,
  );
}

function validateTileMatrices(caps: Record<string, unknown>, layerId: string): void {
  const sets = ((caps["Contents"] as Record<string, unknown>)?.["TileMatrixSet"] ?? []) as Record<string, unknown>[];
  for (const set of sets) {
    for (const m of (set["TileMatrix"] ?? []) as Record<string, unknown>[]) {
      for (const key of ["MatrixWidth", "MatrixHeight", "TileWidth", "TileHeight"]) {
        const v = m[key];
        if (typeof v !== "number" || !Number.isInteger(v) || v <= 0) {
          throw new WmtsLayerError(
            "CAPABILITIES_PARSE",
            `TileMatrix ${String(m["Identifier"])} of ${String(set["Identifier"])} has invalid ${key}`,
            layerId,
          );
        }
      }
    }
  }
}

export function parseCapabilities(xml: string, layerId: string): unknown {
  let caps: unknown;
  try {
    caps = new WMTSCapabilities().read(normalizeTrekCapabilitiesXml(xml));
  } catch (err) {
    throw new WmtsLayerError("CAPABILITIES_PARSE", `GetCapabilities XML could not be parsed: ${String(err)}`, layerId);
  }
  if (!caps || typeof caps !== "object" || !("Contents" in caps)) {
    throw new WmtsLayerError("CAPABILITIES_PARSE", "GetCapabilities document has no <Contents>", layerId);
  }
  validateTileMatrices(caps as Record<string, unknown>, layerId);
  return caps;
}

export function buildWmtsSource(caps: unknown, layer: MarsMapLayer): WMTS {
  registerMarsProjections();
  // optionsFromCapabilities is typed with a loose object signature.
  const options = optionsFromCapabilities(caps as Parameters<typeof optionsFromCapabilities>[0], {
    layer: layer.layerId,
  });
  if (!options) {
    throw new WmtsLayerError(
      "LAYER_NOT_FOUND",
      `Layer ${layer.layerId} or its TileMatrixSet/CRS was not found in GetCapabilities`,
      layer.layerId,
    );
  }
  const projCode = typeof options.projection === "string" ? options.projection : options.projection?.getCode();
  if (projCode !== TREK_DECLARED_CRS) {
    throw new WmtsLayerError(
      "UNSUPPORTED_CRS",
      `Layer CRS ${String(projCode)} differs from the registered Mars CRS ${TREK_DECLARED_CRS}; refusing to overlay without a transformation`,
      layer.layerId,
    );
  }
  return new WMTS({ ...options, crossOrigin: "anonymous", wrapX: layer.coverage === "global" });
}

export function describeTileGrid(source: WMTS): TileGridInfo {
  const grid = source.getTileGrid() as WMTSTileGrid;
  const origin = grid.getOrigin(0);
  return {
    matrixSet: source.getMatrixSet(),
    matrixIds: grid.getMatrixIds(),
    resolutionsDegPerPx: grid.getResolutions(),
    origin: [origin[0] ?? NaN, origin[1] ?? NaN],
    extent: grid.getExtent() ?? null,
    format: source.getFormat(),
    urlTemplate: source.getUrls()?.[0] ?? "",
    projection: source.getProjection()?.getCode() ?? "",
  };
}

export async function loadWmtsLayer(
  layer: MarsMapLayer,
  fetchImpl: typeof fetch = fetch,
): Promise<{ tileLayer: TileLayer<WMTS>; info: TileGridInfo }> {
  if (!layer.capabilitiesUrl) {
    throw new WmtsLayerError("NO_CAPABILITIES_URL", "Layer has no GetCapabilities URL configured", layer.layerId);
  }
  const caps = await fetchCapabilities(layer.capabilitiesUrl, layer.layerId, fetchImpl);
  const source = buildWmtsSource(caps, layer);
  const info = describeTileGrid(source);
  const tileLayer = new TileLayer({
    source,
    visible: layer.visible,
    opacity: layer.opacity,
    zIndex: MARS_LAYERS.findIndex((l) => l.id === layer.id),
    extent: info.extent ?? undefined,
    properties: { marsLayerId: layer.id },
  });
  return { tileLayer, info };
}

// ---------------------------------------------------------------------------
// Map controller (single map instance per page)

export interface TileStats {
  loading: number;
  loaded: number;
  errors: number;
}

export interface MarsMapHandle {
  map: OlMap;
  view: View;
  markerSource: VectorSource;
  hazardSource: VectorSource;
  waypointSource: VectorSource;
}

export const GLOBAL_VIEW = { center: [0, 0] as [number, number], resolution: 0.3515625 };

export function createMarsMap(target: HTMLElement | undefined): MarsMapHandle {
  const projection = registerMarsProjections();
  const view = new View({
    projection,
    center: GLOBAL_VIEW.center,
    resolution: GLOBAL_VIEW.resolution,
    // Coarsest Trek level (0.703125 deg/px) to finer than HiRISE max level.
    maxResolution: 0.703125,
    minResolution: 0.703125 / 2 ** 19,
    extent: MARS_GEOGRAPHIC_EXTENT,
    constrainOnlyCenter: true,
    smoothExtentConstraint: true,
  });
  const markerSource = new VectorSource();
  const hazardSource = new VectorSource();
  const waypointSource = new VectorSource();
  const map = new OlMap({
    target,
    view,
    layers: [
      new VectorLayer({ source: hazardSource, zIndex: 100, properties: { role: "hazards" } }),
      new VectorLayer({ source: waypointSource, zIndex: 101, properties: { role: "waypoints" } }),
      new VectorLayer({ source: markerSource, zIndex: 102, properties: { role: "marker" } }),
    ],
    controls: defaultControls({ zoom: false, rotate: false, attribution: false }),
  });
  return { map, view, markerSource, hazardSource, waypointSource };
}

export function attachTileStats(source: WMTS, onChange: (s: TileStats) => void): () => void {
  const stats: TileStats = { loading: 0, loaded: 0, errors: 0 };
  const start = () => {
    stats.loading += 1;
    onChange({ ...stats });
  };
  const end = () => {
    stats.loading = Math.max(0, stats.loading - 1);
    stats.loaded += 1;
    onChange({ ...stats });
  };
  const error = () => {
    stats.loading = Math.max(0, stats.loading - 1);
    stats.errors += 1;
    onChange({ ...stats });
  };
  source.on("tileloadstart", start);
  source.on("tileloadend", end);
  source.on("tileloaderror", error);
  return () => {
    source.un("tileloadstart", start);
    source.un("tileloadend", end);
    source.un("tileloaderror", error);
  };
}

export function bboxToExtent(b: BBox): Extent {
  return [b.west, b.south, b.east, b.north];
}

let handle: MarsMapHandle | null = null;

export const mapController = {
  setHandle(h: MarsMapHandle | null) {
    handle = h;
  },
  get handle() {
    return handle;
  },
  zoomBy(delta: number) {
    const view = handle?.view;
    if (!view) return;
    view.animate({ zoom: (view.getZoom() ?? 0) + delta, duration: 200 });
  },
  zoomToGlobal() {
    handle?.view.animate({ center: GLOBAL_VIEW.center, resolution: GLOBAL_VIEW.resolution, duration: 400 });
  },
  zoomToBBox(b: BBox) {
    handle?.view.fit(bboxToExtent(b), { padding: [40, 40, 40, 40], duration: 500 });
  },
  centerOn(lon: number, lat: number, resolution?: number) {
    handle?.view.animate({ center: [lon, lat], ...(resolution ? { resolution } : {}), duration: 400 });
  },
};
