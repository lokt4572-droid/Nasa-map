/**
 * Map overlays that depend on the map instance: terrain visualization image and route lines.
 * Rendered by MarsMap only after the map exists.
 */
import { useEffect, useRef } from "react";
import Feature from "ol/Feature";
import LineString from "ol/geom/LineString";
import Point from "ol/geom/Point";
import ImageLayer from "ol/layer/Image";
import VectorLayer from "ol/layer/Vector";
import ImageStatic from "ol/source/ImageStatic";
import VectorSource from "ol/source/Vector";
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from "ol/style";

import { describeError } from "../../services/api";
import { fetchTerrainRender } from "../../services/datasetService";
import { mapController } from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";

const MAX_PX = 1024;

export function TerrainOverlay() {
  const overlay = useAppStore((s) => s.terrainOverlay);
  const datasets = useAppStore((s) => s.datasets.data);
  const layerRef = useRef<ImageLayer<ImageStatic> | null>(null);
  const urlRef = useRef<string | null>(null);
  const dem = datasets?.find((d) => d.status === "VALID" && d.data_type === "DEM" && (d.planet ?? "MARS") === "MARS");

  useEffect(() => {
    const h = mapController.handle;
    if (!h) return;
    const layer = new ImageLayer<ImageStatic>({ zIndex: 50, properties: { role: "terrain-visualization" } });
    layerRef.current = layer;
    h.map.addLayer(layer);
    return () => {
      h.map.removeLayer(layer);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    };
  }, []);

  useEffect(() => {
    layerRef.current?.setOpacity(overlay.opacity);
  }, [overlay.opacity]);

  useEffect(() => {
    const h = mapController.handle;
    const layer = layerRef.current;
    if (!h || !layer) return;
    const { setTerrainOverlay } = useAppStore.getState();
    if (!overlay.product || !dem) {
      layer.setSource(null);
      layer.setVisible(false);
      return;
    }
    layer.setVisible(true);
    let ctrl: AbortController | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const refresh = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const size = h.map.getSize();
        if (!size) return;
        const ext = h.view.calculateExtent(size);
        const bbox: [number, number, number, number] = [Math.max(ext[0]!, -180), Math.max(ext[1]!, -90), Math.min(ext[2]!, 180), Math.min(ext[3]!, 90)];
        if (bbox[0] >= bbox[2] || bbox[1] >= bbox[3]) return;
        const frac = [(bbox[2] - bbox[0]) / (ext[2]! - ext[0]!), (bbox[3] - bbox[1]) / (ext[3]! - ext[1]!)];
        const scale = Math.min(1, MAX_PX / Math.max(size[0]!, size[1]!));
        const width = Math.max(16, Math.round(size[0]! * frac[0]! * scale));
        const height = Math.max(16, Math.round(size[1]! * frac[1]! * scale));
        ctrl?.abort();
        ctrl = new AbortController();
        setTerrainOverlay({ status: "loading", error: null });
        try {
          const r = await fetchTerrainRender({ dataset: dem.id, product: overlay.product!, bbox, width, height }, ctrl.signal);
          if (urlRef.current) URL.revokeObjectURL(urlRef.current);
          urlRef.current = r.url;
          layer.setSource(new ImageStatic({ url: r.url, imageExtent: bbox, projection: h.view.getProjection() }));
          setTerrainOverlay({ status: "ready", meta: { min: r.min, max: r.max, units: r.units, validFraction: r.validFraction, dataset: r.dataset } });
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") return;
          setTerrainOverlay({ status: "error", error: describeError(err) });
        }
      }, 350); // debounce map movement
    };
    refresh();
    h.map.on("moveend", refresh);
    return () => {
      h.map.un("moveend", refresh);
      clearTimeout(timer);
      ctrl?.abort();
    };
  }, [overlay.product, dem]);

  return null;
}

const routeStyles = {
  primary: new Style({ stroke: new Stroke({ color: "#ff8c2e", width: 3 }) }),
  alternative: new Style({ stroke: new Stroke({ color: "#5fb3d9", width: 2, lineDash: [8, 6] }) }),
};

function pointStyle(label: string, color: string) {
  return new Style({
    image: new CircleStyle({ radius: 6, fill: new Fill({ color }), stroke: new Stroke({ color: "#14161a", width: 2 }) }),
    text: new Text({ text: label, offsetY: -14, font: "bold 11px Inter, system-ui, sans-serif", fill: new Fill({ color: "#f3efe9" }), stroke: new Stroke({ color: "#14161a", width: 3 }) }),
  });
}

export function RouteOverlay() {
  const draft = useAppStore((s) => s.routeDraft);
  const result = useAppStore((s) => s.routeResult.data);
  const srcRef = useRef<VectorSource | null>(null);

  useEffect(() => {
    const h = mapController.handle;
    if (!h) return;
    const src = new VectorSource();
    srcRef.current = src;
    const layer = new VectorLayer({ source: src, zIndex: 103, properties: { role: "route" } });
    h.map.addLayer(layer);
    return () => {
      h.map.removeLayer(layer);
    };
  }, []);

  useEffect(() => {
    const src = srcRef.current;
    if (!src) return;
    src.clear();
    if (result?.alternative_route) {
      const f = new Feature(new LineString(result.alternative_route.geometry.coordinates));
      f.setStyle(routeStyles.alternative);
      src.addFeature(f);
    }
    if (result?.route) {
      const f = new Feature(new LineString(result.route.geometry.coordinates));
      f.setStyle(routeStyles.primary);
      src.addFeature(f);
    }
    const pts: [string, string, typeof draft.start][] = [
      ["START", "#6fbf73", draft.start],
      ["END", "#ef5a4c", draft.end],
      ...draft.waypoints.map((w, i) => [`VIA ${i + 1}`, "#c9d1d9", w] as [string, string, typeof draft.start]),
    ];
    for (const [label, color, p] of pts) {
      if (!p) continue;
      const f = new Feature(new Point([p.lon_east_deg, p.lat_deg]));
      f.setStyle(pointStyle(label, color));
      src.addFeature(f);
    }
  }, [draft, result]);

  return null;
}
