import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { formatLat, formatLon } from "../../config/marsProjection";
import { describeError } from "../../services/api";
import {
  DEFAULT_RADIUS_M,
  buildTerrainMesh,
  loadTerrainPatch,
  rampColor,
  type TerrainPatch,
} from "../../services/localTerrainService";
import { useAppStore } from "../../store/useAppStore";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "unavailable"; code: string; message: string }
  | { status: "error"; message: string }
  | { status: "ready"; patch: TerrainPatch };

const RADII_KM = [10, 20, 50, 100, 200, 500];
const fmtM = (m: number) => (m >= 1000 ? `${(m / 1000).toFixed(m >= 10_000 ? 0 : 1)} km` : `${Math.round(m)} m`);

/**
 * Click-to-explore local 3D terrain: a mesh built from a real DEM patch around the selected
 * point (GET /terrain/patch/). Compact preview in the point panel, "Expand" for a large view.
 * Without a covering DEM it says "3D TERRAIN UNAVAILABLE" — no synthetic terrain is ever drawn.
 */
export default function LocalTerrain3D() {
  const planet = useAppStore((s) => s.planet);
  const point = useAppStore((s) => s.selectedPoint);
  const lonMode = useAppStore((s) => s.settings.lonMode);
  const [radiusM, setRadiusM] = useState(DEFAULT_RADIUS_M);
  const [exaggeration, setExaggeration] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const [state, setState] = useState<State>({ status: "idle" });

  // --- load the patch (old requests are cancelled when the point or radius changes)
  useEffect(() => {
    if (!point) return setState({ status: "idle" });
    const ctrl = new AbortController();
    setState({ status: "loading" });
    loadTerrainPatch(planet, point.lon, point.lat, { radiusM, signal: ctrl.signal })
      .then((r) => {
        if (ctrl.signal.aborted) return;
        setState(r.status === "OK" ? { status: "ready", patch: r.patch } : { status: "unavailable", code: r.code, message: r.message });
      })
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted) setState({ status: "error", message: describeError(err) });
      });
    return () => ctrl.abort();
  }, [planet, point?.lon, point?.lat, radiusM]);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setExpanded(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  if (!point) return null;

  return (
    <section className={`lt3d ${expanded ? "lt3d--expanded" : ""}`} data-testid="local-terrain-3d" aria-label="Local 3D terrain">
      <div className="lt3d__head">
        <span className="lt3d__title">LOCAL 3D TERRAIN</span>
        <span className="mono muted">
          {formatLat(point.lat, 3)} {formatLon(point.lon, lonMode, 3)}
        </span>
        {state.status === "ready" && (
          <button className="btn btn--small btn--ghost" onClick={() => setExpanded(!expanded)}>
            {expanded ? "Close" : "Expand"}
          </button>
        )}
      </div>
      {state.status === "loading" && <div className="lt3d__msg">Loading DEM patch…</div>}
      {state.status === "error" && <div className="lt3d__msg error-text">Could not load terrain: {state.message}</div>}
      {state.status === "unavailable" && (
        <div className="lt3d__msg lt3d__unavailable" role="status">
          <strong>3D TERRAIN UNAVAILABLE</strong>
          <div>{state.message}</div>
          <div className="muted small">No elevation model is shown instead: imagery colours are not elevations.</div>
        </div>
      )}
      {state.status === "ready" && (
        <TerrainScene
          patch={state.patch}
          exaggeration={exaggeration}
          expanded={expanded}
          controls={
            <div className="lt3d__controls">
              <label className="lt3d__ctl" title="Radius of the patch around the point">
                Radius
                <select value={radiusM} onChange={(e) => setRadiusM(Number(e.target.value))}>
                  {RADII_KM.map((r) => (
                    <option key={r} value={r * 1000}>
                      {r} km
                    </option>
                  ))}
                </select>
              </label>
              <label className="lt3d__ctl" title="Visual aid only: stretches heights on screen; values and legend stay true elevations">
                Vertical exaggeration {exaggeration.toFixed(1)}× <span className="muted">(visual only)</span>
                <input type="range" min={0.5} max={20} step={0.5} value={exaggeration} onChange={(e) => setExaggeration(Number(e.target.value))} />
              </label>
            </div>
          }
        />
      )}
    </section>
  );
}

