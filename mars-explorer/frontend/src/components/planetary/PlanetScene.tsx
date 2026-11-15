/**
 * Cesium scene for a body with official global 3D Tiles (Mars, Moon). Loaded lazily.
 *
 * One viewer per mount: created once in an effect, destroyed on unmount (the parent keys this
 * component by planet, so switching bodies always destroys the previous viewer first).
 * What is shown is streamed visualisation data — heights read from the scene are picked from
 * render tiles and are labelled as such; measurements come from the DEM endpoints.
 */
import { useEffect, useRef, useState } from "react";

import { formatLat, formatLon } from "../../config/marsProjection";
import { PLANETS } from "../../config/planetRegistry";
import {
  type CesiumBodyConfig,
  cesiumStatus,
  createPlanetViewer,
  describeIonError,
  type PlanetViewer,
} from "../../services/planetary/cesiumSceneService";
import { geodeticToCentric } from "../../services/planetary/planetaryCoordinateService";
import { useAppStore } from "../../store/useAppStore";
import TerrainLoadingOverlay from "./TerrainLoadingOverlay";

const TOKEN = import.meta.env.VITE_CESIUM_ION_TOKEN as string | undefined;

type LoadState =
  | { state: "not-configured" }
  | { state: "loading"; step: string }
  | { state: "ready"; loadMs: number }
  | { state: "error"; error: string };

interface Picked {
  lon: number;
  latGeodetic: number;
  latCentric: number;
  height: number | null;
}

