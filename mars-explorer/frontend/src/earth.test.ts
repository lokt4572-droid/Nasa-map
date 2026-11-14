import { describe, expect, it, vi } from "vitest";

import { parseCoordinates } from "./components/earth/PlaceSearch";
import { globeConfig } from "./components/earth/Globe3D";
import { type GibsLayer, dateAvailable, gibsXyzTemplate, stepDate } from "./services/earthService";
import { GeolocationService } from "./services/geolocationService";
import { useAppStore } from "./store/useAppStore";

// Time domain copied from the live GIBS capabilities for IMERG_Precipitation_Rate (2026-11-14),
// shortened: two intervals with a gap.
const IMERG_TIME: GibsLayer["time"] = {
  default: "2026-11-12",
  intervals: [
    { start: "2000-06-01", end: "2025-10-22", period: "P1D" },
    { start: "2026-05-27", end: "2026-11-12", period: "P1D" },
  ],
  first: "2000-06-01",
  latest: "2026-11-12",
  daily: true,
};

describe("GIBS time handling", () => {
  it("respects gaps in the published time domain", () => {
    expect(dateAvailable(IMERG_TIME, "2025-10-22")).toBe(true);
    expect(dateAvailable(IMERG_TIME, "2026-01-15")).toBe(false);
    expect(dateAvailable(IMERG_TIME, "2026-11-13")).toBe(false); // after latest: not assumed available
  });

  it("steps over gaps and stops at the latest published day", () => {
    expect(stepDate(IMERG_TIME, "2026-05-27", -1)).toBe("2025-10-22");
    expect(stepDate(IMERG_TIME, "2025-10-22", 1)).toBe("2026-05-27");
    expect(stepDate(IMERG_TIME, "2026-11-12", 1)).toBeNull();
  });

  it("builds the XYZ template from the published ResourceURL and date", () => {
    const layer = {
      id: "IMERG_Precipitation_Rate",
      tile_matrix_set: "GoogleMapsCompatible_Level6",
      template: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate/default/{Time}/{TileMatrixSet}/{TileMatrix}/{TileRow}/{TileCol}.png",
      time: IMERG_TIME,
    } as GibsLayer;
    expect(gibsXyzTemplate(layer, "2026-11-12")).toBe(
      "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate/default/2026-11-12/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png",
    );
    expect(() => gibsXyzTemplate(layer, null)).toThrow();
  });
});

describe("coordinate search input", () => {
  it.each([
    ["48.8584, 2.2945", { lat: 48.8584, lon: 2.2945 }],
    ["-33.9 18.4", { lat: -33.9, lon: 18.4 }],
    ["91, 0", null],
    ["Paris", null],
  ])("%s", (text, expected) => {
    expect(parseCoordinates(text)).toEqual(expected);
  });
});

function fakeGeo() {
  const geo = {
    getCurrentPosition: vi.fn(),
    watchPosition: vi.fn(() => 7),
    clearWatch: vi.fn(),
  };
  return geo;
}
const position = (accuracy: number, speed: number | null = null) =>
  ({ coords: { latitude: 55.75, longitude: 37.62, accuracy, altitude: null, altitudeAccuracy: null, speed, heading: null }, timestamp: 1_700_000_000_000 }) as unknown as GeolocationPosition;

