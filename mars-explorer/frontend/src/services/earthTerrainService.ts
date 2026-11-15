/**
 * Earth terrain colours from a real DEM: Copernicus DEM GLO-30 (a surface model) for the tile
 * at the view centre, rendered by the backend for the part of the view inside that tile.
 * No tile (ocean, or a country not in the public release) -> NO DATA; nothing is drawn.
 */
import type { DemProduct } from "./datasetDiscoveryService";
import { apiRequest } from "./api";
import { fetchTerrainRender } from "./datasetService";

export const MAX_VIEW_SPAN_DEG = 1.5; // larger views are decimated beyond use; zoom in first

export interface EarthTerrainImage {
  url: string;
  bbox: [number, number, number, number];
  min: number | null;
  max: number | null;
  units: string;
  dataset: string;
  tile: string;
  validFraction: number | null;
}

export const MAX_TILES = 4;

/** Colour ramps used by the backend renderer (services/raster_render.py): kept identical here
 * so the legend shows exactly what is drawn. Elevation positions are fractions of the range. */
export const ELEVATION_STOPS: [number, [number, number, number]][] = [[0, [40, 60, 140]], [0.25, [60, 150, 120]], [0.5, [190, 180, 90]], [0.75, [150, 95, 50]], [1, [245, 245, 245]]];
export const SLOPE_STOPS: [number, [number, number, number]][] = [[0, [60, 160, 90]], [10, [200, 210, 80]], [20, [240, 170, 60]], [30, [230, 90, 40]], [45, [150, 20, 30]]];

export function cssGradient(stops: [number, [number, number, number]][]): string {
  const max = stops[stops.length - 1]![0];
  return `linear-gradient(to right, ${stops.map(([v, [r, g, b]]) => `rgb(${r},${g},${b}) ${((v / max) * 100).toFixed(1)}%`).join(", ")})`;
}

export type EarthTerrainResult =
  | { status: "ready"; images: EarthTerrainImage[]; missingTiles: number }
  | { status: "no-data"; message: string };

/** The part of the view inside the 1x1 degree tile [w, s, w+1, s+1] (null if they do not overlap). */
export function clipToTile(view: [number, number, number, number], tile: [number, number, number, number]): [number, number, number, number] | null {
  const w = Math.max(view[0], tile[0]);
  const s = Math.max(view[1], tile[1]);
  const e = Math.min(view[2], tile[2]);
  const n = Math.min(view[3], tile[3]);
  return w < e && s < n ? [w, s, e, n] : null;
}

/** Pixel size of the render: aspect of the box on the ground, longest side <= maxSide. */
export function renderSize(bbox: [number, number, number, number], maxSide = 768): { width: number; height: number } {
  const midLat = ((bbox[1] + bbox[3]) / 2) * (Math.PI / 180);
  const wDeg = (bbox[2] - bbox[0]) * Math.cos(midLat);
  const hDeg = bbox[3] - bbox[1];
  const k = maxSide / Math.max(wDeg, hDeg);
  return { width: Math.max(16, Math.round(wDeg * k)), height: Math.max(16, Math.round(hDeg * k)) };
}

type Req = typeof apiRequest;

export async function renderEarthTerrain(
  view: [number, number, number, number],
  product: "elevation" | "hillshade" | "slope",
  opts: { signal?: AbortSignal; request?: Req; render?: typeof fetchTerrainRender } = {},
): Promise<EarthTerrainResult> {
  const request = opts.request ?? apiRequest;
  if (view[2] - view[0] > MAX_VIEW_SPAN_DEG || view[3] - view[1] > MAX_VIEW_SPAN_DEG) {
    return { status: "no-data", message: `Zoom in: terrain colours are rendered for views up to ${MAX_VIEW_SPAN_DEG}° across.` };
  }
  const found = await request<{ products: DemProduct[] }>("/datasets/search/", {
    query: { planet: "EARTH", bbox: view.map((v) => v.toFixed(5)).join(","), data_type: "DEM", limit: MAX_TILES },
    signal: opts.signal,
    timeoutMs: 45_000,
  });
  const tiles = found.products.filter((t) => t.bbox && clipToTile(view, t.bbox));
  if (!tiles.length) {
    return { status: "no-data", message: "NO DATA: no Copernicus DEM tile covers this view (ocean, or not in the public 30 m release). Nothing is drawn." };
  }
  // Every 1x1 degree cell the view touches; cells without a tile stay empty (never filled).
  const cells = (Math.ceil(view[2]) - Math.floor(view[0])) * (Math.ceil(view[3]) - Math.floor(view[1]));
  const images: EarthTerrainImage[] = [];
  const registered: number[] = [];
  for (const tile of tiles) {
    const reg = await request<{ registered_dataset_id: number }>("/datasets/register-remote/", {
      method: "POST",
      body: { collection: tile.dataset_id, product_id: tile.product_id },
      signal: opts.signal,
      timeoutMs: 90_000,
    });
    registered.push(reg.registered_dataset_id);
    const bbox = clipToTile(view, tile.bbox!)!;
    const img = await (opts.render ?? fetchTerrainRender)({ dataset: reg.registered_dataset_id, product, bbox, ...renderSize(bbox), crs: "EPSG:4326" }, opts.signal);
    images.push({ url: img.url, bbox, min: img.min, max: img.max, units: img.units, dataset: img.dataset, tile: tile.product_id, validFraction: img.validFraction });
  }
  // Elevation colours are stretched per render. With several tiles, re-render them all with one
  // shared range so that a colour means the same height across tile boundaries.
  if (product === "elevation" && images.length > 1) {
    const lo = Math.min(...images.map((i) => i.min ?? Infinity));
    const hi = Math.max(...images.map((i) => i.max ?? -Infinity));
    if (Number.isFinite(lo) && Number.isFinite(hi) && lo < hi) {
      for (let k = 0; k < images.length; k++) {
        const old = images[k]!;
        const datasetId = registered[k]!;
        const img = await (opts.render ?? fetchTerrainRender)({ dataset: datasetId, product, bbox: old.bbox, ...renderSize(old.bbox), crs: "EPSG:4326", range: [lo, hi] }, opts.signal);
        if (typeof URL !== "undefined" && old.url.startsWith("blob:")) URL.revokeObjectURL(old.url);
        images[k] = { ...old, url: img.url };
      }
    }
  }
  return { status: "ready", images, missingTiles: Math.max(0, cells - tiles.length) };
}
