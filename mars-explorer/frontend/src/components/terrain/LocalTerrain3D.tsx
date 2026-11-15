import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { formatLat, formatLon } from "../../config/marsProjection";
import { describeError } from "../../services/api";
import {
  buildTerrainMesh,
  loadTerrainPatch,
  rampColor,
  type TerrainPatch,
} from "../../services/localTerrainService";
import { routeOnPatch } from "../../services/route3DService";
import { deviceHints, meshDimensionFor } from "../../services/terrainMeshService";
import { useAppStore } from "../../store/useAppStore";

type State =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "unavailable"; code: string; message: string }
  | { status: "error"; message: string }
  | { status: "ready"; patch: TerrainPatch };

const RADII_KM = [0.25, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500];
/** Vertical exaggeration steps (visualisation only; never used for any calculation). */
export const EXAGGERATIONS = [1, 1.5, 2, 5];
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
  const [radiusM, setRadiusM] = useState<number | "native">("native");
  const [datasetId, setDatasetId] = useState<number | null>(null);
  const product = useAppStore((s) => s.terrainProduct);
  const [exaggeration, setExaggeration] = useState(1);
  const layout = useAppStore((s) => s.terrainView);
  const setLayout = useAppStore((s) => s.setTerrainView);
  const expanded = layout !== "panel";
  const [state, setState] = useState<State>({ status: "idle" });

  // --- load the patch (old requests are cancelled when the point or radius changes)
  useEffect(() => {
    if (!point) return setState({ status: "idle" });
    const ctrl = new AbortController();
    setState({ status: "loading" });
    loadTerrainPatch(planet, point.lon, point.lat, {
      radiusM,
      source: "auto",
      datasetId: datasetId ?? undefined,
      product: datasetId ? undefined : (product ?? undefined),
      maxDimension: meshDimensionFor(deviceHints()),
      signal: ctrl.signal,
    })
      .then((r) => {
        if (ctrl.signal.aborted) return;
        setState(r.status === "OK" ? { status: "ready", patch: r.patch } : { status: "unavailable", code: r.code, message: r.message });
      })
      .catch((err: unknown) => {
        if (!ctrl.signal.aborted) setState({ status: "error", message: describeError(err) });
      });
    return () => ctrl.abort();
  }, [planet, point?.lon, point?.lat, radiusM, datasetId, product]);

  // A whole-route view asks for a radius that covers the route.
  const radiusRequest = useAppStore((s) => s.terrainRadiusRequest);
  useEffect(() => {
    if (radiusRequest) setRadiusM(radiusRequest.radiusM);
  }, [radiusRequest]);

  // A new point starts again from the best available DEM.
  useEffect(() => setDatasetId(null), [planet, point?.lon, point?.lat]);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setLayout("panel");
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded, setLayout]);

  // Outline the patch on the 2D map so the 3D scene can be located on the map.
  const setPatchBBox = useAppStore((s) => s.setTerrainPatchBBox);
  useEffect(() => {
    setPatchBBox(state.status === "ready" ? state.patch.bbox : null);
  }, [state, setPatchBBox]);
  useEffect(() => () => setPatchBBox(null), [setPatchBBox]);

  if (!point) return null;

  return (
    <section className={`lt3d ${layout === "expanded" ? "lt3d--expanded" : layout === "split" ? "lt3d--split" : ""}`} data-testid="local-terrain-3d" aria-label="Local 3D terrain">
      <div className="lt3d__head">
        <span className="lt3d__title">LOCAL 3D TERRAIN</span>
        <span className="mono muted">
          {formatLat(point.lat, 3)} {formatLon(point.lon, lonMode, 3)}
        </span>
        {state.status === "ready" && (
          <span className="lt3d__layout">
            {layout !== "split" && (
              <button className="btn btn--small btn--ghost" onClick={() => setLayout("split")} title="3D on the right, the 2D map stays visible with the patch outlined">
                2D | 3D
              </button>
            )}
            <button className="btn btn--small btn--ghost" onClick={() => setLayout(expanded ? "panel" : "expanded")}>
              {expanded ? "Close" : "Expand"}
            </button>
          </span>
        )}
      </div>
      {state.status === "loading" && (
        <div className="lt3d__msg" role="status">
          Searching elevation data and reading the DEM window… <span className="muted small">(a first read of a remote DTM can take 10–30 s)</span>
        </div>
      )}
      {state.status === "error" && <div className="lt3d__msg error-text">Could not load terrain: {state.message}</div>}
      {state.status === "unavailable" && (
        <div className="lt3d__msg lt3d__unavailable" role="status">
          <strong>LOCAL 3D TERRAIN UNAVAILABLE</strong>
          <div>{state.code === "DEM_NOT_AVAILABLE" ? "No validated elevation dataset covers this location." : state.message}</div>
          <div className="muted small">The available imagery can still be inspected. No elevation model is shown instead: imagery colours are not elevations.</div>
        </div>
      )}
      {state.status === "ready" && (state.patch.data_warnings?.length ?? 0) > 0 && (
        <div className="lt3d__warn" role="alert" data-testid="terrain-data-warnings">
          {state.patch.data_warnings!.map((w) => (
            <div key={w}>{w}</div>
          ))}
          {state.patch.extent && (
            <div className="small">
              DEM cell {fmtM(state.patch.extent.native_cell_spacing_m)} · sample spacing {fmtM(state.patch.extent.effective_sample_spacing_m)} · area shown radius{" "}
              {fmtM(state.patch.extent.actual_radius_m)} · {state.patch.terrain_suitability?.replaceAll("_", " ")}
            </div>
          )}
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
                <select value={radiusM} onChange={(e) => setRadiusM(e.target.value === "native" ? "native" : Number(e.target.value))}>
                  <option value="native">DEM native resolution</option>
                  {RADII_KM.map((r) => (
                    <option key={r} value={r * 1000}>
                      {r < 1 ? `${r * 1000} m` : `${r} km`}
                    </option>
                  ))}
                </select>
              </label>
              {(state.patch.alternatives?.length ?? 0) > 0 && (
                <label className="lt3d__ctl" title="Other validated DEMs covering this point">
                  DEM
                  <select value={datasetId ?? state.patch.dataset.id} onChange={(e) => setDatasetId(Number(e.target.value))}>
                    <option value={state.patch.dataset.id}>
                      {state.patch.dataset.instrument} · {fmtM(state.patch.dataset.native_resolution_m)}
                    </option>
                    {state.patch.alternatives!.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.instrument} · {a.resolution_meters ? fmtM(a.resolution_meters) : "resolution not stated"}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="lt3d__ctl" role="group" aria-label="Vertical exaggeration">
                <span>
                  VERTICAL EXAGGERATION: {exaggeration.toFixed(1)}x <span className="warn-text">VISUALIZATION ONLY</span>
                </span>
                <span className="lt3d__steps">
                  {EXAGGERATIONS.map((x) => (
                    <button key={x} className={`btn btn--small ${exaggeration === x ? "" : "btn--ghost"}`} aria-pressed={exaggeration === x} onClick={() => setExaggeration(x)}>
                      {x.toFixed(1)}x
                    </button>
                  ))}
                </span>
              </div>
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
  const route = useAppStore((s) => s.routeResult.data);
  const [routeCover, setRouteCover] = useState<{ a: number; b: number } | null>(null);

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
    // Routes (A orange, B blue) drawn on the same grid as the mesh; rebuilt with the exaggeration.
    const routeGroup = new THREE.Group();
    scene.add(routeGroup);
    const clearRoutes = () => {
      for (const o of [...routeGroup.children]) {
        routeGroup.remove(o);
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        (m.material as THREE.Material | undefined)?.dispose();
      }
    };
    const buildRoutes = (ex: number) => {
      clearRoutes();
      if (!route) return setRouteCover(null);
      const cover = { a: 0, b: 0 };
      const draw = (coords: [number, number][] | undefined, color: number, key: "a" | "b") => {
        if (!coords?.length) return;
        const r3 = routeOnPatch(patch, coords, ex);
        cover[key] = r3.insideFraction;
        for (const part of r3.parts) {
          const g = new THREE.BufferGeometry();
          g.setAttribute("position", new THREE.BufferAttribute(part, 3));
          routeGroup.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color, depthTest: true })));
        }
        for (const [pt, c] of [[r3.start, 0x6fbf73], [r3.end, 0xef5a4c]] as const) {
          if (key !== "a" || !pt) continue;
          const m = new THREE.Mesh(new THREE.SphereGeometry(0.008, 12, 8), new THREE.MeshBasicMaterial({ color: c }));
          m.position.set(pt[0], pt[1], pt[2]);
          routeGroup.add(m);
        }
      };
      draw(route.alternative_route?.geometry.coordinates, 0x5fb3d9, "b");
      draw(route.route.geometry.coordinates, 0xff8c2e, "a");
      setRouteCover(cover);
    };
    const build = (ex: number) => {
      buildRoutes(ex);
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
      clearRoutes();
      geom.dispose();
      mat.dispose();
      frame.geometry.dispose();
      renderer.dispose();
      // dispose() frees buffers and textures but keeps the WebGL context; release it explicitly so
      // repeated view switches never pile up contexts (browsers cap them at about 16).
      renderer.forceContextLoss();
      renderer.domElement.remove();
      api.current = null;
    };
  }, [patch, route]);

  useEffect(() => {
    api.current?.setExaggeration(exaggeration);
  }, [exaggeration]);

  const s = patch.statistics;
  const ds = patch.dataset;
  const gradient = [0, 0.25, 0.5, 0.75, 1].map((t) => `rgb(${rampColor(t).map((v) => Math.round(v * 255)).join(",")}) ${t * 100}%`).join(", ");

  return (
    <div className="lt3d__body">
      {route && routeCover && routeCover.a === 0 && routeCover.b === 0 && (
        <div className="hint small lt3d__routehint" data-testid="route-3d-status">SELECTED TERRAIN AREA DOES NOT INTERSECT THE ACTIVE ROUTE</div>
      )}
      {route && routeCover && (routeCover.a > 0 || routeCover.b > 0) && (
        <div className="hint small lt3d__routehint" data-testid="route-3d-status">
          <span style={{ color: "#ff8c2e" }}>Route A</span> {(routeCover.a * 100).toFixed(0)}% inside this patch
          {route.alternative_route ? (
            <>
              {" · "}
              <span style={{ color: "#5fb3d9" }}>Route B</span> {(routeCover.b * 100).toFixed(0)}%
            </>
          ) : null}{" "}
          · heights from the terrain shown
        </div>
      )}
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
        <dt>Accuracy</dt>
        <dd>{ds.effective_accuracy ?? "NOT_DOCUMENTED"} — post spacing is not accuracy</dd>
        <dt>Access</dt>
        <dd>
          {ds.access === "REMOTE_COG" ? "Remote: window read from the provider's Cloud-Optimized GeoTIFF (nothing downloaded in bulk)" : "Local file"}
          {ds.quality_status && ds.quality_status !== "NOT_DOCUMENTED" ? ` · provider quality: ${ds.quality_status}` : ""}
          {patch.selection?.skipped_products?.length ? (
            <span className="warn-text"> · {patch.selection.skipped_products.length} finer product(s) could not be read and were skipped</span>
          ) : null}
        </dd>
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
          {ds.source_url ? (
            <a href={ds.source_url} target="_blank" rel="noreferrer">
              {ds.source}
            </a>
          ) : (
            ds.source
          )}
          {ds.license ? ` · ${ds.license}` : ""}
        </dd>
      </dl>
    </div>
  );
}
