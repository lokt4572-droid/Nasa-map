/**
 * Cesium scenes for planetary bodies: configuration, status and viewer lifecycle.
 *
 * Mars and Moon use Cesium's official global 3D Tiles (Cesium ion assets). They are STREAMED
 * VISUALISATION DATA under the Cesium ion terms: this app never downloads, caches or
 * redistributes them, and never uses them as an analytical DEM (analysis reads the original
 * NASA/USGS rasters on the backend).
 *
 * Ellipsoid handling: the official pattern sets `Cesium.Ellipsoid.default` before the Viewer
 * is created. That is a global, so it is set when a scene is created and restored to WGS 84
 * when the scene is destroyed. Only one Cesium viewer is ever alive (each scene is a keyed
 * React component that destroys its viewer on unmount), so no scene sees another body's shape.
 */
import type { PlanetId } from "../../config/planetRegistry";

export type CesiumBodyId = "MARS" | "MOON";

export interface CesiumBodyConfig {
  planet: CesiumBodyId;
  /** Cesium ion asset id of the global 3D Tiles (verified against cesium.com on 2026-11-15). */
  assetId: number;
  ellipsoid: "MARS" | "MOON";
  crs: string;
  docsUrl: string;
  /** Documented approximate resolutions — not uniform over the body. */
  resolutions: { area: string; imagery: string; terrain: string }[];
  sources: string[];
  provenanceNotice: string | null;
  attribution: string;
}

export const CESIUM_BODIES: Record<CesiumBodyId, CesiumBodyConfig> = {
  MARS: {
    planet: "MARS",
    assetId: 3644333,
    ellipsoid: "MARS",
    crs: "IAU_2015:49901",
    docsUrl: "https://cesium.com/platform/cesium-ion/content/cesium-mars/",
    resolutions: [
      { area: "Global", imagery: "≈ 232 m", terrain: "≈ 200 m" },
      { area: "Jezero crater", imagery: "≈ 6 m", terrain: "≈ 20 m" },
      { area: "Gale crater", imagery: "≈ 0.25 m", terrain: "≈ 1 m" },
    ],
    sources: [
      "Mars Viking Colorized Global Mosaic 232 m",
      "Mars MGS MOLA – MEX HRSC Blended DEM Global 200 m",
      "CTX orthoimage and Mars 2020 TRN CTX DTM mosaic (Jezero)",
      "MSL Gale merged orthophoto mosaic 25 cm and merged DEM 1 m (Gale)",
    ],
    provenanceNotice:
      "Colour in the Jezero and Gale high-resolution areas is ESTIMATED: the red channel comes from the grayscale image, green and blue are derived from low-resolution colour ratios, and pixels without data were filled. It is not verified natural colour.",
    attribution: "Cesium Mars — data: NASA and the USGS Astrogeology Science Center; streamed by Cesium ion",
  },
  MOON: {
    planet: "MOON",
    assetId: 2684829,
    ellipsoid: "MOON",
    crs: "NOT_DOCUMENTED by Cesium (lunar sphere, radius 1737.4 km)",
    docsUrl: "https://cesium.com/platform/cesium-ion/content/cesium-moon/",
    resolutions: [
      { area: "60°N – 60°S", imagery: "≈ 100 m", terrain: "≈ 59 m" },
      { area: "Poles", imagery: "≈ 100 m (1 m LROC NAC at 85.5°–90°)", terrain: "≈ 60 m, down to ≈ 5 m at 87.5°–90°" },
    ],
    sources: [
      "LRO LROC WAC Global Morphology Mosaic 100 m",
      "SELENE/Kaguya TC DEM merge 60°N–60°S 59 m",
      "LOLA gridded polar data",
      "LROC NAC polar images",
    ],
    provenanceNotice: null,
    attribution: "Cesium Moon — data: NASA and the USGS Astrogeology Science Center; streamed by Cesium ion",
  },
};

export function cesiumBodyFor(planet: PlanetId): CesiumBodyConfig | null {
  return planet === "MARS" || planet === "MOON" ? CESIUM_BODIES[planet] : null;
}

