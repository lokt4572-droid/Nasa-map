"""Central registry of celestial bodies (backend mirror of frontend/src/config/planetRegistry.ts).

Every radius below was read from the PROJ database shipped with pyproj 3.8 (checked
2026-11-14) unless the entry says otherwise. Where authoritative sources disagree, both
values are kept in ``conflicts`` instead of silently picking one.

Rules enforced through this registry:
* a DEM / point is only accepted when its CRS ellipsoid matches the selected body;
* Earth (WGS84) parameters are never applied to another body, and vice versa.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PlanetConfig:
    id: str
    name: str
    category: str
    status: str  # PRIMARY | FULL | SCIENTIFIC_VIEWER | EXPERIMENTAL
    radius_equatorial_m: float
    radius_polar_m: float
    reference_crs: str  # PROJ identifier used by the backend
    reference_crs_note: str
    latitude_type: str
    longitude_direction: str
    longitude_range: str
    units: str
    vertical_datum: str
    projections: tuple[str, ...]
    map_crs: str | None  # CRS identifier declared by the map service, if any
    # Accept CRS ellipsoids whose semi-major axis is inside this range (metres).
    semi_major_range_m: tuple[float, float]
    coverage_note: str
    browser_geolocation_allowed: bool = False
    conflicts: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["projections"] = list(self.projections)
        d["semi_major_range_m"] = list(self.semi_major_range_m)
        d["conflicts"] = list(self.conflicts)
        return d


PLANETS: dict[str, PlanetConfig] = {
    "MARS": PlanetConfig(
        id="MARS",
        name="Mars",
        category="terrestrial",
        status="PRIMARY",
        radius_equatorial_m=3_396_190.0,
        radius_polar_m=3_376_200.0,
        reference_crs="ESRI:104905",
        reference_crs_note="GCS_Mars_2000 (IAU 2000 ellipsoid, rf 169.894447223612). Trek declares urn:ogc:def:crs:EPSG::104905.",
        latitude_type="Map: as declared by source; MOLA MEGDR: planetocentric",
        longitude_direction="EAST_POSITIVE",
        longitude_range="-180..180 (map); MEGDR products 0..360",
        units="degrees / metres",
        vertical_datum="MOLA areoid (GMM3, mgm1025) for MEGDR topography",
        projections=("Equirectangular", "Simple Cylindrical", "Polar Stereographic"),
        map_crs="urn:ogc:def:crs:EPSG::104905",
        semi_major_range_m=(3_390_000.0, 3_400_000.0),
        coverage_note="Global MOLA (4–128 px/deg); HiRISE/CTX regional only.",
        conflicts=(
            "MEGDR products use a 3 396 000 m sphere; the Trek map uses the 3 396 190 m Mars 2000 ellipsoid.",
        ),
    ),
    "EARTH": PlanetConfig(
        id="EARTH",
        name="Earth",
        category="terrestrial",
        status="FULL",
        radius_equatorial_m=6_378_137.0,
        radius_polar_m=6_356_752.314245179,
        reference_crs="EPSG:4326",
        reference_crs_note="WGS 84 (EPSG:4326); web maps in EPSG:3857.",
        latitude_type="Geodetic (WGS 84)",
        longitude_direction="EAST_POSITIVE",
        longitude_range="-180..180",
        units="degrees / metres",
        vertical_datum="Product-specific: Copernicus DEM = EGM2008 (EPSG:3855); GEBCO = mean sea level",
        projections=("EPSG:4326", "EPSG:3857"),
        map_crs="EPSG:3857",
        semi_major_range_m=(6_377_000.0, 6_379_000.0),
        coverage_note="Global imagery (GIBS, OSM); DEMs only where downloaded.",
        browser_geolocation_allowed=True,
    ),
    "MOON": PlanetConfig(
        id="MOON",
        name="Moon",
        category="terrestrial",
        status="SCIENTIFIC_VIEWER",
        radius_equatorial_m=1_737_400.0,
        radius_polar_m=1_737_400.0,
        reference_crs="ESRI:104903",
        reference_crs_note="GCS_Moon_2000 sphere R = 1 737 400 m. Trek declares urn:ogc:def:crs:EPSG::104903.",
        latitude_type="Planetocentric",
        longitude_direction="EAST_POSITIVE",
        longitude_range="-180..180 (Trek map)",
        units="degrees / metres",
        vertical_datum="Product-specific (GLD100: not stated on the LROC product page)",
        projections=("Equirectangular", "Polar Stereographic"),
        map_crs="urn:ogc:def:crs:EPSG::104903",
        semi_major_range_m=(1_737_000.0, 1_738_000.0),
        coverage_note="WAC mosaic global; GLD100 DEM 79°S–79°N (98.2 %), use LOLA near the poles.",
    ),
    "MERCURY": PlanetConfig(
        id="MERCURY",
        name="Mercury",
        category="terrestrial",
        status="SCIENTIFIC_VIEWER",
        radius_equatorial_m=2_440_530.0,
        radius_polar_m=2_440_530.0,
        reference_crs="IAU_2015:19900",
        reference_crs_note="Mercury (2015) sphere / ocentric. Trek declares urn:ogc:def:crs:IAU2000::19900 (IAU 2000 namespace).",
        latitude_type="Planetocentric",
        longitude_direction="EAST_POSITIVE",
        longitude_range="-180..180 (Trek map); USGS DEM 0..360",
        units="degrees / metres",
        vertical_datum="Product-specific (USGS MESSENGER DEM 665 m: relative to its reference sphere)",
        projections=("Equirectangular",),
        map_crs="urn:ogc:def:crs:IAU2000::19900",
        semi_major_range_m=(2_438_000.0, 2_441_000.0),
        coverage_note="MESSENGER MDIS global mosaics; USGS DEM ≈ 665 m/px (low detail).",
        conflicts=(
            "PROJ IAU_2015:19900 radius = 2 440 530 m; ESRI:104974 'Mercury_2015' = 2 439 400 m. Both are accepted for DEM CRS checks; the value of each product's own label is used.",
        ),
    ),
    "VENUS": PlanetConfig(
        id="VENUS",
        name="Venus (preview)",
        category="terrestrial",
        status="EXPERIMENTAL",
        radius_equatorial_m=6_051_800.0,
        radius_polar_m=6_051_800.0,
        reference_crs="IAU_2015:29900",
        reference_crs_note="Venus (2015) sphere / ocentric.",
        latitude_type="Planetocentric",
        longitude_direction="EAST_POSITIVE",
        longitude_range="0..360 (Magellan products)",
        units="degrees / metres",
        vertical_datum="Magellan GTDR stores planetary radius, not height above a datum",
        projections=("Sinusoidal", "Mercator", "North polar stereographic", "South polar stereographic"),
        map_crs=None,
        semi_major_range_m=(6_050_000.0, 6_053_000.0),
        coverage_note="Magellan GTDR ≈ 5×5 km/px. No NASA Trek map service exists for Venus.",
    ),
}

DEFAULT_PLANET = "MARS"


class UnknownPlanetError(ValueError):
    pass


def get_planet(planet_id: str) -> PlanetConfig:
    p = PLANETS.get((planet_id or "").upper())
    if not p:
        raise UnknownPlanetError(f"Unknown planet {planet_id!r}; expected one of {', '.join(PLANETS)}")
    return p


def planet_for_semi_major(a_m: float) -> PlanetConfig | None:
    for p in PLANETS.values():
        lo, hi = p.semi_major_range_m
        if lo <= a_m <= hi:
            return p
    return None


def crs_matches_planet(crs, planet_id: str) -> bool:
    """True when the CRS ellipsoid belongs to the given body."""
    if crs is None or crs.ellipsoid is None:
        return False
    lo, hi = get_planet(planet_id).semi_major_range_m
    return lo <= crs.ellipsoid.semi_major_metre <= hi