function TerrainScene({
  patch,
  exaggeration,
  expanded,
  controls,
}: {
  patch: TerrainPatch;
  exaggeration: number;
  expanded: boolean;
  controls: React.ReactNode;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const arrowRef = useRef<HTMLDivElement>(null);
  const api = useRef<{ setExaggeration: (e: number) => void; reset: () => void; northUp: () => void } | null>(null);
  const [webgl, setWebgl] = useState(true);
  const [triangles, setTriangles] = useState({ valid: 0, skipped: 0 });

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setWebgl(false);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    host.appendChild(renderer.domElement);
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(40, 1, 0.001, 50);
    const home = new THREE.Vector3(0, 0.75, 0.95); // from the south, looking north
    camera.position.copy(home);

    const geom = new THREE.BufferGeometry();
    const build = (ex: number) => {
      const m = buildTerrainMesh(patch, ex);
      geom.setAttribute("position", new THREE.BufferAttribute(m.positions, 3));
      geom.setAttribute("color", new THREE.BufferAttribute(m.colors, 3));
      geom.setIndex(new THREE.BufferAttribute(m.indices, 1));
      geom.computeVertexNormals();
      geom.computeBoundingSphere();
      setTriangles({ valid: m.validTriangles, skipped: m.skippedTriangles });
    };
    build(exaggeration);
    const mat = new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide });
    scene.add(new THREE.Mesh(geom, mat));
    scene.add(new THREE.AmbientLight(0xffffff, 0.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.4);
    sun.position.set(-1, 1.2, -0.6); // NW illumination, cartographic convention (illustrative)
    scene.add(sun);
    // patch outline at mean elevation, for scale
    const half = 0.5;
    const frame = new THREE.LineLoop(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-half, 0, -half),
        new THREE.Vector3(half, 0, -half),
        new THREE.Vector3(half, 0, half),
        new THREE.Vector3(-half, 0, half),
      ]),
      new THREE.LineBasicMaterial({ color: 0x9aa3ad, transparent: true, opacity: 0.35 }),
    );
    scene.add(frame);

    const ctl = new OrbitControls(camera, renderer.domElement);
    ctl.enableDamping = true;
    ctl.minDistance = 0.15;
    ctl.maxDistance = 4;
    ctl.maxPolarAngle = Math.PI / 2 - 0.02;
    ctl.screenSpacePanning = false;

    const resize = () => {
      const w = host.clientWidth || 1;
      const h = host.clientHeight || 1;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = "100%";
      renderer.domElement.style.height = "100%";
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    resize();
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (document.hidden) return;
      ctl.update();
      if (arrowRef.current) arrowRef.current.style.transform = `rotate(${ctl.getAzimuthalAngle()}rad)`;
      renderer.render(scene, camera);
    };
    loop();

    api.current = {
      setExaggeration: build,
      reset: () => {
        camera.position.copy(home);
        ctl.target.set(0, 0, 0);
      },
      northUp: () => {
        const d = camera.position.distanceTo(ctl.target);
        const el = Math.asin(Math.min(1, (camera.position.y - ctl.target.y) / d));
        camera.position.set(ctl.target.x, ctl.target.y + d * Math.sin(el), ctl.target.z + d * Math.cos(el));
      },
    };
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      ctl.dispose();
      geom.dispose();
      mat.dispose();
      frame.geometry.dispose();
      renderer.dispose();
      renderer.domElement.remove();
      api.current = null;
    };
  }, [patch]);

  useEffect(() => {
    api.current?.setExaggeration(exaggeration);
  }, [exaggeration]);

  const s = patch.statistics;
  const ds = patch.dataset;
  const gradient = [0, 0.25, 0.5, 0.75, 1].map((t) => `rgb(${rampColor(t).map((v) => Math.round(v * 255)).join(",")}) ${t * 100}%`).join(", ");

  return (
    <div className="lt3d__body">
      <div className={`lt3d__view ${expanded ? "lt3d__view--big" : ""}`}>
        <div ref={hostRef} className="lt3d__host" aria-label="3D terrain mesh; drag to rotate, right-drag to pan, wheel to zoom" />
        {!webgl && <div className="lt3d__msg error-text">WebGL is not available; the 3D terrain cannot be drawn.</div>}
        <div className="lt3d__north" title="North arrow">
          <div ref={arrowRef} className="lt3d__arrow">
            ▲<span>N</span>
          </div>
        </div>
        <div className="lt3d__buttons">
          <button className="map-btn map-btn--text" onClick={() => api.current?.reset()} title="Reset view">
            RESET
          </button>
          <button className="map-btn map-btn--text" onClick={() => api.current?.northUp()} title="Rotate so north is up">
            NORTH
          </button>
        </div>
      </div>
      {controls}
      <div className="lt3d__legend">
        <div className="lt3d__bar" style={{ background: `linear-gradient(to right, ${gradient})` }} />
        <div className="lt3d__barlabels mono">
          <span>
            {Math.round(s.min)} {ds.units === "meter" ? "m" : ds.units}
          </span>
          <span>colour = elevation</span>
          <span>
            {Math.round(s.max)} {ds.units === "meter" ? "m" : ds.units}
          </span>
        </div>
      </div>
      <dl className="lt3d__meta">
        <dt>DEM</dt>
        <dd>
          {ds.name} — {ds.instrument} ({ds.product_id})
        </dd>
        <dt>Resolution</dt>
        <dd>
          native {fmtM(ds.native_resolution_m)}; grid {patch.grid.width}×{patch.grid.height} ({patch.grid.native_cells_across} native cells across)
        </dd>
        <dt>Patch</dt>
        <dd>
          radius {fmtM(patch.radius_m)}
          {patch.radiusAdjusted && (
            <span className="warn-text"> (enlarged from {fmtM(patch.requestedRadiusM)}: the DEM is too coarse for a smaller patch)</span>
          )}
        </dd>
        <dt>Relief</dt>
        <dd>
          {Math.round(s.relief)} m (mean {Math.round(s.mean)} m)
        </dd>
        <dt>Datum</dt>
        <dd>{ds.vertical_datum}</dd>
        <dt>NoData</dt>
        <dd className={s.nodata_fraction > 0 ? "warn-text" : ""}>
          {(s.nodata_fraction * 100).toFixed(1)}% {s.nodata_fraction > 0 ? `— ${triangles.skipped} triangles left empty` : ""}
        </dd>
        <dt>Use</dt>
        <dd className={patch.suitability === "REGIONAL_OVERVIEW_ONLY" ? "warn-text" : ""}>
          {patch.suitability === "REGIONAL_OVERVIEW_ONLY"
            ? "Regional overview only — far too coarse for site or traverse planning"
            : patch.suitability === "SITE_RECONNAISSANCE"
              ? "Site reconnaissance"
              : "Detailed study"}
        </dd>
        <dt>Source</dt>
        <dd>
          {ds.source}
          {ds.license ? ` · ${ds.license}` : ""}
        </dd>
      </dl>
    </div>
  );
}
