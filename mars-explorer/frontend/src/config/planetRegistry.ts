/**
 * Central registry of celestial bodies (mirror of backend/services/planet_registry.py).
 * Radii are from the PROJ database (pyproj 3.8), checked 2026-11-14. Conflicting values
 * between sources are listed in `conflicts`, never silently merged.
 */
export type PlanetId = "EARTH" | "MARS" | "MOON" | "MERCURY" | "VENUS";

export interface PlanetConfig {
  id: PlanetId;
  name: string;
  category: "terrestrial";
  status: "PRIMARY" | "FULL" | "SCIENTIFIC_VIEWER" | "EXPERIMENTAL";
  radiusEquatorial: number; // metres
  radiusPolar: number; // metres
  defaultCenter: [number, number];
  longitudeConvention: string;
  longitudeRange: string;
  latitudeType: string;
  coordinateSystem: string; // reference CRS (PROJ id)
  mapCrs: string | null; // CRS declared by the map service
  verticalDatum: string;
  projections: string[];
  availableViews: ("2D" | "3D")[];
  layers: string[]; // layer ids from mapLayers.ts
  datasets: string[]; // catalog entries (Data Manager)
  coverage: string;
  browserGeolocationAllowed: boolean;
  conflicts: string[];
}

export const PLANETS: Record<PlanetId, PlanetConfig> = {
  MARS: {
    id: "MARS",
    name: "Mars",
    category: "terrestrial",
    status: "PRIMARY",
    radiusEquatorial: 3_396_190,
    radiusPolar: 3_376_200,
    defaultCenter: [0, 0],
    longitudeConvention: "East-positive",
    longitudeRange: "-180..180 (map); MEGDR products 0..360",
    latitudeType: "Map: as declared by NASA Trek (not stated); MOLA MEGDR: planetocentric",
    coordinateSystem: "ESRI:104905 (GCS_Mars_2000)",
    mapCrs: "urn:ogc:def:crs:EPSG::104905",
    verticalDatum: "MOLA areoid (GMM3, mgm1025) for MEGDR topography",
    projections: ["Equirectangular", "Simple Cylindrical", "Polar Stereographic"],
    availableViews: ["2D"],
    layers: ["mola-global-clrshade", "mola-hrsc-blend-clrshade", "jezero-ctx-ortho", "jezero-hirise-ortho"],
    datasets: ["mola-megdr", "hirise-dtm"],
    coverage: "Global MOLA; HiRISE/CTX regional (Jezero).",
    browserGeolocationAllowed: false,
    conflicts: ["MEGDR uses a 3 396 000 m sphere; the Trek map uses the 3 396 190 m Mars 2000 ellipsoid."],
  },
  EARTH: {
    id: "EARTH",
    name: "Earth",
    category: "terrestrial",
    status: "FULL",
    radiusEquatorial: 6_378_137,
    radiusPolar: 6_356_752.314245179,
    defaultCenter: [0, 20],
    longitudeConvention: "East-positive",
    longitudeRange: "-180..180",
    latitudeType: "Geodetic (WGS 84)",
    coordinateSystem: "EPSG:4326 (WGS 84)",
    mapCrs: "EPSG:3857",
    verticalDatum: "Product-specific: Copernicus DEM = EGM2008; GEBCO = mean sea level",
    projections: ["EPSG:4326", "EPSG:3857"],
    availableViews: ["2D", "3D"],
    layers: [],
    datasets: ["copernicus-dem", "gebco-2026"],
    coverage: "Global imagery (NASA GIBS, OpenStreetMap); DEM only where downloaded.",
    browserGeolocationAllowed: true,
    conflicts: [],
  },
  MOON: {
    id: "MOON",
    name: "Moon",
    category: "terrestrial",
    status: "SCIENTIFIC_VIEWER",
    radiusEquatorial: 1_737_400,
    radiusPolar: 1_737_400,
    defaultCenter: [0, 0],
    longitudeConvention: "East-positive",
    longitudeRange: "-180..180 (Trek map)",
    latitudeType: "Planetocentric",
    coordinateSystem: "ESRI:104903 (GCS_Moon_2000, sphere)",
    mapCrs: "urn:ogc:def:crs:EPSG::104903",
    verticalDatum: "Product-specific (GLD100: not stated on the LROC product page)",
    projections: ["Equirectangular", "Polar Stereographic"],
    availableViews: ["2D"],
    layers: ["moon-lroc-wac-mosaic", "moon-lola-clrshade"],
    datasets: ["lroc-gld100", "lola-dem"],
    coverage: "WAC mosaic global. GLD100 DEM 79°S–79°N (98.2 %): poles need LOLA.",
    browserGeolocationAllowed: false,
    conflicts: [],
  },
  MERCURY: {
    id: "MERCURY",
    name: "Mercury",
    category: "terrestrial",
    status: "SCIENTIFIC_VIEWER",
    radiusEquatorial: 2_440_530,
    radiusPolar: 2_440_530,
    defaultCenter: [0, 0],
    longitudeConvention: "East-positive",
    longitudeRange: "-180..180 (Trek map); USGS DEM 0..360",
    latitudeType: "Planetocentric",
    coordinateSystem: "IAU_2015:19900 (Mercury 2015 sphere)",
    mapCrs: "urn:ogc:def:crs:IAU2000::19900",
    verticalDatum: "Product-specific (USGS DEM: relative to its reference sphere)",
    projections: ["Equirectangular"],
    availableViews: ["2D"],
    layers: ["mercury-mdis-mosaic", "mercury-usgs-dem-clrshade"],
    datasets: ["messenger-dem-665m"],
    coverage: "MESSENGER global mosaics; USGS DEM ≈ 665 m/px — low detail.",
    browserGeolocationAllowed: false,
    conflicts: [
      "PROJ IAU_2015:19900 radius 2 440 530 m vs ESRI:104974 'Mercury_2015' 2 439 400 m; Trek declares the IAU2000 namespace.",
    ],
  },
  VENUS: {
    id: "VENUS",
    name: "Venus (preview)",
    category: "terrestrial",
    status: "EXPERIMENTAL",
    radiusEquatorial: 6_051_800,
    radiusPolar: 6_051_800,
    defaultCenter: [0, 0],
    longitudeConvention: "East-positive",
    longitudeRange: "0..360 (Magellan products)",
    latitudeType: "Planetocentric",
    coordinateSystem: "IAU_2015:29900 (Venus 2015 sphere)",
    mapCrs: null,
    verticalDatum: "Magellan GTDR stores planetary radius, not height above a datum",
    projections: ["Sinusoidal", "Mercator", "North polar stereographic", "South polar stereographic"],
    availableViews: [],
    layers: [],
    datasets: ["magellan-gtdr"],
    coverage: "Magellan GTDR ≈ 5×5 km/px. No NASA Trek map service exists for Venus.",
    browserGeolocationAllowed: false,
    conflicts: [],
  },
};

/** Order of the planet switcher. Mars stays the default start body. */
export const PLANET_ORDER: PlanetId[] = ["EARTH", "MARS", "MOON", "MERCURY", "VENUS"];
export const DEFAULT_PLANET: PlanetId = "MARS";

export function getPlanet(id: PlanetId): PlanetConfig {
  return PLANETS[id];
}

/** First eccentricity squared of the body's reference figure (0 for spheres). */
export function planetE2(p: PlanetConfig): number {
  const a = p.radiusEquatorial;
  const b = p.radiusPolar;
  return 1 - (b * b) / (a * a);
}
