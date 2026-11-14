"""Mars coordinate reference systems and conversions.

Every coordinate handled by the backend carries an explicit CRS identifier and
latitude/longitude convention. Nothing here guesses a CRS: unknown identifiers raise
:class:`UnknownCRSError`.

Reference values
----------------
Mars 2000 / IAU 2000 ellipsoid (as defined in the PROJ database entry ESRI:104905,
verified with pyproj 3.8 / PROJ data):
    +proj=longlat +a=3396190 +rf=169.894447223612
Semi-minor axis b = 3376200 m (a = 3396190 m, f = 1/169.894447223612).
Mars 2000 sphere (ESRI:104971, IAU_2015:49900): R = 3396190 m.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

MARS_EQUATORIAL_RADIUS_M = 3_396_190.0
MARS_INVERSE_FLATTENING = 169.894447223612
MARS_FLATTENING = 1.0 / MARS_INVERSE_FLATTENING
MARS_POLAR_RADIUS_M = MARS_EQUATORIAL_RADIUS_M * (1.0 - MARS_FLATTENING)  # ~3376200 m
MARS_E2 = MARS_FLATTENING * (2.0 - MARS_FLATTENING)

MARS_2000_PROJ4 = "+proj=longlat +a=3396190 +rf=169.894447223612 +no_defs +type=crs"

# CRS identifier exactly as declared in NASA Mars Trek WMTS GetCapabilities
# (<ows:SupportedCRS> and <ows:BoundingBox crs=...>) for the EQ (equirectangular,
# decimal degree) layers, checked 2026-11-12.
TREK_DECLARED_CRS = "urn:ogc:def:crs:EPSG::104905"


class LongitudeConvention(StrEnum):
    EAST_POSITIVE_180 = "EAST_POSITIVE_180"  # -180..180, east positive
    EAST_POSITIVE_360 = "EAST_POSITIVE_360"  # 0..360, east positive
    WEST_POSITIVE_360 = "WEST_POSITIVE_360"  # 0..360, west positive (older planetographic products)
    UNKNOWN = "UNKNOWN"


class LatitudeConvention(StrEnum):
    PLANETOCENTRIC = "PLANETOCENTRIC"
    PLANETOGRAPHIC = "PLANETOGRAPHIC"
    # The source declares a CRS but does not state the latitude type explicitly.
    AS_DECLARED_BY_SOURCE = "AS_DECLARED_BY_SOURCE"
    UNKNOWN = "UNKNOWN"


class UnknownCRSError(ValueError):
    """Raised when a CRS identifier cannot be resolved without guessing."""


@dataclass(frozen=True)
class CRSAlias:
    requested: str
    resolved_as: str
    reason: str


# Explicit, documented aliases. These are NOT silent namespace fixes: every response
# that uses an alias reports it (see resolve_crs). PROJ has no EPSG:104905; the code
# 104905 exists only in the ESRI namespace (GCS_Mars_2000). NASA Trek nevertheless
# writes urn:ogc:def:crs:EPSG::104905. We interpret it with the ESRI:104905 parameters
# because (1) the numeric code matches, (2) the tile matrix TopLeftCorner (-180, 90)
# and the bounding boxes are in decimal degrees, consistent with a geographic Mars 2000
# CRS. The latitude type (planetocentric vs planetographic) of the underlying Trek
# mosaics is NOT stated in the capabilities document.
CRS_ALIASES: dict[str, CRSAlias] = {
    TREK_DECLARED_CRS: CRSAlias(
        requested=TREK_DECLARED_CRS,
        resolved_as="ESRI:104905",
        reason=(
            "NASA Trek declares urn:ogc:def:crs:EPSG::104905, which does not exist in "
            "the EPSG registry. Interpreted with ESRI:104905 (GCS_Mars_2000) parameters "
            "by explicit project configuration."
        ),
    ),
}


def normalize_lon_180(lon_east_deg: float) -> float:
    """Normalize an east-positive longitude to the half-open range [-180, 180)."""
    if not math.isfinite(lon_east_deg):
        raise ValueError("longitude must be finite")
    lon = ((lon_east_deg + 180.0) % 360.0) - 180.0
    return 0.0 if lon == 0 else lon


def normalize_lon_360(lon_east_deg: float) -> float:
    """Normalize an east-positive longitude to [0, 360)."""
    if not math.isfinite(lon_east_deg):
        raise ValueError("longitude must be finite")
    return lon_east_deg % 360.0


def east_to_west_360(lon_east_deg: float) -> float:
    """Convert east-positive longitude to west-positive [0, 360)."""
    return (-lon_east_deg) % 360.0


def west_360_to_east_180(lon_west_deg: float) -> float:
    return normalize_lon_180(-lon_west_deg)


def validate_lat(lat_deg: float) -> float:
    if not math.isfinite(lat_deg) or not -90.0 <= lat_deg <= 90.0:
        raise ValueError(f"latitude {lat_deg!r} is outside [-90, 90] degrees")
    return lat_deg


def planetocentric_to_planetographic(
    lat_c_deg: float,
    a: float = MARS_EQUATORIAL_RADIUS_M,
    b: float = MARS_POLAR_RADIUS_M,
) -> float:
    """tan(lat_g) = (a/b)^2 * tan(lat_c). Exact at the equator and the poles."""
    validate_lat(lat_c_deg)
    if abs(lat_c_deg) == 90.0:
        return lat_c_deg
    lat_c = math.radians(lat_c_deg)
    return math.degrees(math.atan((a / b) ** 2 * math.tan(lat_c)))


def planetographic_to_planetocentric(
    lat_g_deg: float,
    a: float = MARS_EQUATORIAL_RADIUS_M,
    b: float = MARS_POLAR_RADIUS_M,
) -> float:
    validate_lat(lat_g_deg)
    if abs(lat_g_deg) == 90.0:
        return lat_g_deg
    lat_g = math.radians(lat_g_deg)
    return math.degrees(math.atan((b / a) ** 2 * math.tan(lat_g)))


def meridional_radius_m(lat_g_deg: float, a: float = MARS_EQUATORIAL_RADIUS_M, e2: float = MARS_E2) -> float:
    """Radius of curvature in the meridian, M(phi). With e2=0 this is the sphere radius."""
    s = math.sin(math.radians(lat_g_deg))
    return a * (1 - e2) / (1 - e2 * s * s) ** 1.5


def prime_vertical_radius_m(lat_g_deg: float, a: float = MARS_EQUATORIAL_RADIUS_M, e2: float = MARS_E2) -> float:
    """Radius of curvature in the prime vertical, N(phi). With e2=0 this is the sphere radius."""
    s = math.sin(math.radians(lat_g_deg))
    return a / math.sqrt(1 - e2 * s * s)


def resolve_crs(identifier: str):
    """Return (pyproj.CRS, CRSAlias | None). Raises UnknownCRSError, never guesses."""
    from pyproj import CRS
    from pyproj.exceptions import CRSError

    if not identifier or not identifier.strip():
        raise UnknownCRSError("CRS identifier is empty")
    identifier = identifier.strip()
    alias = CRS_ALIASES.get(identifier)
    target = alias.resolved_as if alias else identifier
    try:
        crs = CRS.from_user_input(target)
    except CRSError as exc:
        raise UnknownCRSError(f"Cannot resolve CRS {identifier!r}: {exc}") from exc
    if crs.ellipsoid is None:
        raise UnknownCRSError(f"CRS {identifier!r} has no ellipsoid definition")
    if not is_mars_crs(crs):
        raise UnknownCRSError(
            f"CRS {identifier!r} ({crs.name}) does not describe Mars "
            f"(semi-major axis {crs.ellipsoid.semi_major_metre} m)"
        )
    return crs, alias


def is_mars_crs(crs) -> bool:
    if crs.ellipsoid is None:
        return False
    a = crs.ellipsoid.semi_major_metre
    # Mars reference radii in use are ~3396000–3397000 m. Earth is ~6378137 m.
    return 3_390_000.0 <= a <= 3_400_000.0


def transform_point(x: float, y: float, src_crs, dst_crs) -> tuple[float, float]:
    """Transform (x=lon/easting, y=lat/northing) between two pyproj CRS objects."""
    from pyproj import Transformer

    transformer = Transformer.from_crs(src_crs, dst_crs, always_xy=True)
    out_x, out_y = transformer.transform(x, y)
    if not (math.isfinite(out_x) and math.isfinite(out_y)):
        raise ValueError("coordinate transformation produced a non-finite result")
    return float(out_x), float(out_y)


def geodesic_distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Geodesic distance on the Mars 2000 ellipsoid (inputs are ellipsoidal/ographic)."""
    from pyproj import Geod

    geod = Geod(a=MARS_EQUATORIAL_RADIUS_M, rf=MARS_INVERSE_FLATTENING)
    _, _, dist = geod.inv(lon1, lat1, lon2, lat2)
    return float(dist)


