"""
Mars coordinate system utilities.

Mars uses a coordinate system similar to Earth's WGS84 but with different
reference ellipsoid parameters.

Mars reference ellipsoid (IAU 2000):
- Semi-major axis: 3396.19 km
- Semi-minor axis: 3376.20 km
- Flattening: 1/169.894

For web mapping, we typically use Simple Cylindrical (Equirectangular) 
projection with Mars radius, or the Mars-specific projections.
"""
from dataclasses import dataclass
from typing import Tuple, Optional
import math


# Mars physical constants (IAU 2000)
MARS_EQUATORIAL_RADIUS_KM = 3396.19
MARS_POLAR_RADIUS_KM = 3376.20
MARS_FLATTENING = 1 / 169.894
MARS_MEAN_RADIUS_KM = 3389.50

# Degrees to km conversion on Mars
# At equator: 1 degree ≈ 59.3 km
# At poles: 1 degree ≈ 58.9 km
DEG_TO_KM_EQUATOR = 2 * math.pi * MARS_EQUATORIAL_RADIUS_KM / 360
DEG_TO_KM_POLAR = 2 * math.pi * MARS_POLAR_RADIUS_KM / 360


@dataclass
class MarsCoordinate:
    """Mars coordinate with metadata."""
    longitude: float  # -180 to 180 (or 0-360)
    latitude: float   # -90 to 90
    
    def __post_init__(self):
        # Normalize longitude to -180..180
        self.longitude = ((self.longitude + 180) % 360) - 180
        # Clamp latitude
        self.latitude = max(-90, min(90, self.latitude))
    
    @property
    def lon_360(self) -> float:
        """Longitude in 0-360 range."""
        return self.longitude if self.longitude >= 0 else self.longitude + 360
    
    def distance_to(self, other: "MarsCoordinate") -> float:
        """Calculate great-circle distance in km using haversine formula."""
        lat1, lon1 = math.radians(self.latitude), math.radians(self.longitude)
        lat2, lon2 = math.radians(other.latitude), math.radians(other.longitude)
        
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        
        a = (math.sin(dlat / 2) ** 2 + 
             math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        c = 2 * math.asin(min(1, math.sqrt(a)))
        
        return MARS_MEAN_RADIUS_KM * c
    
    def to_wgs84(self) -> Tuple[float, float]:
        """Convert to WGS84-like coordinate (same lat/lon, different ellipsoid).
        
        For display purposes, Mars coordinates are often treated as if they were
        Earth WGS84 coordinates. This returns the same numerical values.
        """
        return (self.longitude, self.latitude)
    
    def to_dict(self) -> dict:
        return {"longitude": self.longitude, "latitude": self.latitude}


def meters_per_degree_at_lat(latitude: float) -> Tuple[float, float]:
    """Return (meters per degree longitude, meters per degree latitude) at given latitude on Mars."""
    lat_rad = math.radians(latitude)
    # Radius of parallel at this latitude
    r_parallel = MARS_EQUATORIAL_RADIUS_KM * 1000 * math.cos(lat_rad)
    m_per_deg_lon = 2 * math.pi * r_parallel / 360
    m_per_deg_lat = 2 * math.pi * MARS_POLAR_RADIUS_KM * 1000 / 360
    return (m_per_deg_lon, m_per_deg_lat)


def create_bbox_around_point(lon: float, lat: float, radius_km: float) -> Tuple[float, float, float, float]:
    """Create bounding box around a point with given radius in km."""
    m_per_deg_lon, m_per_deg_lat = meters_per_degree_at_lat(lat)
    deg_lon = radius_km / (m_per_deg_lon / 1000)
    deg_lat = radius_km / (m_per_deg_lat / 1000)
    return (lon - deg_lon, lat - deg_lat, lon + deg_lon, lat + deg_lat)


# NASA Mars Trek layer identifiers and configurations
MARS_TREK_BASE_URL = "https://trek.nasa.gov/tiles/mars"

# Known WMTS layer identifiers from NASA Mars Trek
MARS_LAYERS = {
    "mola_global": {
        "id": "Mars_MGS_MOLA_ClrShade_merge_global_463m",
        "name": "MOLA Global Color Hillshade",
        "description": "Mars Global Surveyor MOLA Global Color Hillshade (463m/px)",
        "type": "hillshade",
        "resolution_m": 463,
        "coverage": "global",
        "wmts_style": "default",
        "wmts_format": "image/png",
        "attribution": "NASA/USGS",
    },
    "hrsc_mola_blend": {
        "id": "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
        "name": "HRSC + MOLA Blend",
        "description": "MOLA and HRSC Color Hillshade Blend (200m/px)",
        "type": "hillshade",
        "resolution_m": 200,
        "coverage": "regional",
        "wmts_style": "default",
        "wmts_format": "image/png",
        "attribution": "NASA/ESA/DLR/FU Berlin",
    },
    "hirise_jezero": {
        "id": "JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd",
        "name": "HiRISE Jezero Orthomosaic",
        "description": "MRO HiRISE Jezero Controlled Orthomosaic (25cm/px)",
        "type": "orthoimage",
        "resolution_m": 0.25,
        "coverage": {
            "west": 77.2229331,
            "south": 18.3067994,
            "east": 77.583964,
            "north": 18.669315,
        },
        "wmts_style": "default",
        "wmts_format": "image/png",
        "attribution": "NASA/JPL-Caltech/University of Arizona",
    },
}


def get_wmts_tile_url(layer_id: str, style: str = "default", tile_matrix_set: str = "Mars_Equirectangular", 
                      format: str = "image/png") -> str:
    """Generate WMTS tile URL template for NASA Mars Trek."""
    return f"{MARS_TREK_BASE_URL}/{{TileMatrix}}/{{TileCol}}/{{TileRow}}.png"


def get_wmts_getcapabilities_url() -> str:
    return f"{MARS_TREK_BASE_URL}/1.0.0/WMTSCapabilities.xml"
