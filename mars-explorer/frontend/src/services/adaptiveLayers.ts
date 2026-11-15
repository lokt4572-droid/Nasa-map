/**
 * Adaptive layer loading (Phase 2): which layers are useful for the current view, and which
 * regional high-resolution layers to switch on/off automatically.
 *
 * Rules (scientific, not cosmetic):
 * - The global parent layer is never switched off: where a high-resolution layer has no
 *   coverage, the parent stays visible (no blank areas, no substitution).
 * - Products are not interchangeable. Viking (albedo), THEMIS (thermal IR), MOLA (relief
 *   visualization), CTX and HiRISE (orthoimages) show different physical quantities; auto mode only
 *   adds a regional layer *over* the parent and the UI always names the instrument shown.
 * - A regional layer is only requested when its coverage is in view and big enough to see
 *   (see regionalMaxResolution), so it never competes with the base map at global zoom.
 * - A user's explicit choice wins: a layer the user switched off is never re-enabled by auto mode,
 *   and a layer the user switched on is never switched off by it.
 * - Overzoom (view finer than the product's native resolution) is reported, never hidden.
 */
import type { BBox, MarsMapLayer } from "../config/mapLayers";

export type ViewScale = "GLOBAL" | "REGIONAL" | "LOCAL";
export type CoverageAtView = "OUTSIDE_VIEW" | "BELOW_DISPLAY_THRESHOLD" | "IN_VIEW" | "OVERZOOMED";

/** A regional layer is only rendered once its coverage spans at least this many pixels. */
export const REGIONAL_MIN_PIXELS = 64;
/** Auto mode switches a layer off only when zoomed out this factor past its threshold (hysteresis). */
export const AUTO_OFF_HYSTERESIS = 2;
/** Overzoom is reported when the view is this many times finer than the native resolution. */
export const OVERZOOM_FACTOR = 2;

/** View scale thresholds, in metres per pixel on the body's equatorial radius. */
export const SCALE_THRESHOLDS_M = { GLOBAL: 2000, REGIONAL: 50 };

export function metersPerPixel(resolutionDeg: number, radiusM: number): number {
  return (resolutionDeg * Math.PI * radiusM) / 180;
}

export function viewScale(resolutionDeg: number, radiusM: number): ViewScale {
  const m = metersPerPixel(resolutionDeg, radiusM);
  if (m > SCALE_THRESHOLDS_M.GLOBAL) return "GLOBAL";
  if (m > SCALE_THRESHOLDS_M.REGIONAL) return "REGIONAL";
  return "LOCAL";
}

/**
 * Resolution limit (deg/px) above which a regional layer is not rendered (and requests no
 * tiles). Without it, a 0.5 deg CTX/HiRISE mosaic requests coarse, mostly empty tiles at the
 * global view and competes with the base map for NASA Trek's ~6 HTTP/1.1 connections.
 */
export function regionalMaxResolution(layer: Pick<MarsMapLayer, "coverage" | "bbox">): number | undefined {
  if (layer.coverage !== "regional") return undefined;
  const span = Math.max(layer.bbox.east - layer.bbox.west, layer.bbox.north - layer.bbox.south);
  return span / REGIONAL_MIN_PIXELS;
}

/**
 * Finest resolution (deg/px) of the layer: from its GetCapabilities tile grid when loaded,
 * otherwise from the verified level count on NASA Trek's decimal-degree grid (level 0 =
 * 2x1 tiles of 256 px = 0.703125 deg/px, halving per level).
 */
export function nativeResolutionDeg(layer: Pick<MarsMapLayer, "tileMatrixLevelsVerified">, gridResolutions?: number[] | null): number {
  if (gridResolutions && gridResolutions.length) return Math.min(...gridResolutions);
  return 0.703125 / 2 ** Math.max(0, layer.tileMatrixLevelsVerified - 1);
}

export function bboxIntersectsExtent(b: BBox, extent: number[], worldWidth = 360): boolean {
  const [w, s, e, n] = extent as [number, number, number, number];
  if (n <= b.south || s >= b.north) return false;
  return [-worldWidth, 0, worldWidth].some((shift) => e + shift > b.west && w + shift < b.east);
}

