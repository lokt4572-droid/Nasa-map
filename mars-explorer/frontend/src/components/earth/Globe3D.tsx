/**
 * Earth 3D globe (CesiumJS), loaded lazily.
 *
 * Terrain: Cesium World Terrain when VITE_CESIUM_ION_TOKEN is set. Without a token the globe
 * is a smooth WGS 84 ellipsoid and is labelled "NO TERRAIN" — it never claims relief.
 * Imagery: NASA GIBS (date from the 2D selection) or OpenStreetMap, draped on the surface;
 * GIBS atmosphere/precipitation overlays are 2D imagery on the globe, not a 3D atmosphere model.
 */
import { useEffect, useRef, useState } from "react";

import { formatDistance, formatLat, formatLon } from "../../config/marsProjection";
import { dateAvailable, gibsXyzTemplate } from "../../services/earthService";
import { geolocation } from "../../services/geolocationService";
import { useAppStore } from "../../store/useAppStore";

export type TerrainMode = "CESIUM_WORLD_TERRAIN" | "ELLIPSOID_NO_TERRAIN";

/**
 * The 3D GLOBE (CesiumJS viewer: rotating Earth with imagery) and 3D TERRAIN (real relief from
 * a terrain provider) are separate things. The globe always works; terrain needs Cesium terrain
 * configuration (an ion token for Cesium World Terrain, or a self-hosted terrain tile server).
 * Decided from the token only (pure; unit-tested).
 */
export function globeConfig(token: string | undefined): {
  globe: "AVAILABLE";
  terrain: TerrainMode;
  terrainStatus: "REQUIRES_CESIUM_TERRAIN_CONFIGURATION" | "CONFIGURED_NOT_VERIFIED";
  tokenPresent: boolean;
  message: string;
} {
  const t = (token ?? "").trim();
  if (!t) {
    return {
      globe: "AVAILABLE",
      terrain: "ELLIPSOID_NO_TERRAIN",
      terrainStatus: "REQUIRES_CESIUM_TERRAIN_CONFIGURATION",
      tokenPresent: false,
      message:
        "3D GLOBE without 3D TERRAIN — real relief requires Cesium terrain configuration (VITE_CESIUM_ION_TOKEN in frontend/.env.local, or a self-hosted terrain server). The surface shown is a smooth WGS 84 ellipsoid: no mountains or valleys.",
    };
  }
  return {
    globe: "AVAILABLE",
    terrain: "CESIUM_WORLD_TERRAIN",
    terrainStatus: "CONFIGURED_NOT_VERIFIED",
    tokenPresent: true,
    message: "3D GLOBE with Cesium World Terrain requested via your ion token (not verified by this project; ion plan quotas apply).",
  };
}

const TOKEN = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;

interface Picked {
  lon: number;
  lat: number;
  height: number | null;
}