export type CesiumStatus = "REQUIRES_USER_CONFIGURATION" | "CONFIGURED_NOT_VERIFIED";

/** Pure status from the token only. A present token is never reported as "working". */
export function cesiumStatus(token: string | undefined): { status: CesiumStatus; tokenPresent: boolean; message: string } {
  const present = !!(token ?? "").trim();
  return present
    ? {
        status: "CONFIGURED_NOT_VERIFIED",
        tokenPresent: true,
        message: "A Cesium ion token is configured. Whether the asset loads is shown below once the scene has asked Cesium ion.",
      }
    : {
        status: "REQUIRES_USER_CONFIGURATION",
        tokenPresent: false,
        message:
          "Cesium ion is not configured: set VITE_CESIUM_ION_TOKEN in frontend/.env.local and restart the dev server (see docs/SETUP_CESIUM.md). The 2D map and the texture globe work without it.",
      };
}

/** Readable reason for a failed asset request (token wrong, asset not in the account, offline). */
export function describeIonError(err: unknown): string {
  const e = err as { statusCode?: number; message?: string } | null;
  const code = e?.statusCode;
  if (code === 401) return "Cesium ion rejected the token (HTTP 401). Check VITE_CESIUM_ION_TOKEN.";
  if (code === 403 || code === 404)
    return `Cesium ion refused this asset (HTTP ${code}). Add the asset to your ion account (Asset Depot) and allow it for the token.`;
  if (code === 429) return "Cesium ion quota or rate limit reached (HTTP 429).";
  if (typeof navigator !== "undefined" && navigator.onLine === false) return "No network: Cesium ion tiles cannot be streamed offline.";
  return `Cesium ion request failed${code ? ` (HTTP ${code})` : ""}: ${e?.message ?? String(err)}`;
}

type CesiumModule = typeof import("cesium");

let liveViewers = 0;

/** Number of Cesium viewers currently alive (diagnostics; must never exceed 1). */
export function liveCesiumViewers(): number {
  return liveViewers;
}

export interface PlanetViewer {
  viewer: InstanceType<CesiumModule["Viewer"]>;
  ellipsoid: InstanceType<CesiumModule["Ellipsoid"]>;
  /** Destroys the viewer, frees WebGL resources and restores the default ellipsoid. Idempotent. */
  dispose: () => void;
}

/**
 * Viewer for a body with global 3D Tiles, following the official Cesium Mars / Moon pattern:
 * no Earth globe, no Earth imagery, no geocoder, 3D scene mode only.
 */
export function createPlanetViewer(C: CesiumModule, container: HTMLElement, cfg: CesiumBodyConfig, token: string): PlanetViewer {
  const ellipsoid = C.Ellipsoid[cfg.ellipsoid];
  C.Ion.defaultAccessToken = token;
  C.Ellipsoid.default = ellipsoid; // must precede the Viewer (camera, controllers, picking)
  let viewer: InstanceType<CesiumModule["Viewer"]>;
  try {
    viewer = new C.Viewer(container, {
      globe: false, // the tileset is the surface; an Earth globe would interfere
      baseLayer: false,
      baseLayerPicker: false,
      geocoder: false, // geocoding is Earth-only
      sceneModePicker: false, // 2D / Columbus view are not supported for global 3D Tiles
      skyAtmosphere: false, // Earth's atmosphere model does not apply
      animation: false,
      timeline: false,
      navigationHelpButton: false,
      homeButton: true,
      infoBox: false,
      selectionIndicator: false,
      fullscreenButton: false,
    });
  } catch (err) {
    C.Ellipsoid.default = C.Ellipsoid.WGS84;
    throw err;
  }
  liveViewers++;
  let disposed = false;
  return {
    viewer,
    ellipsoid,
    dispose: () => {
      if (disposed) return;
      disposed = true;
      liveViewers--;
      if (!viewer.isDestroyed()) viewer.destroy(); // releases primitives, textures and the WebGL context
      C.Ellipsoid.default = C.Ellipsoid.WGS84;
    },
  };
}