describe("geolocation service", () => {
  it("is idle until the user asks and only works on Earth", () => {
    const geo = fakeGeo();
    const svc = new GeolocationService(geo as unknown as Geolocation, () => true);
    expect(svc.snapshot.state).toBe("IDLE");
    expect(geo.getCurrentPosition).not.toHaveBeenCalled();
    expect(() => svc.locateOnce("MARS")).toThrow(/Earth/);
    expect(() => svc.startTracking("MOON")).toThrow(/Earth/);
  });

  it("requests permission, then reports position, accuracy, timestamp", () => {
    const geo = fakeGeo();
    const svc = new GeolocationService(geo as unknown as Geolocation, () => true);
    svc.locateOnce("EARTH");
    expect(svc.snapshot.state).toBe("REQUESTING_PERMISSION");
    const [ok] = geo.getCurrentPosition.mock.calls[0]!;
    (ok as PositionCallback)(position(12, 1.5));
    expect(svc.snapshot).toMatchObject({ state: "LOCATED", poorAccuracy: false });
    expect(svc.snapshot.fix).toMatchObject({ latitude: 55.75, longitude: 37.62, accuracy_m: 12, speed_mps: 1.5, timestamp: 1_700_000_000_000 });
  });

  it("flags poor accuracy and missing speed", () => {
    const geo = fakeGeo();
    const svc = new GeolocationService(geo as unknown as Geolocation, () => true);
    svc.locateOnce("EARTH");
    (geo.getCurrentPosition.mock.calls[0]![0] as PositionCallback)(position(5000, null));
    expect(svc.snapshot.poorAccuracy).toBe(true);
    expect(svc.snapshot.fix?.speed_mps).toBeNull();
  });

  it.each([
    [1, "PERMISSION_DENIED"],
    [2, "POSITION_UNAVAILABLE"],
    [3, "TIMEOUT"],
  ])("maps error code %i to %s", (code, state) => {
    const geo = fakeGeo();
    const svc = new GeolocationService(geo as unknown as Geolocation, () => true);
    svc.locateOnce("EARTH");
    (geo.getCurrentPosition.mock.calls[0]![1] as PositionErrorCallback)({ code, message: "x" } as GeolocationPositionError);
    expect(svc.snapshot.state).toBe(state);
    expect(svc.snapshot.error).toBeTruthy();
  });

  it("handles unsupported browsers and insecure origins", () => {
    const none = new GeolocationService(undefined, () => true);
    none.locateOnce("EARTH");
    expect(none.snapshot.state).toBe("UNSUPPORTED");
    const insecure = new GeolocationService(fakeGeo() as unknown as Geolocation, () => false);
    insecure.locateOnce("EARTH");
    expect(insecure.snapshot.state).toBe("INSECURE_CONTEXT");
  });

  it("tracks only after an explicit start and stops cleanly", () => {
    const geo = fakeGeo();
    const svc = new GeolocationService(geo as unknown as Geolocation, () => true);
    svc.startTracking("EARTH");
    expect(geo.watchPosition).toHaveBeenCalledTimes(1);
    expect(svc.snapshot.tracking).toBe(true);
    svc.stopTracking();
    expect(geo.clearWatch).toHaveBeenCalledWith(7);
    expect(svc.snapshot.tracking).toBe(false);
    svc.reset();
    expect(svc.snapshot).toMatchObject({ state: "IDLE", fix: null });
  });
});

describe("3D globe configuration", () => {
  it("never claims terrain without a token", () => {
    expect(globeConfig(undefined)).toMatchObject({ globe: "AVAILABLE", terrain: "ELLIPSOID_NO_TERRAIN", terrainStatus: "REQUIRES_CESIUM_TERRAIN_CONFIGURATION", tokenPresent: false });
    expect(globeConfig("  ").message).toContain("without 3D TERRAIN");
    // a token only REQUESTS terrain; the project has not verified it
    expect(globeConfig("abc.def")).toMatchObject({ terrain: "CESIUM_WORLD_TERRAIN", terrainStatus: "CONFIGURED_NOT_VERIFIED", tokenPresent: true });
  });
});

describe("Earth mode switching", () => {
  it("opens the Earth Layers section and keeps Mars default otherwise", () => {
    useAppStore.getState().setPlanet("EARTH");
    expect(useAppStore.getState()).toMatchObject({ planet: "EARTH", section: "e-layers", activeLayerId: "" });
    useAppStore.getState().setPlanet("MARS");
    expect(useAppStore.getState().section).toBe("layers");
  });
});
