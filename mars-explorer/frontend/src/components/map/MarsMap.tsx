import { useEffect, useRef, useState } from "react";
import Feature from "ol/Feature";
import Point from "ol/geom/Point";
import type TileLayer from "ol/layer/Tile";
import type WMTS from "ol/source/WMTS";
import { Circle as CircleStyle, Fill, RegularShape, Stroke, Style, Text } from "ol/style";

import { layersForPlanet } from "../../config/mapLayers";
import { normalizeLon180 } from "../../config/marsProjection";
import { PLANETS } from "../../config/planetRegistry";
import { describeError } from "../../services/api";
import {
  WmtsLayerError,
  attachTileStats,
  createMarsMap,
  loadWmtsLayer,
  mapController,
  type MarsMapHandle,
} from "../../services/marsMapService";
import { useAppStore } from "../../store/useAppStore";
import type { HazardSeverity } from "../../types/api";
import MapControls from "./MapControls";
import MapLegend from "./MapLegend";
import { RouteOverlay, TerrainOverlay } from "./MapOverlays";

const SEVERITY_COLOR: Record<HazardSeverity, string> = {
  UNKNOWN: "#9aa3ad",
  LOW: "#f2c14e",
  MEDIUM: "#f2893a",
  HIGH: "#e5412e",
};

const markerStyle = new Style({
  image: new CircleStyle({
    radius: 7,
    fill: new Fill({ color: "rgba(229,101,46,0.25)" }),
    stroke: new Stroke({ color: "#ffb347", width: 2 }),
  }),
});

function hazardStyle(severity: HazardSeverity, title: string) {
  return new Style({
    image: new RegularShape({
      points: 3,
      radius: 9,
      fill: new Fill({ color: SEVERITY_COLOR[severity] }),
      stroke: new Stroke({ color: "#14161a", width: 1.5 }),
    }),
    text: new Text({
      text: title,
      offsetY: -16,
      font: "11px Inter, system-ui, sans-serif",
      fill: new Fill({ color: "#f3efe9" }),
      stroke: new Stroke({ color: "#14161a", width: 3 }),
    }),
  });
}

function waypointStyle(name: string, kind: string) {
  return new Style({
    image: new RegularShape({
      points: 4,
      radius: 7,
      angle: Math.PI / 4,
      fill: new Fill({ color: kind === "BASE" ? "#5fb3d9" : "#c9d1d9" }),
      stroke: new Stroke({ color: "#14161a", width: 1.5 }),
    }),
    text: new Text({
      text: name,
      offsetY: -15,
      font: "11px Inter, system-ui, sans-serif",
      fill: new Fill({ color: "#dfe7ee" }),
      stroke: new Stroke({ color: "#14161a", width: 3 }),
    }),
  });
}

