/**
 * Earth 2D map (OpenLayers, EPSG:3857).
 *
 * - OpenStreetMap standard tiles: interactive viewing only, attribution always visible,
 *   browser HTTP cache only (no prefetch, no offline download — OSMF tile policy).
 * - NASA GIBS layers: XYZ built from the ResourceURL template published in the live
 *   GetCapabilities (via the backend), with the TIME the user selected inside the
 *   published intervals. maxZoom = the layer's own TileMatrixSet level.
 */
import { useEffect, useRef, useState } from "react";
import Feature from "ol/Feature";
import OlMap from "ol/Map";
import View from "ol/View";
import { defaults as defaultControls } from "ol/control/defaults";
import { LineString, Point } from "ol/geom";
import { circular } from "ol/geom/Polygon";
import TileLayer from "ol/layer/Tile";
import VectorLayer from "ol/layer/Vector";
import { fromLonLat, toLonLat } from "ol/proj";
import { getLength } from "ol/sphere";
import OSM from "ol/source/OSM";
import VectorSource from "ol/source/Vector";
import XYZ from "ol/source/XYZ";
import { Circle as CircleStyle, Fill, Stroke, Style, Text } from "ol/style";

import { formatDistance, normalizeLon180 } from "../../config/marsProjection";
import { type GibsLayer, dateAvailable, gibsXyzTemplate, timeValue } from "../../services/earthService";
import { geolocation } from "../../services/geolocationService";
import { useAppStore } from "../../store/useAppStore";

const markerStyle = new Style({
  image: new CircleStyle({ radius: 7, fill: new Fill({ color: "rgba(229,101,46,0.3)" }), stroke: new Stroke({ color: "#ffb347", width: 2 }) }),
});
const accuracyStyle = new Style({ fill: new Fill({ color: "rgba(95,179,217,0.15)" }), stroke: new Stroke({ color: "#5fb3d9", width: 1.5 }) });
const locationStyle = new Style({
  image: new CircleStyle({ radius: 6, fill: new Fill({ color: "#5fb3d9" }), stroke: new Stroke({ color: "#fff", width: 2 }) }),
});

function measureStyle(label: string) {
  return new Style({
    stroke: new Stroke({ color: "#f2c14e", width: 2, lineDash: [6, 4] }),
    image: new CircleStyle({ radius: 4, fill: new Fill({ color: "#f2c14e" }) }),
    text: new Text({ text: label, placement: "line", font: "bold 12px Inter, sans-serif", fill: new Fill({ color: "#fff" }), stroke: new Stroke({ color: "#000", width: 3 }) }),
  });
}

function gibsSource(layer: GibsLayer, date: string | null): XYZ {
  return new XYZ({
    url: gibsXyzTemplate(layer, date),
    maxZoom: layer.max_zoom ?? 9,
    crossOrigin: "anonymous",
    attributions: `${layer.attribution} — ${layer.title}${date ? ` (${date})` : ""}`,
  });
}

