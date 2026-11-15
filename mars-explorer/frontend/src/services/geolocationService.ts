/**
 * Browser geolocation for EARTH MODE ONLY.
 *
 * Rules:
 * - never requested automatically: only after the user presses MY LOCATION;
 * - continuous tracking only after a separate explicit action (START TRACKING);
 * - positions are kept in memory only: no history is stored and nothing is sent to the backend;
 * - refuses to run for any body other than Earth.
 */
import type { PlanetId } from "../config/planetRegistry";

export type GeoState =
  | "IDLE"
  | "REQUESTING_PERMISSION"
  | "LOCATING"
  | "LOCATED"
  | "PERMISSION_DENIED"
  | "POSITION_UNAVAILABLE"
  | "TIMEOUT"
  | "UNSUPPORTED"
  | "INSECURE_CONTEXT";

export interface GeoFix {
  latitude: number;
  longitude: number;
  accuracy_m: number;
  altitude_m: number | null;
  altitude_accuracy_m: number | null;
  speed_mps: number | null; // only when the browser reports it
  heading_deg: number | null;
  timestamp: number;
  source: "Browser Geolocation API (device: GPS / Wi-Fi / cell / IP, chosen by the browser)";
}

export interface GeoSnapshot {
  state: GeoState;
  fix: GeoFix | null;
  tracking: boolean;
  error: string | null;
  poorAccuracy: boolean;
}

export const POOR_ACCURACY_M = 1000;

type Listener = (s: GeoSnapshot) => void;

function errorState(code: number): GeoState {
  // GeolocationPositionError codes: 1 PERMISSION_DENIED, 2 POSITION_UNAVAILABLE, 3 TIMEOUT
  return code === 1 ? "PERMISSION_DENIED" : code === 2 ? "POSITION_UNAVAILABLE" : "TIMEOUT";
}

const MESSAGES: Partial<Record<GeoState, string>> = {
  PERMISSION_DENIED: "Location permission was denied. Allow it in the browser's site settings to use MY LOCATION.",
  POSITION_UNAVAILABLE: "The device could not determine a position (GPS/location services off or no signal).",
  TIMEOUT: "Locating took too long. Try again outdoors or with location services enabled.",
  UNSUPPORTED: "This browser does not support the Geolocation API.",
  INSECURE_CONTEXT: "Geolocation requires HTTPS (or localhost). Open the app over a secure origin.",
};

export class GeolocationService {
  private snap: GeoSnapshot = { state: "IDLE", fix: null, tracking: false, error: null, poorAccuracy: false };
  private listeners = new Set<Listener>();
  private watchId: number | null = null;

  constructor(
    private readonly geo: Geolocation | undefined = typeof navigator !== "undefined" ? navigator.geolocation : undefined,
    private readonly secure: () => boolean = () => (typeof window === "undefined" ? true : window.isSecureContext),
  ) {}

  get snapshot(): GeoSnapshot {
    return this.snap;
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    fn(this.snap);
    return () => this.listeners.delete(fn);
  }

  private set(patch: Partial<GeoSnapshot>) {
    this.snap = { ...this.snap, ...patch };
    this.listeners.forEach((l) => l(this.snap));
  }

  private precheck(planet: PlanetId): boolean {
    if (planet !== "EARTH") throw new Error("Browser geolocation is only allowed in Earth mode");
    if (!this.secure()) {
      this.set({ state: "INSECURE_CONTEXT", error: MESSAGES.INSECURE_CONTEXT! });
      return false;
    }
    if (!this.geo) {
      this.set({ state: "UNSUPPORTED", error: MESSAGES.UNSUPPORTED! });
      return false;
    }
    return true;
  }

  private onFix = (p: GeolocationPosition) => {
    const c = p.coords;
    const fix: GeoFix = {
      latitude: c.latitude,
      longitude: c.longitude,
      accuracy_m: c.accuracy,
      altitude_m: c.altitude ?? null,
      altitude_accuracy_m: c.altitudeAccuracy ?? null,
      speed_mps: c.speed !== null && Number.isFinite(c.speed) ? c.speed : null,
      heading_deg: c.heading !== null && Number.isFinite(c.heading) ? c.heading : null,
      timestamp: p.timestamp,
      source: "Browser Geolocation API (device: GPS / Wi-Fi / cell / IP, chosen by the browser)",
    };
    this.set({ state: "LOCATED", fix, error: null, poorAccuracy: c.accuracy > POOR_ACCURACY_M });
  };

  private onError = (e: GeolocationPositionError) => {
    const state = errorState(e.code);
    this.set({ state, error: MESSAGES[state] ?? e.message, tracking: state === "TIMEOUT" ? this.snap.tracking : false });
    if (state === "PERMISSION_DENIED") this.stopTracking();
  };

  /** One-shot fix, after the user pressed MY LOCATION. */
  locateOnce(planet: PlanetId): void {
    if (!this.precheck(planet)) return;
    this.set({ state: "REQUESTING_PERMISSION", error: null });
    // If permission is already granted there is no prompt: show LOCATING right away.
    void this.permissionGranted().then((granted) => {
      if (granted && this.snap.state === "REQUESTING_PERMISSION") this.set({ state: "LOCATING" });
    });
    this.geo!.getCurrentPosition(this.onFix, this.onError, { enableHighAccuracy: true, timeout: 20_000, maximumAge: 0 });
  }

  private async permissionGranted(): Promise<boolean> {
    try {
      const status = await navigator.permissions?.query({ name: "geolocation" as PermissionName });
      return status?.state === "granted";
    } catch {
      return false;
    }
  }

  /** Continuous tracking: a separate explicit user action. */
  startTracking(planet: PlanetId): void {
    if (!this.precheck(planet) || this.watchId !== null) return;
    this.set({ state: "LOCATING", tracking: true, error: null });
    this.watchId = this.geo!.watchPosition(this.onFix, this.onError, { enableHighAccuracy: true, timeout: 30_000, maximumAge: 5_000 });
  }

  stopTracking(): void {
    if (this.watchId !== null && this.geo) this.geo.clearWatch(this.watchId);
    this.watchId = null;
    if (this.snap.tracking) this.set({ tracking: false });
  }

  /** Forget the position (called when leaving Earth mode). */
  reset(): void {
    this.stopTracking();
    this.set({ state: "IDLE", fix: null, error: null, poorAccuracy: false });
  }
}

export const geolocation = new GeolocationService();