export function coverageAtView(
  layer: Pick<MarsMapLayer, "coverage" | "bbox" | "tileMatrixLevelsVerified">,
  extent: number[],
  resolutionDeg: number,
  gridResolutions?: number[] | null,
): CoverageAtView {
  if (!bboxIntersectsExtent(layer.bbox, extent)) return "OUTSIDE_VIEW";
  const maxRes = regionalMaxResolution(layer);
  if (maxRes !== undefined && resolutionDeg > maxRes) return "BELOW_DISPLAY_THRESHOLD";
  if (resolutionDeg * OVERZOOM_FACTOR < nativeResolutionDeg(layer, gridResolutions)) return "OVERZOOMED";
  return "IN_VIEW";
}

export interface LayerView {
  visible: boolean;
  autoEnabled?: boolean;
  autoSuppressed?: boolean;
  gridResolutions?: number[] | null;
}

export interface AutoChange {
  id: string;
  visible: boolean;
  reason: string;
}

/**
 * Auto high-resolution switching for regional layers. Returns only the changes to apply.
 * Global layers are never touched.
 */
export function autoLayerChanges(
  layers: MarsMapLayer[],
  states: Record<string, LayerView | undefined>,
  extent: number[],
  resolutionDeg: number,
  enabled: boolean,
): AutoChange[] {
  const out: AutoChange[] = [];
  for (const l of layers) {
    if (l.coverage !== "regional") continue;
    const st = states[l.id];
    if (!st) continue;
    const maxRes = regionalMaxResolution(l)!;
    const inView = bboxIntersectsExtent(l.bbox, extent);
    if (!enabled) {
      if (st.visible && st.autoEnabled) out.push({ id: l.id, visible: false, reason: "auto mode switched off" });
      continue;
    }
    if (!st.visible && !st.autoSuppressed && inView && resolutionDeg <= maxRes) {
      out.push({ id: l.id, visible: true, reason: "high-resolution coverage in view" });
    } else if (st.visible && st.autoEnabled && (!inView || resolutionDeg > maxRes * AUTO_OFF_HYSTERESIS)) {
      out.push({ id: l.id, visible: false, reason: inView ? "zoomed out" : "coverage left the view" });
    }
  }
  return out;
}

export interface DataAtPoint {
  layer: MarsMapLayer;
  nativeDeg: number;
  visible: boolean;
}

/** Layers whose coverage contains the point, finest native resolution first. */
export function dataAtPoint(
  layers: MarsMapLayer[],
  states: Record<string, LayerView | undefined>,
  lon: number,
  lat: number,
): DataAtPoint[] {
  return layers
    .filter((l) => lon >= l.bbox.west && lon <= l.bbox.east && lat >= l.bbox.south && lat <= l.bbox.north)
    .map((l) => ({ layer: l, nativeDeg: nativeResolutionDeg(l, states[l.id]?.gridResolutions), visible: !!states[l.id]?.visible }))
    .sort((a, b) => a.nativeDeg - b.nativeDeg);
}

/**
 * What the user actually sees at the view centre: the top-most visible layer covering it
 * (layers later in the catalog draw on top) and whether finer data exists there.
 */
export function shownAtCenter(
  layers: MarsMapLayer[],
  states: Record<string, LayerView | undefined>,
  lon: number,
  lat: number,
  resolutionDeg: number,
): { shown: MarsMapLayer | null; finest: MarsMapLayer | null; overzoomed: boolean } {
  const here = dataAtPoint(layers, states, lon, lat);
  const drawn = here.filter((d) => {
    if (!d.visible) return false;
    const maxRes = regionalMaxResolution(d.layer);
    return maxRes === undefined || resolutionDeg <= maxRes;
  });
  const top = drawn.sort((a, b) => layers.indexOf(b.layer) - layers.indexOf(a.layer))[0] ?? null;
  return {
    shown: top?.layer ?? null,
    finest: here[0]?.layer ?? null,
    overzoomed: !!top && resolutionDeg * OVERZOOM_FACTOR < top.nativeDeg,
  };
}

/** Human-readable ground resolution. */
export function formatMpp(m: number): string {
  if (m >= 1000) return `${(m / 1000).toFixed(m >= 10_000 ? 0 : 1)} km/px`;
  if (m >= 1) return `${m.toFixed(m >= 10 ? 0 : 1)} m/px`;
  return `${Math.round(m * 100)} cm/px`;
}