export default function EarthMap() {
  const target = useRef<HTMLDivElement>(null);
  const mapRef = useRef<OlMap | null>(null);
  const baseRef = useRef<TileLayer | null>(null);
  const overlayGroup = useRef(new Map<string, TileLayer>());
  const vec = useRef({ marker: new VectorSource(), measure: new VectorSource(), location: new VectorSource() });
  const [ready, setReady] = useState(false);

  const earth = useAppStore((s) => s.earth);
  const point = useAppStore((s) => s.selectedPoint);

  useEffect(() => {
    const base = new TileLayer({ source: new OSM(), zIndex: 0 });
    baseRef.current = base;
    const map = new OlMap({
      target: target.current ?? undefined,
      view: new View({ center: fromLonLat([0, 20]), zoom: 2, maxZoom: 19 }),
      layers: [
        base,
        new VectorLayer({ source: vec.current.location, zIndex: 200 }),
        new VectorLayer({ source: vec.current.measure, zIndex: 201 }),
        new VectorLayer({ source: vec.current.marker, zIndex: 202 }),
      ],
      controls: defaultControls({ rotate: false, attributionOptions: { collapsible: false } }),
    });
    mapRef.current = map;
    if (import.meta.env.DEV) (window as unknown as { __earthMap?: OlMap }).__earthMap = map;
    const { setCursor, setView } = useAppStore.getState();
    map.on("pointermove", (e) => {
      if (e.dragging) return;
      const [lon, lat] = toLonLat(e.coordinate);
      setCursor({ lon: normalizeLon180(lon!), lat: lat! });
    });
    map.on("moveend", () => {
      const v = map.getView();
      const c = toLonLat(v.getCenter() ?? [0, 0]);
      // Web Mercator m/px at the equator expressed as degrees/px; the shared scale bar then
      // applies N(φ)·cos(φ) on the WGS84 ellipsoid (cos φ is applied there, not here).
      const res = (v.getResolution() ?? 0) / 111_319.49;
      setView({ resolution: res, centerLat: c[1] ?? 0, zoom: v.getZoom() ?? 0 });
    });
    map.on("singleclick", (e) => {
      const [lonRaw, lat] = toLonLat(e.coordinate);
      const lon = normalizeLon180(lonRaw!);
      const st = useAppStore.getState();
      if (st.earth.measure.active) {
        st.setEarth({ measure: { active: true, points: [...st.earth.measure.points, [lon, lat!]] } });
        return;
      }
      st.selectPoint({ lon, lat: lat!, crs: "EPSG:4326", layerId: "", pickedAt: new Date().toISOString() });
    });
    setReady(true);
    const unsub = geolocation.subscribe((g) => {
      const src = vec.current.location;
      src.clear();
      if (!g.fix) return;
      const acc = new Feature(circular([g.fix.longitude, g.fix.latitude], g.fix.accuracy_m, 64).transform("EPSG:4326", "EPSG:3857"));
      acc.setStyle(accuracyStyle);
      const pos = new Feature(new Point(fromLonLat([g.fix.longitude, g.fix.latitude])));
      pos.setStyle(locationStyle);
      src.addFeatures([acc, pos]);
    });
    return () => {
      unsub();
      map.setTarget(undefined);
      mapRef.current = null;
    };
  }, []);

  // Base layer: OSM or a GIBS satellite layer (with its selected date).
  useEffect(() => {
    const base = baseRef.current;
    if (!base) return;
    if (earth.base === "OSM") {
      if (!(base.getSource() instanceof OSM)) base.setSource(new OSM());
      return;
    }
    const layer = earth.gibs.data?.layers.find((l) => l.id === earth.base && l.status === "AVAILABLE");
    if (!layer) return;
    const date = timeValue(layer, earth.dates[layer.id]);
    if (layer.time && date && !dateAvailable(layer.time, date)) return; // never request dates outside the domain
    base.setSource(gibsSource(layer, date ? date.slice(0, 10) : null));
  }, [earth.base, earth.dates, earth.gibs.data]);

  // Overlays.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const wanted = new Set(earth.overlays);
    for (const [id, tl] of overlayGroup.current) {
      if (!wanted.has(id)) {
        map.removeLayer(tl);
        overlayGroup.current.delete(id);
      }
    }
    earth.overlays.forEach((id, i) => {
      const layer = earth.gibs.data?.layers.find((l) => l.id === id && l.status === "AVAILABLE");
      if (!layer) return;
      const date = timeValue(layer, earth.dates[id]);
      let tl = overlayGroup.current.get(id);
      if (!tl) {
        tl = new TileLayer({ zIndex: 10 + i });
        overlayGroup.current.set(id, tl);
        map.addLayer(tl);
      }
      const ok = !layer.time || (date !== null && dateAvailable(layer.time, date));
      tl.setVisible(ok);
      if (ok) {
        const url = gibsXyzTemplate(layer, date);
        if ((tl.getSource() as XYZ | null)?.getUrls()?.[0] !== url) tl.setSource(gibsSource(layer, date));
      }
      tl.setOpacity(earth.overlayOpacity);
    });
  }, [earth.overlays, earth.dates, earth.gibs.data, earth.overlayOpacity]);

  // Selected point marker.
  useEffect(() => {
    const src = vec.current.marker;
    src.clear();
    if (point && point.crs === "EPSG:4326") {
      const f = new Feature(new Point(fromLonLat([point.lon, point.lat])));
      f.setStyle(markerStyle);
      src.addFeature(f);
    }
  }, [point]);

  // Distance measurement (geodesic on the WGS84 sphere used by ol/sphere: radius 6 371 008.8 m).
  useEffect(() => {
    const src = vec.current.measure;
    src.clear();
    const pts = earth.measure.points;
    if (pts.length === 0) return;
    const line = new LineString(pts.map((p) => fromLonLat(p)));
    const len = pts.length > 1 ? getLength(line) : 0;
    const f = new Feature(pts.length > 1 ? line : new Point(fromLonLat(pts[0]!)));
    f.setStyle(measureStyle(pts.length > 1 ? formatDistance(len) : ""));
    src.addFeature(f);
  }, [earth.measure.points]);

  // Fly-to commands (search results, my location).
  useEffect(() => {
    const map = mapRef.current;
    const ft = earth.flyTo;
    if (!map || !ft) return;
    if (ft.bbox) {
      const [w, s, e, n] = ft.bbox;
      map.getView().fit([...fromLonLat([w, s]), ...fromLonLat([e, n])], { duration: 600, maxZoom: 15, padding: [40, 40, 40, 40] });
    } else {
      map.getView().animate({ center: fromLonLat([ft.lon, ft.lat]), zoom: ft.zoom ?? 12, duration: 600 });
    }
  }, [earth.flyTo]);

  return (
    <div className="map-wrap">
      <div ref={target} className="map-target" data-testid="earth-map" aria-label="Map of Earth" />
      {ready && earth.measure.active && (
        <div className="map-error" style={{ borderColor: "var(--warn)", background: "rgba(40,34,14,.95)" }}>
          MEASURE: click points on the map ({earth.measure.points.length} placed). Geodesic distance on a sphere (R = 6 371 km).
        </div>
      )}
    </div>
  );
}
