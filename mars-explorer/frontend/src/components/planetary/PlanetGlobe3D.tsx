import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

import { formatLat, formatLon } from "../../config/marsProjection";
import { textureFor, type PlanetTexture } from "../../config/planetTextures";
import { PLANETS, type PlanetId } from "../../config/planetRegistry";
import {
  buildEllipsoidArrays,
  buildPlanetTexture,
  graticule,
  lonLatToXYZ,
  xyzToLonLat,
  type TextureLevel,
} from "../../services/planetTextureService";
import { useAppStore } from "../../store/useAppStore";

type TexState =
  | { status: "loading"; level: TextureLevel | null }
  | { status: "ready"; level: TextureLevel }
  | { status: "error"; message: string; level: TextureLevel | null };

const START_DISTANCE = 3.4;

/**
 * 3D globe of a body: real ellipsoid (registry radii), equirectangular texture placed by
 * longitude/latitude, drag to rotate, wheel to zoom, click for coordinates. Lighting is
 * illustrative (fixed to the camera), not the real Sun position.
 */
export default function PlanetGlobe3D({ planet }: { planet: PlanetId }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const tex = textureFor(planet);
  const body = PLANETS[planet];
  const [texState, setTexState] = useState<TexState>({ status: "loading", level: null });
  const [picked, setPicked] = useState<{ lon: number; lat: number } | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [lighting, setLighting] = useState(true);
  const [autoRotate, setAutoRotate] = useState(false);
  const [webgl, setWebgl] = useState(true);
  const api = useRef<{
    setGrid: (v: boolean) => void;
    setLighting: (v: boolean) => void;
    setAutoRotate: (v: boolean) => void;
    reset: () => void;
    setTexture: (l: TextureLevel) => void;
  } | null>(null);
  const lonMode = useAppStore((s) => s.settings.lonMode);

  // --- scene lifecycle (one per mounted body)
  useEffect(() => {
    const host = hostRef.current;
    if (!host || !tex) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      setWebgl(false);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);
    renderer.domElement.setAttribute("data-testid", "globe-canvas");

    const a = body.radiusEquatorial;
    const b = body.radiusPolar;
    const mode = tex.latitude;
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 1, 0.01, 100);
    const startDir = new THREE.Vector3(...lonLatToXYZ(body.defaultCenter[0], body.defaultCenter[1], a, b, mode)).normalize();
    camera.position.copy(startDir).multiplyScalar(START_DISTANCE);

    const arr = buildEllipsoidArrays(a, b, mode);
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.BufferAttribute(arr.positions, 3));
    geom.setAttribute("normal", new THREE.BufferAttribute(arr.normals, 3));
    geom.setAttribute("uv", new THREE.BufferAttribute(arr.uvs, 2));
    geom.setIndex(new THREE.BufferAttribute(arr.indices, 1));
    const placeholder = new THREE.Color("#3a3f46");
    const lit = new THREE.MeshLambertMaterial({ color: placeholder });
    const unlit = new THREE.MeshBasicMaterial({ color: placeholder });
    const mesh = new THREE.Mesh<THREE.BufferGeometry, THREE.Material>(geom, lit);
    scene.add(mesh);

    const gridPts: number[] = [];
    for (const line of graticule(a, b, mode)) {
      for (let i = 0; i < line.length - 1; i++) gridPts.push(...line[i]!, ...line[i + 1]!);
    }
    const gridGeom = new THREE.BufferGeometry();
    gridGeom.setAttribute("position", new THREE.Float32BufferAttribute(gridPts, 3));
    const grid = new THREE.LineSegments(gridGeom, new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.22 }));
    scene.add(grid);

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(-1.5, 1, 2.5); // relative to the camera: illustrative lighting only
    camera.add(sun);
    scene.add(camera);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.minDistance = 1.08;
    controls.maxDistance = 8;
    controls.autoRotateSpeed = 0.6;
    const adaptSpeed = () => {
      // Slower rotation when close to the surface.
      controls.rotateSpeed = Math.min(1, Math.max(0.05, (camera.position.length() - 1) * 0.5));
    };
    controls.addEventListener("change", adaptSpeed);
    adaptSpeed();

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
      controls.update();
      renderer.render(scene, camera);
    };
    loop();

    // --- picking
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pick = (ev: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ndc, camera);
      const hit = ray.intersectObject(mesh, false)[0];
      if (!hit) return null;
      const p = mesh.worldToLocal(hit.point.clone());
      return xyzToLonLat(p.x, p.y, p.z, a, b, mode);
    };
    let down: { x: number; y: number } | null = null;
    let moveFrame = 0;
    const onDown = (ev: PointerEvent) => (down = { x: ev.clientX, y: ev.clientY });
    const onUp = (ev: PointerEvent) => {
      if (!down || Math.hypot(ev.clientX - down.x, ev.clientY - down.y) > 4) return;
      const ll = pick(ev);
      setPicked(ll);
      if (ll && planet !== "EARTH" && body.mapCrs) {
        useAppStore.getState().selectPoint({
          lon: ll.lon,
          lat: ll.lat,
          crs: body.mapCrs,
          layerId: useAppStore.getState().activeLayerId,
          pickedAt: new Date().toISOString(),
        });
      }
    };
    const onMove = (ev: PointerEvent) => {
      cancelAnimationFrame(moveFrame);
      moveFrame = requestAnimationFrame(() => useAppStore.getState().setCursor(pick(ev)));
    };
    const onLeave = () => useAppStore.getState().setCursor(null);
    const el = renderer.domElement;
    el.addEventListener("pointerdown", onDown);
    el.addEventListener("pointerup", onUp);
    el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerleave", onLeave);

    let texture: THREE.Texture | null = null;
    api.current = {
      setGrid: (v) => (grid.visible = v),
      setLighting: (v) => (mesh.material = v ? lit : unlit),
      setAutoRotate: (v) => (controls.autoRotate = v),
      reset: () => {
        camera.position.copy(startDir).multiplyScalar(START_DISTANCE);
        controls.target.set(0, 0, 0);
        controls.update();
      },
      setTexture: (level) => {
        const t = new THREE.CanvasTexture(level.canvas as HTMLCanvasElement);
        t.colorSpace = THREE.SRGBColorSpace;
        t.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
        t.minFilter = THREE.LinearMipmapLinearFilter;
        for (const m of [lit, unlit]) {
          m.map = t;
          m.color.set(0xffffff);
          m.needsUpdate = true;
        }
        texture?.dispose();
        texture = t;
      },
    };

    // --- texture: coarse level first, then finer
    const ctrl = new AbortController();
    setTexState({ status: "loading", level: null });
    buildPlanetTexture(
      tex,
      (level) => {
        api.current?.setTexture(level);
        setTexState((s) => (s.status === "error" ? s : { status: "loading", level }));
      },
      ctrl.signal,
      { maxTextureSize: Math.min(4096, renderer.capabilities.maxTextureSize) },
    )
      .then(() => {
        if (ctrl.signal.aborted) return;
        setTexState((s) => (s.level ? { status: "ready", level: s.level } : { status: "error", message: "no texture level could be loaded", level: null }));
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return;
        setTexState((s) => ({ status: "error", message: err instanceof Error ? err.message : String(err), level: s.level }));
      });

    return () => {
      ctrl.abort();
      cancelAnimationFrame(raf);
      cancelAnimationFrame(moveFrame);
      ro.disconnect();
      el.removeEventListener("pointerdown", onDown);
      el.removeEventListener("pointerup", onUp);
      el.removeEventListener("pointermove", onMove);
      el.removeEventListener("pointerleave", onLeave);
      controls.dispose();
      geom.dispose();
      gridGeom.dispose();
      lit.dispose();
      unlit.dispose();
      texture?.dispose();
      renderer.dispose();
      el.remove();
      api.current = null;
      useAppStore.getState().setCursor(null);
    };
  }, [planet]);

  useEffect(() => {
    api.current?.setGrid(showGrid);
  }, [showGrid]);
  useEffect(() => {
    api.current?.setLighting(lighting);
  }, [lighting]);
  useEffect(() => {
    api.current?.setAutoRotate(autoRotate);
  }, [autoRotate]);

  if (!tex) {
    return (
      <div className="globe-wrap globe-wrap--empty" role="status">
        No verified global texture is available for {body.name}; the 3D globe is not offered for this body.
      </div>
    );
  }

  const openIn2D = () => {
    if (!picked) return;
    const st = useAppStore.getState();
    st.setPendingMapCenter({ lon: picked.lon, lat: picked.lat });
    st.setBodyView("MAP");
  };
  const level = texState.level;

  return (
    <div className="globe-wrap" data-testid="planet-globe">
      <div ref={hostRef} className="globe-host" aria-label={`3D globe of ${body.name}`} />
      {!webgl && <div className="map-error">WebGL is not available in this browser; the 3D globe cannot be shown.</div>}
      <div className="globe-panel">
        <div className="globe-panel__title">{body.name} — 3D globe</div>
        <div className="globe-panel__row">
          <label className="check">
            <input type="checkbox" checked={showGrid} onChange={(e) => setShowGrid(e.target.checked)} /> Grid 30°
          </label>
          <label className="check" title="Light fixed to the camera for shape perception; not the real Sun position.">
            <input type="checkbox" checked={lighting} onChange={(e) => setLighting(e.target.checked)} /> Illustrative lighting
          </label>
          <label className="check">
            <input type="checkbox" checked={autoRotate} onChange={(e) => setAutoRotate(e.target.checked)} /> Rotate
          </label>
          <button className="btn btn--small btn--ghost" onClick={() => api.current?.reset()}>
            Reset view
          </button>
        </div>
        <div className="globe-panel__status" data-testid="globe-texture-status">
          {texState.status === "loading" && (level ? `Texture ${level.level} shown; loading finer level…` : "Loading texture…")}
          {texState.status === "ready" && `Texture ${texState.level.width}×${texState.level.height} px (${texState.level.level})`}
          {texState.status === "error" && <span className="error-text">Texture failed: {texState.message}</span>}
          {level && level.tilesMissing > 0 && (
            <span className="warn-text"> · {level.tilesMissing}/{level.tilesTotal} tiles missing (left blank, not filled in)</span>
          )}
        </div>
        {picked && (
          <div className="globe-panel__pick">
            <span className="mono">
              {formatLat(picked.lat, 3)} {formatLon(picked.lon, lonMode, 3)}
            </span>
            {planet !== "EARTH" && (
              <button className="btn btn--small" onClick={openIn2D}>
                Open in 2D map
              </button>
            )}
          </div>
        )}
        <TextureMeta tex={tex} />
      </div>
    </div>
  );
}

function TextureMeta({ tex }: { tex: PlanetTexture }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="globe-meta">
      <button className="map-legend__toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        TEXTURE SOURCE {open ? "▾" : "▸"}
      </button>
      {open && (
        <dl className="globe-meta__list">
          <dt>Dataset</dt>
          <dd>{tex.title}</dd>
          <dt>Instrument</dt>
          <dd>{tex.instrument}</dd>
          <dt>Projection</dt>
          <dd>{tex.projection}</dd>
          <dt>Resolution</dt>
          <dd>
            native {tex.nativeResolution}; on the globe {tex.globeResolution}
          </dd>
          <dt>Date</dt>
          <dd>{tex.date}</dd>
          <dt>Coverage</dt>
          <dd>{tex.coverage}</dd>
          <dt>Attribution</dt>
          <dd>
            <a href={tex.sourceUrl} target="_blank" rel="noreferrer">
              {tex.attribution}
            </a>
          </dd>
          <dt>Notes</dt>
          <dd>{tex.notes}</dd>
        </dl>
      )}
    </div>
  );
}