export default function PlanetScene({ cfg }: { cfg: CesiumBodyConfig }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const sceneRef = useRef<PlanetViewer | null>(null);
  const status = cesiumStatus(TOKEN);
  const [load, setLoad] = useState<LoadState>(status.tokenPresent ? { state: "loading", step: "Loading CesiumJS…" } : { state: "not-configured" });
  const [picked, setPicked] = useState<Picked | null>(null);
  const [showSources, setShowSources] = useState(false);
  const lonMode = useAppStore((s) => s.settings.lonMode);
  const body = PLANETS[cfg.planet];

  useEffect(() => {
    if (!status.tokenPresent || !hostRef.current) return;
    let cancelled = false;
    const t0 = performance.now();
    (async () => {
      try {
        await import("cesium/Build/Cesium/Widgets/widgets.css");
        const C = await import("cesium");
        if (cancelled || !hostRef.current) return;
        const scene = createPlanetViewer(C, hostRef.current, cfg, TOKEN!.trim());
        sceneRef.current = scene;
        const { viewer, ellipsoid } = scene;
        setLoad({ state: "loading", step: `Requesting ion asset ${cfg.assetId}…` });
        const tileset = await C.Cesium3DTileset.fromIonAssetId(cfg.assetId);
        if (cancelled) {
          if (!tileset.isDestroyed()) tileset.destroy();
          return;
        }
        viewer.scene.primitives.add(tileset);
        await viewer.zoomTo(tileset);
        if (cancelled) return;
        const shape = { a: ellipsoid.radii.x, b: ellipsoid.radii.z };
        const handler = new C.ScreenSpaceEventHandler(viewer.scene.canvas); // destroyed with the viewer's canvas
        handler.setInputAction((e: { position: InstanceType<typeof C.Cartesian2> }) => {
          // pickPosition returns the rendered surface; outside the body it is undefined.
          const cart = viewer.scene.pickPositionSupported ? viewer.scene.pickPosition(e.position) : undefined;
          if (!cart || !Number.isFinite(cart.x)) return;
          const carto = C.Cartographic.fromCartesian(cart, ellipsoid);
          if (!carto) return;
          const lon = C.Math.toDegrees(carto.longitude);
          const latGeodetic = C.Math.toDegrees(carto.latitude);
          const p: Picked = { lon, latGeodetic, latCentric: geodeticToCentric(latGeodetic, shape), height: Number.isFinite(carto.height) ? carto.height : null };
          setPicked(p);
          if (body.mapCrs) {
            const st = useAppStore.getState();
            st.selectPoint({ lon: p.lon, lat: p.latCentric, crs: body.mapCrs, layerId: st.activeLayerId, pickedAt: new Date().toISOString() });
          }
        }, C.ScreenSpaceEventType.LEFT_CLICK);
        const prevDispose = scene.dispose;
        scene.dispose = () => {
          if (!handler.isDestroyed()) handler.destroy();
          prevDispose();
        };
        setLoad({ state: "ready", loadMs: Math.round(performance.now() - t0) });
      } catch (err) {
        if (!cancelled) setLoad({ state: "error", error: describeIonError(err) });
      }
    })();
    return () => {
      cancelled = true;
      sceneRef.current?.dispose();
      sceneRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg.assetId]);

  const openIn2D = () => {
    if (!picked) return;
    const st = useAppStore.getState();
    st.setPendingMapCenter({ lon: picked.lon, lat: picked.latCentric });
    st.setBodyView("MAP");
  };

  return (
    <div className="globe-wrap" data-testid="planet-scene">
      <div ref={hostRef} className="globe-host globe-target" aria-label={`Cesium 3D scene of ${body.name}`} />
      {load.state === "loading" && <TerrainLoadingOverlay title={`${body.name} 3D Tiles`} detail={load.step} />}
      {load.state === "error" && <TerrainLoadingOverlay tone="error" title="3D TILES NOT AVAILABLE" detail={`${load.error} The 2D map and the texture globe still work.`} />}
      {load.state === "not-configured" && (
        <TerrainLoadingOverlay tone="warn" title="3D TILES: REQUIRES_USER_CONFIGURATION" detail={status.message} />
      )}
      <div className="globe-panel">
        <div className="globe-panel__title">{body.name} — Cesium 3D Tiles</div>
        <div className="globe-panel__row">
          <span className={`status-chip ${load.state === "ready" ? "status-chip--ready" : load.state === "error" ? "status-chip--error" : "status-chip--t-no-data"}`} data-testid="scene-status">
            {load.state === "ready" ? "STREAMING" : load.state === "error" ? "ERROR" : load.state === "loading" ? "LOADING" : "NOT CONFIGURED"}
          </span>
          <span className="mono small">ion asset {cfg.assetId}</span>
          {load.state === "ready" && <span className="mono small">first view {(load.loadMs / 1000).toFixed(1)} s</span>}
        </div>
        <div className="globe-panel__status">
          Visualisation only. Resolution varies by area; this is streamed render data, not the analytical DEM. Ellipsoid: {cfg.ellipsoid}; CRS: {cfg.crs}.
        </div>
        {cfg.provenanceNotice && <div className="globe-panel__status scene-notice">DATA PROVENANCE: {cfg.provenanceNotice}</div>}
        {(load.state === "not-configured" || load.state === "error") && (
          <div className="globe-panel__pick">
            <button className="btn btn--small" onClick={() => useAppStore.getState().setBodyView("GLOBE")}>
              Use texture globe
            </button>
            <button className="btn btn--small btn--ghost" onClick={() => useAppStore.getState().setBodyView("MAP")}>
              2D map
            </button>
          </div>
        )}
        {picked && (
          <div className="globe-panel__pick">
            <span className="mono small">
              {formatLat(picked.latCentric, 4)} {formatLon(picked.lon, lonMode, 4)} (planetocentric)
              <br />
              geodetic lat {picked.latGeodetic.toFixed(4)}°
              {picked.height !== null && (
                <>
                  <br />
                  render-tile height {picked.height.toFixed(0)} m above the ellipsoid (not a DEM value)
                </>
              )}
            </span>
            <button className="btn btn--small" onClick={openIn2D}>
              Open in 2D map
            </button>
          </div>
        )}
        <div className="globe-meta">
          <button className="map-legend__toggle" onClick={() => setShowSources(!showSources)} aria-expanded={showSources}>
            DATA SOURCES AND ATTRIBUTION {showSources ? "▾" : "▸"}
          </button>
          {showSources && (
            <dl className="globe-meta__list">
              {cfg.resolutions.map((r) => (
                <FragmentRow key={r.area} dt={r.area} dd={`imagery ${r.imagery}; terrain ${r.terrain} (documented, approximate)`} />
              ))}
              <FragmentRow dt="Sources" dd={cfg.sources.join("; ")} />
              <FragmentRow dt="Terms" dd="Cesium ion Terms of Service: streaming only — not downloaded, cached offline or redistributed by this app." />
              <dt>Attribution</dt>
              <dd>
                <a href={cfg.docsUrl} target="_blank" rel="noreferrer">
                  {cfg.attribution}
                </a>
              </dd>
            </dl>
          )}
        </div>
      </div>
    </div>
  );
}

function FragmentRow({ dt, dd }: { dt: string; dd: string }) {
  return (
    <>
      <dt>{dt}</dt>
      <dd>{dd}</dd>
    </>
  );
}