export default function MarsMap() {
  const targetRef = useRef<HTMLDivElement>(null);
  const handleRef = useRef<MarsMapHandle | null>(null);
  const tileLayers = useRef(new Map<string, { layer: TileLayer<WMTS>; detach: () => void }>());

  const layers = useAppStore((s) => s.layers);
  const hazards = useAppStore((s) => s.hazards.data);
  const missions = useAppStore((s) => s.missions.data);
  const activeMissionId = useAppStore((s) => s.activeMissionId);
  const selectedPoint = useAppStore((s) => s.selectedPoint);
  const [mapReady, setMapReady] = useState(false);
  // The component is remounted per body (key={planet} in App), so planet is fixed here.
  const planet = useAppStore.getState().planet;
  const planetLayers = layersForPlanet(planet);

  // --- map lifecycle
  useEffect(() => {
    const h = createMarsMap(targetRef.current ?? undefined, planet);
    handleRef.current = h;
    mapController.setHandle(h);
    setMapReady(true);
    if (import.meta.env.DEV) (window as unknown as { __marsMap?: MarsMapHandle }).__marsMap = h; // dev-only inspection
    const { setCursor, setView, selectPoint, patchLayer } = useAppStore.getState();
    // A new map instance has no tile layers yet: reset load state that a previous
    // instance (e.g. before switching planets) left as "ready", so layers reload here.
    for (const cfg of planetLayers) {
      patchLayer(cfg.id, { status: "idle", error: null, errorCode: null, grid: null, tiles: { loading: 0, loaded: 0, errors: 0 } });
    }

    let frame = 0;
    const onMove = (evt: { coordinate: number[]; dragging: boolean }) => {
      if (evt.dragging) return;
      cancelAnimationFrame(frame);
      const [x, y] = evt.coordinate;
      frame = requestAnimationFrame(() => {
        if (x === undefined || y === undefined || y < -90 || y > 90) return setCursor(null);
        setCursor({ lon: normalizeLon180(x), lat: y });
      });
    };
    const onClick = (evt: { coordinate: number[] }) => {
      const [x, y] = evt.coordinate;
      if (x === undefined || y === undefined || y < -90 || y > 90) return;
      const st = useAppStore.getState();
      selectPoint({
        lon: normalizeLon180(x),
        lat: y,
        crs: PLANETS[planet].mapCrs!,
        layerId: st.activeLayerId,
        pickedAt: new Date().toISOString(),
      });
    };
    const onMoveEnd = () => {
      const v = h.view;
      setView({ resolution: v.getResolution() ?? 0, centerLat: v.getCenter()?.[1] ?? 0, zoom: v.getZoom() ?? 0 });
    };
    h.map.on("pointermove", onMove);
    h.map.on("singleclick", onClick);
    h.map.on("moveend", onMoveEnd);
    const leave = () => setCursor(null);
    targetRef.current?.addEventListener("mouseleave", leave);
    const target = targetRef.current;
    const layersMap = tileLayers.current;
    return () => {
      target?.removeEventListener("mouseleave", leave);
      layersMap.forEach((l) => l.detach());
      layersMap.clear();
      h.map.setTarget(undefined);
      mapController.setHandle(null);
      setMapReady(false);
      handleRef.current = null;
    };
  }, []);

  // --- WMTS layers: load on first enable, then sync visibility/opacity
  useEffect(() => {
    const h = handleRef.current;
    if (!h) return;
    const { patchLayer } = useAppStore.getState();
    for (const cfg of planetLayers) {
      const st = layers[cfg.id];
      if (!st) continue;
      const existing = tileLayers.current.get(cfg.id);
      if (existing) {
        existing.layer.setVisible(st.visible);
        existing.layer.setOpacity(st.opacity);
        continue;
      }
      if (st.visible && st.status === "idle") {
        patchLayer(cfg.id, { status: "loading", error: null, errorCode: null });
        loadWmtsLayer(cfg)
          .then(({ tileLayer, info }) => {
            if (handleRef.current !== h) return;
            const now = useAppStore.getState().layers[cfg.id]!;
            tileLayer.setVisible(now.visible);
            tileLayer.setOpacity(now.opacity);
            const source = tileLayer.getSource();
            const detach = source ? attachTileStats(source, (tiles) => patchLayer(cfg.id, { tiles })) : () => {};
            tileLayers.current.set(cfg.id, { layer: tileLayer, detach });
            h.map.addLayer(tileLayer);
            patchLayer(cfg.id, { status: "ready", grid: info });
          })
          .catch((err: unknown) => {
            patchLayer(cfg.id, {
              status: "error",
              error: describeError(err),
              errorCode: err instanceof WmtsLayerError ? err.code : "UNKNOWN",
            });
          });
      }
    }
  }, [layers]);

  // --- hazards
  useEffect(() => {
    const src = handleRef.current?.hazardSource;
    if (!src) return;
    src.clear();
    for (const hz of hazards ?? []) {
      const f = new Feature({ geometry: new Point([hz.lon_east_deg, hz.lat_deg]) });
      f.setStyle(hazardStyle(hz.severity, hz.title));
      f.set("hazardId", hz.id);
      src.addFeature(f);
    }
  }, [hazards]);

  // --- waypoints of the active mission
  useEffect(() => {
    const src = handleRef.current?.waypointSource;
    if (!src) return;
    src.clear();
    const mission = missions?.find((m) => m.id === activeMissionId);
    for (const wp of mission?.waypoints ?? []) {
      const f = new Feature({ geometry: new Point([wp.lon_east_deg, wp.lat_deg]) });
      f.setStyle(waypointStyle(wp.name, wp.kind));
      src.addFeature(f);
    }
  }, [missions, activeMissionId]);

  // --- selected point marker
  useEffect(() => {
    const src = handleRef.current?.markerSource;
    if (!src) return;
    src.clear();
    if (selectedPoint) {
      const f = new Feature({ geometry: new Point([selectedPoint.lon, selectedPoint.lat]) });
      f.setStyle(markerStyle);
      src.addFeature(f);
    }
  }, [selectedPoint]);

  const failed = planetLayers.filter((l) => layers[l.id]?.visible && layers[l.id]?.status === "error");

  return (
    <div className="map-wrap">
      <div ref={targetRef} className="map-target" data-testid="mars-map" aria-label="Map of Mars" />
      <MapControls />
      {mapReady && <TerrainOverlay />}
      {mapReady && <RouteOverlay />}
      <MapLegend />
      {failed.length > 0 && (
        <div className="map-error" role="alert">
          {failed.map((l) => (
            <div key={l.id} className="map-error__row">
              <span>
                <strong>{l.name}</strong> could not be loaded: {layers[l.id]?.error}
              </span>
              <button className="btn btn--small" onClick={() => useAppStore.getState().retryLayer(l.id)}>
                Retry
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
