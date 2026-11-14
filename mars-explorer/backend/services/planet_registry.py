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


# ---------------------------------------------------------------------------
# Map layer catalog per body. Every Trek entry was verified against its live
# GetCapabilities on 2026-11-14 (identifier, SupportedCRS, format, bbox, levels).
# Tile grids are NOT stored here: clients must read them from GetCapabilities.

TREK = "https://trek.nasa.gov/tiles"


def _trek(body: str, layer_id: str, **kw) -> dict:
    return {
        "source": "NASA_TREK",
        "layer_id": layer_id,
        "capabilities_url": f"{TREK}/{body}/EQ/{layer_id}/1.0.0/WMTSCapabilities.xml",
        "pixels_are_elevation": False,
        "verified_at": "2026-11-14",
        **kw,
    }


PLANET_LAYERS: dict[str, list[dict]] = {
    "MARS": [
        _trek("Mars", "Mars_MGS_MOLA_ClrShade_merge_global_463m", id="mola-global-clrshade", name="MOLA Global Color Hillshade",
              kind="COLOR_HILLSHADE", resolution="463 m/px", coverage="global", crs="urn:ogc:def:crs:EPSG::104905", format="image/jpeg", levels=8),
        _trek("Mars", "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw", id="mola-hrsc-blend-clrshade", name="MOLA + HRSC Color Hillshade Blend",
              kind="COLOR_HILLSHADE", resolution="200 m/px", coverage="global", crs="urn:ogc:def:crs:EPSG::104905", format="image/jpeg", levels=9),
        _trek("Mars", "Mars_Viking_MDIM21_ClrMosaic_global_232m", id="viking-mdim21-color", name="Viking MDIM 2.1 Colorized Mosaic",
              kind="ORTHOIMAGE", resolution="232 m/px", coverage="global", crs="urn:ogc:def:crs:EPSG::104905", format="image/jpeg", levels=10),
        _trek("Mars", "Mars_MO_THEMIS-IR-Day_mosaic_global_100m_v12_clon0_ly", id="themis-day-ir-100m", name="THEMIS Day IR Global Mosaic",
              kind="THERMAL_IR_MOSAIC", resolution="100 m/px", coverage="global", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=11),
        _trek("Mars", "JEZ_ctx_B_soc_008_orthoMosaic_6m_Eqc_latTs0_lon0", id="jezero-ctx-ortho", name="CTX Jezero Orthomosaic",
              kind="ORTHOIMAGE", resolution="6 m/px", coverage="regional", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=14),
        _trek("Mars", "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd", id="jezero-hirise-ortho", name="HiRISE Jezero Controlled Orthomosaic",
              kind="ORTHOIMAGE", resolution="25 cm/px", coverage="regional", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=18),
        # Landing-site mosaics (Trek catalogue search + live GetCapabilities, 2026-11-14)
        _trek("Mars", "curiosity_ctx_mosaic", id="gale-ctx-mosaic", name="CTX Gale Mosaic", kind="ORTHOIMAGE", resolution="tile pyramid finest level ~41 m/px",
              coverage="regional", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=11, region="Gale crater"),
        _trek("Mars", "curiosity_hirise_mosaic", id="gale-hirise-mosaic", name="HiRISE Gale Mosaic", kind="ORTHOIMAGE", resolution="tile pyramid finest level ~64 cm/px",
              coverage="regional", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=17, region="Gale crater"),
        _trek("Mars", "spirit_hirise_mosaic", id="gusev-hirise-mosaic", name="HiRISE Gusev (Spirit) Mosaic", kind="ORTHOIMAGE", resolution="tile pyramid finest level ~32 cm/px",
              coverage="regional", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=18, region="Gusev crater"),
        _trek("Mars", "opportunity_hirise_mosaic", id="meridiani-hirise-mosaic", name="HiRISE Meridiani (Opportunity) Mosaic", kind="ORTHOIMAGE",
              resolution="tile pyramid finest level ~32 cm/px", coverage="regional", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=18, region="Meridiani Planum"),
        _trek("Mars", "phoenix_hirise_mosaic", id="phoenix-hirise-mosaic", name="HiRISE Phoenix Site Mosaic", kind="ORTHOIMAGE", resolution="tile pyramid finest level ~64 cm/px",
              coverage="regional", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=17, region="Green Valley (Vastitas Borealis)"),
        _trek("Mars", "InSightCTXMosaic_112917", id="insight-ctx-mosaic", name="CTX InSight Site Mosaic", kind="ORTHOIMAGE", resolution="tile pyramid finest level ~5 m/px",
              coverage="regional", crs="urn:ogc:def:crs:EPSG::104905", format="image/png", levels=14, region="Elysium Planitia"),
    ],
    "MOON": [
        _trek("Moon", "LRO_WAC_Mosaic_Global_303ppd_v02", id="moon-lroc-wac-mosaic", name="LROC WAC Global Mosaic v2",
              kind="ORTHOIMAGE", resolution="303 px/deg (≈100 m/px at the equator)", coverage="global", crs="urn:ogc:def:crs:EPSG::104903", format="image/jpeg", levels=9),
        _trek("Moon", "LRO_LOLA_ClrShade_Global_128ppd_v04", id="moon-lola-clrshade", name="LOLA Color Hillshade v4",
              kind="COLOR_HILLSHADE", resolution="128 px/deg (≈237 m/px at the equator)", coverage="global", crs="urn:ogc:def:crs:EPSG::104903", format="image/png", levels=6),
    ],
    "MERCURY": [
        _trek("Mercury", "Mercury_MESSENGER_mosaic_global_250m_2013", id="mercury-mdis-mosaic", name="MESSENGER MDIS Global Mosaic (2013)",
              kind="ORTHOIMAGE", resolution="250 m/px", coverage="global", crs="urn:ogc:def:crs:IAU2000::19900", format="image/png", levels=8),
        _trek("Mercury", "Mercury_Messenger_USGS_DEM_665m_v2_HillshadeColor", id="mercury-usgs-dem-clrshade", name="USGS MESSENGER DEM 665 m — Color Hillshade",
              kind="COLOR_HILLSHADE", resolution="665 m/px (low detail)", coverage="global", crs="urn:ogc:def:crs:IAU2000::19900", format="image/png", levels=6),
    ],
    "VENUS": [],  # NASA Trek has no Venus body (checked 2026-11-14); see the GTDR catalog entry.
    "EARTH": [],  # Earth layers come from NASA GIBS discovery + OpenStreetMap (Earth mode).
}


def layers_for(planet_id: str) -> list[dict]:
    return PLANET_LAYERS[get_planet(planet_id).id]