export default function Globe3D() {
  const container = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<unknown>(null);
  const cesiumRef = useRef<typeof import("cesium") | null>(null);
  const [status, setStatus] = useState<{ state: "loading" | "ready" | "error"; error: string | null }>({ state: "loading", error: null });
  const [picked, setPicked] = useState<Picked | null>(null);
  const [measure, setMeasure] = useState<{ active: boolean; pts: Picked[] }>({ active: false, pts: [] });
  const measureRef = useRef(measure);
  measureRef.current = measure;
  const earth = useAppStore((s) => s.earth);
  const cfg = globeConfig(TOKEN);

  // Create the viewer once.
  useEffect(() => {
    let destroyed = false;
    (async () => {
      try {
        await import("cesium/Build/Cesium/Widgets/widgets.css");
        const C = await import("cesium");
        if (destroyed || !container.current) return;
        cesiumRef.current = C;
        if (cfg.tokenPresent) C.Ion.defaultAccessToken = TOKEN!.trim();
        const viewer = new C.Viewer(container.current, {
          baseLayer: false, // no default ion/Bing imagery; layers are added below
          terrain: cfg.terrain === "CESIUM_WORLD_TERRAIN" ? C.Terrain.fromWorldTerrain() : undefined,
          terrainProvider: cfg.terrain === "ELLIPSOID_NO_TERRAIN" ? new C.EllipsoidTerrainProvider() : undefined,
          geocoder: false, // ion geocoder needs a token; place search lives in the 2D panel
          baseLayerPicker: false,
          animation: false,
          timeline: false,
          navigationHelpButton: false,
          sceneModePicker: true,
          homeButton: true,
          infoBox: false,
          selectionIndicator: false,
        });
        viewerRef.current = viewer;
        viewer.scene.globe.depthTestAgainstTerrain = cfg.terrain === "CESIUM_WORLD_TERRAIN";
        const handler = new C.ScreenSpaceEventHandler(viewer.scene.canvas);
        handler.setInputAction((e: { position: InstanceType<typeof C.Cartesian2> }) => {
          const cart = viewer.scene.pickPosition(e.position) ?? viewer.camera.pickEllipsoid(e.position, viewer.scene.globe.ellipsoid);
          if (!cart) return;
          const carto = C.Cartographic.fromCartesian(cart);
          const height = cfg.terrain === "CESIUM_WORLD_TERRAIN" ? (viewer.scene.globe.getHeight(carto) ?? null) : null;
          const p = { lon: C.Math.toDegrees(carto.longitude), lat: C.Math.toDegrees(carto.latitude), height };
          if (measureRef.current.active) setMeasure((m) => ({ ...m, pts: [...m.pts, p] }));
          else {
            setPicked(p);
            useAppStore.getState().selectPoint({ lon: p.lon, lat: p.lat, crs: "EPSG:4326", layerId: "", pickedAt: new Date().toISOString() });
          }
        }, C.ScreenSpaceEventType.LEFT_CLICK);
        setStatus({ state: "ready", error: null });
      } catch (err) {
        setStatus({ state: "error", error: err instanceof Error ? err.message : String(err) });
      }
    })();
    return () => {
      destroyed = true;
      const v = viewerRef.current as { destroy?: () => void; isDestroyed?: () => boolean } | null;
      if (v?.destroy && !v.isDestroyed?.()) v.destroy();
      viewerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Imagery: base + overlays, following the 2D selection.
  useEffect(() => {
    const C = cesiumRef.current;
    const viewer = viewerRef.current as InstanceType<typeof import("cesium").Viewer> | null;
    if (!C || !viewer || status.state !== "ready") return;
    const layers = viewer.imageryLayers;
    layers.removeAll();
    const gibs = earth.gibs.data?.layers ?? [];
    const addGibs = (id: string, alpha: number) => {
      const l = gibs.find((x) => x.id === id && x.status === "AVAILABLE");
      if (!l) return;
      const date = l.time ? (earth.dates[id] ?? l.time.latest)?.slice(0, 10) ?? null : null;
      if (l.time && (!date || !dateAvailable(l.time, date))) return;
      const provider = new C.UrlTemplateImageryProvider({
        url: gibsXyzTemplate(l, date),
        tilingScheme: new C.WebMercatorTilingScheme(),
        maximumLevel: l.max_zoom ?? 9,
        credit: `${l.attribution} — ${l.title}${date ? ` (${date})` : ""}`,
      });
      layers.addImageryProvider(provider).alpha = alpha;
    };
    if (earth.base === "OSM") {
      layers.addImageryProvider(new C.OpenStreetMapImageryProvider({ url: "https://tile.openstreetmap.org/" }));
    } else addGibs(earth.base, 1);
    earth.overlays.forEach((id) => addGibs(id, earth.overlayOpacity));
  }, [status.state, earth.base, earth.overlays, earth.dates, earth.gibs.data, earth.overlayOpacity]);

  // Markers + measurement line.
  useEffect(() => {
    const C = cesiumRef.current;
    const viewer = viewerRef.current as InstanceType<typeof import("cesium").Viewer> | null;
    if (!C || !viewer || status.state !== "ready") return;
    viewer.entities.removeAll();
    const clamp = cfg.terrain === "CESIUM_WORLD_TERRAIN" ? C.HeightReference.CLAMP_TO_GROUND : C.HeightReference.NONE;
    if (picked) viewer.entities.add({ position: C.Cartesian3.fromDegrees(picked.lon, picked.lat), point: { pixelSize: 10, color: C.Color.ORANGE, heightReference: clamp } });
    const fix = geolocation.snapshot.fix;
    if (fix) viewer.entities.add({ position: C.Cartesian3.fromDegrees(fix.longitude, fix.latitude), point: { pixelSize: 10, color: C.Color.CYAN, heightReference: clamp } });
    if (measure.pts.length > 1) {
      viewer.entities.add({
        polyline: { positions: measure.pts.map((p) => C.Cartesian3.fromDegrees(p.lon, p.lat)), width: 3, material: C.Color.YELLOW, clampToGround: true },
      });
    }
  }, [status.state, picked, measure.pts, cfg.terrain]);

  // Geodesic length on the WGS 84 ellipsoid.
  let measured: number | null = null;
  const C = cesiumRef.current;
  if (C && measure.pts.length > 1) {
    measured = 0;
    for (let i = 1; i < measure.pts.length; i++) {
      const a = measure.pts[i - 1]!;
      const b = measure.pts[i]!;
      measured += new C.EllipsoidGeodesic(C.Cartographic.fromDegrees(a.lon, a.lat), C.Cartographic.fromDegrees(b.lon, b.lat)).surfaceDistance;
    }
  }

  const flyToLocation = () => {
    const viewer = viewerRef.current as InstanceType<typeof import("cesium").Viewer> | null;
    const fix = geolocation.snapshot.fix;
    if (!C || !viewer || !fix) return;
    viewer.camera.flyTo({ destination: C.Cartesian3.fromDegrees(fix.longitude, fix.latitude, 20_000) });
  };

  return (
    <div className="map-wrap">
      <div ref={container} className="map-target globe-target" data-testid="globe-3d" />
      <div className={`globe-banner ${cfg.tokenPresent ? "" : "globe-banner--warn"}`}>
        {cfg.message} Imagery overlays are draped on the surface — not a 3D atmospheric simulation.
      </div>
      {status.state === "loading" && <div className="map-error">Loading CesiumJS…</div>}
      {status.state === "error" && <div className="map-error">3D globe failed: {status.error}. Use the 2D map.</div>}
      <div className="globe-tools">
        <button className="map-btn map-btn--text" onClick={() => useAppStore.getState().setEarth({ view: "2D" })}>
          2D MAP
        </button>
        <button className="map-btn map-btn--text" onClick={flyToLocation} disabled={!geolocation.snapshot.fix} title="Requires MY LOCATION first">
          MY LOCATION
        </button>
        <button className="map-btn map-btn--text" onClick={() => setMeasure((m) => ({ active: !m.active, pts: m.active ? m.pts : [] }))}>
          {measure.active ? "FINISH" : "MEASURE"}
        </button>
      </div>
      {(picked || measured !== null) && (
        <div className="map-legend" style={{ width: 260 }}>
          <div className="map-legend__body" style={{ paddingTop: 8 }}>
            {picked && (
              <div className="mono small">
                {formatLat(picked.lat, 5)} {formatLon(picked.lon, "180", 5)}
                <br />
                Height: {picked.height !== null ? `${picked.height.toFixed(0)} m (Cesium terrain, ellipsoidal)` : "DATA NOT AVAILABLE (no terrain)"}
              </div>
            )}
            {measured !== null && <div className="mono small">Distance: {formatDistance(measured)} (WGS 84 geodesic)</div>}
          </div>
        </div>
      )}
    </div>
  );
}

/** Sidebar section for the 3D globe. */
export function GlobeControls() {
  const view = useAppStore((s) => s.earth.view);
  const setEarth = useAppStore((s) => s.setEarth);
  const cfg = globeConfig(TOKEN);
  return (
    <div className="panel-section">
      <div className="layer-card__actions">
        <button className={`btn btn--small ${view === "2D" ? "" : "btn--ghost"}`} onClick={() => setEarth({ view: "2D" })}>
          2D map
        </button>
        <button className={`btn btn--small ${view === "3D" ? "" : "btn--ghost"}`} onClick={() => setEarth({ view: "3D" })}>
          3D globe
        </button>
      </div>
      <div className="kv">
        <span className="label">3D globe</span>
        <span className="status-chip status-chip--ready">{cfg.globe}</span>
      </div>
      <div className="kv">
        <span className="label">3D terrain</span>
        <span className={`status-chip ${cfg.tokenPresent ? "status-chip--t-no-data" : "status-chip--error"}`}>{cfg.terrainStatus}</span>
      </div>
      <p className="hint small">{cfg.message}</p>
      <p className="hint small">
        Cesium ion tokens are visible to every user of the frontend: use a token restricted to your domain, keep it out of Git
        (frontend/.env.local is ignored). The Community plan is for personal/non-commercial use and has monthly quotas.
      </p>
      <p className="hint small">Imagery and overlays follow the selections in Satellite and Weather. Offline 3D terrain: not implemented (see docs/OFFLINE_MODE.md).</p>
    </div>
  );
}