def adapt_latitude(lat_deg: float, from_conv: str, to_conv: str) -> tuple[float, str]:
    """Convert latitude between conventions explicitly.

    PROJ treats the Mars sphere (ESRI:104971) and the Mars 2000 ellipsoid (ESRI:104905)
    as the same datum and applies a *null* transformation between them (verified with
    PROJ 9 / pyproj 3.8: 45.0 -> 45.0). It therefore never converts planetocentric to
    planetographic latitude for us. This function does it analytically when both
    conventions are known. Returns (latitude, status) where status is one of
    ``NONE``, ``CONVERTED_<FROM>_TO_<TO>`` or ``NOT_VERIFIED``.
    """
    known = {LatitudeConvention.PLANETOCENTRIC.value, LatitudeConvention.PLANETOGRAPHIC.value}
    f, t = str(from_conv), str(to_conv)
    if f in known and t in known:
        if f == t:
            return lat_deg, "NONE"
        if f == LatitudeConvention.PLANETOCENTRIC.value:
            return planetocentric_to_planetographic(lat_deg), f"CONVERTED_{f}_TO_{t}"
        return planetographic_to_planetocentric(lat_deg), f"CONVERTED_{f}_TO_{t}"
    return lat_deg, "NOT_VERIFIED"


def latitude_convention_for_crs(crs) -> LatitudeConvention:
    """Derive the latitude type implied by the CRS geometry.

    On a sphere, planetocentric and planetographic latitude coincide; we report
    PLANETOCENTRIC. On an ellipsoid, PROJ geographic latitude is geodetic, i.e.
    planetographic.
    """
    geodetic = crs.geodetic_crs or crs
    ell = geodetic.ellipsoid
    if ell is None:
        return LatitudeConvention.UNKNOWN
    if math.isclose(ell.semi_major_metre, ell.semi_minor_metre, rel_tol=0, abs_tol=1e-3):
        return LatitudeConvention.PLANETOCENTRIC
    return LatitudeConvention.PLANETOGRAPHIC
