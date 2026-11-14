"""
Terrain analysis service for MARS EXPLORER.

Provides slope, aspect, hillshade, roughness, curvature, and other
terrain derivatives from DEM data.
"""
import numpy as np
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
from pathlib import Path

try:
    from scipy import ndimage
    from scipy.signal import convolve2d
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from .dem_reader import DEMReader, DEMInfo


@dataclass
class TerrainResult:
    """Result of a terrain analysis operation."""
    analysis_type: str
    data: Optional[np.ndarray]  # 2D array of results
    metadata: Dict[str, Any]
    statistics: Dict[str, float]
    success: bool
    error: Optional[str] = None


class TerrainAnalyzer:
    """Perform terrain analysis on DEM data."""
    
    def __init__(self, dem_path: str):
        self.reader = DEMReader(dem_path)
        self._dem_data = None
        self._info = None
    
    def load(self) -> bool:
        """Load DEM data into memory."""
        if not self.reader.open():
            return False
        
        self._info = self.reader.get_info()
        
        if self.reader._dataset == "mock":
            # Generate mock DEM data
            self._dem_data = self._generate_mock_dem()
            return True
        
        # Load actual DEM data
        try:
            if hasattr(self.reader._dataset, 'read'):
                # Rasterio
                self._dem_data = self.reader._dataset.read(1).astype(np.float32)
            else:
                # GDAL
                band = self.reader._dataset.GetRasterBand(1)
                self._dem_data = band.ReadAsArray().astype(np.float32)
            
            # Mask nodata values
            if self._info.nodata is not None:
                self._dem_data = np.ma.masked_equal(self._dem_data, self._info.nodata)
            
            return True
        except Exception as e:
            print(f"Failed to load DEM data: {e}")
            return False
    
    def _generate_mock_dem(self) -> np.ndarray:
        """Generate synthetic Mars DEM for development."""
        h, w = self._info.height, self._info.width
        y, x = np.meshgrid(np.linspace(-90, 90, h), np.linspace(-180, 180, w), indexing='ij')
        
        elevation = np.zeros((h, w), dtype=np.float32)
        
        # Tharsis
        tharsis = np.exp(-((x + 105) ** 2 + y ** 2) / (2 * 15 ** 2)) * 10000
        elevation += tharsis
        
        # Hellas Basin
        hellas = -np.exp(-((x - 75) ** 2 + (y + 42) ** 2) / (2 * 10 ** 2)) * 7000
        elevation += hellas
        
        # Valles Marineris
        valles = -np.exp(-((x - 65) ** 2 + (y + 7) ** 2) / (2 * 3 ** 2)) * 5000
        elevation += valles
        
        # Add noise
        np.random.seed(42)
        elevation += np.random.normal(0, 200, (h, w))
        
        return np.clip(elevation, -10000, 25000)
    
    def compute_slope(self, unit: str = "degrees") -> TerrainResult:
        """Compute slope from DEM."""
        if self._dem_data is None:
            if not self.load():
                return TerrainResult("slope", None, {}, {}, False, "Failed to load DEM")
        
        if not SCIPY_AVAILABLE:
            return TerrainResult("slope", None, {}, {}, False, "SciPy not available for slope computation")
        
        try:
            # Get cell size in meters
            cell_size_x = abs(self._info.resolution[0]) * 111000  # rough deg to m at equator
            cell_size_y = abs(self._info.resolution[1]) * 111000
            
            # Use Horn's algorithm (3x3 kernel)
            # dz/dx and dz/dy using 3x3 neighborhood
            z = self._dem_data.filled(np.nan) if np.ma.is_masked(self._dem_data) else self._dem_data
            
            # Gradient
            dzdx = (np.roll(z, -1, axis=1) - np.roll(z, 1, axis=1)) / (2 * cell_size_x)
            dzdy = (np.roll(z, -1, axis=0) - np.roll(z, 1, axis=0)) / (2 * cell_size_y)
            
            # Slope
            slope_rad = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
            
            if unit == "degrees":
                result = np.degrees(slope_rad)
            elif unit == "percent":
                result = np.tan(slope_rad) * 100
            else:
                result = slope_rad
            
            # Mask invalid
            if np.ma.is_masked(self._dem_data):
                result = np.ma.masked_where(self._dem_data.mask, result)
            
            valid_data = result[~np.ma.getmaskarray(result)] if np.ma.is_masked(result) else result.flatten()
            valid_data = valid_data[~np.isnan(valid_data)]
            
            stats = {
                "min": float(np.min(valid_data)) if len(valid_data) > 0 else 0,
                "max": float(np.max(valid_data)) if len(valid_data) > 0 else 0,
                "mean": float(np.mean(valid_data)) if len(valid_data) > 0 else 0,
                "std": float(np.std(valid_data)) if len(valid_data) > 0 else 0,
            }
            
            return TerrainResult(
                analysis_type="slope",
                data=result,
                metadata={"unit": unit, "cell_size_x_m": cell_size_x, "cell_size_y_m": cell_size_y},
                statistics=stats,
                success=True,
            )
        except Exception as e:
            return TerrainResult("slope", None, {}, {}, False, str(e))
    
    def compute_aspect(self) -> TerrainResult:
        """Compute aspect (slope direction) from DEM."""
        if self._dem_data is None:
            if not self.load():
                return TerrainResult("aspect", None, {}, {}, False, "Failed to load DEM")
        
        if not SCIPY_AVAILABLE:
            return TerrainResult("aspect", None, {}, {}, False, "SciPy not available")
        
        try:
            z = self._dem_data.filled(np.nan) if np.ma.is_masked(self._dem_data) else self._dem_data
            cell_size_x = abs(self._info.resolution[0]) * 111000
            cell_size_y = abs(self._info.resolution[1]) * 111000
            
            dzdx = (np.roll(z, -1, axis=1) - np.roll(z, 1, axis=1)) / (2 * cell_size_x)
            dzdy = (np.roll(z, -1, axis=0) - np.roll(z, 1, axis=0)) / (2 * cell_size_y)
            
            # Aspect in degrees (0 = North, 90 = East)
            aspect_rad = np.arctan2(dzdx, -dzdy)
            aspect_deg = np.degrees(aspect_rad)
            aspect_deg = np.where(aspect_deg < 0, aspect_deg + 360, aspect_deg)
            
            # Flat areas (slope ~ 0) have undefined aspect
            slope = np.sqrt(dzdx**2 + dzdy**2)
            aspect_deg = np.ma.masked_where(slope < 0.001, aspect_deg)
            
            valid_data = aspect_deg[~np.ma.getmaskarray(aspect_deg)] if np.ma.is_masked(aspect_deg) else aspect_deg.flatten()
            valid_data = valid_data[~np.isnan(valid_data)]
            
            stats = {
                "min": float(np.min(valid_data)) if len(valid_data) > 0 else 0,
                "max": float(np.max(valid_data)) if len(valid_data) > 0 else 0,
                "mean": float(np.mean(valid_data)) if len(valid_data) > 0 else 0,
            }
            
            return TerrainResult(
                analysis_type="aspect",
                data=aspect_deg,
                metadata={"unit": "degrees", "north_is": 0},
                statistics=stats,
                success=True,
            )
        except Exception as e:
            return TerrainResult("aspect", None, {}, {}, False, str(e))
    
    def compute_hillshade(self, azimuth: float = 315, altitude: float = 45) -> TerrainResult:
        """Compute hillshade (shaded relief) from DEM."""
        if self._dem_data is None:
            if not self.load():
                return TerrainResult("hillshade", None, {}, {}, False, "Failed to load DEM")
        
        if not SCIPY_AVAILABLE:
            return TerrainResult("hillshade", None, {}, {}, False, "SciPy not available")
        
        try:
            z = self._dem_data.filled(np.nan) if np.ma.is_masked(self._dem_data) else self._dem_data
            cell_size_x = abs(self._info.resolution[0]) * 111000
            cell_size_y = abs(self._info.resolution[1]) * 111000
            
            dzdx = (np.roll(z, -1, axis=1) - np.roll(z, 1, axis=1)) / (2 * cell_size_x)
            dzdy = (np.roll(z, -1, axis=0) - np.roll(z, 1, axis=0)) / (2 * cell_size_y)
            
            # Sun angles in radians
            azimuth_rad = np.radians(azimuth)
            altitude_rad = np.radians(altitude)
            
            # Hillshade formula
            # Shade = cos(zenith) * cos(slope) + sin(zenith) * sin(slope) * cos(azimuth - aspect)
            zenith_rad = np.pi/2 - altitude_rad
            slope = np.arctan(np.sqrt(dzdx**2 + dzdy**2))
            aspect = np.arctan2(
                np.roll(z, -1, axis=1) - np.roll(z, 1, axis=1),
                -np.roll(z, -1, axis=0) + np.roll(z, 1, axis=0)
            )
            
            shade = (np.sin(altitude_rad) * np.cos(slope) + 
                     np.cos(altitude_rad) * np.sin(slope) * 
                     np.cos(azimuth_rad - aspect))
            
            # Normalize to 0-255
            hillshade = np.clip((shade + 1) * 127.5, 0, 255).astype(np.uint8)
            
            if np.ma.is_masked(self._dem_data):
                hillshade = np.ma.masked_where(np.ma.getmaskarray(self._dem_data), hillshade)
            
            valid_data = hillshade.flatten()
            valid_data = valid_data[~np.isnan(valid_data)] if hasattr(valid_data, '__iter__') else []
            
            stats = {
                "min": int(np.min(valid_data)) if len(valid_data) > 0 else 0,
                "max": int(np.max(valid_data)) if len(valid_data) > 0 else 255,
                "mean": float(np.mean(valid_data)) if len(valid_data) > 0 else 128,
            }
            
            return TerrainResult(
                analysis_type="hillshade",
                data=hillshade,
                metadata={"azimuth": azimuth, "altitude": altitude, "unit": "0-255"},
                statistics=stats,
                success=True,
            )
        except Exception as e:
            return TerrainResult("hillshade", None, {}, {}, False, str(e))
    
    def compute_roughness(self, window_size: int = 3) -> TerrainResult:
        """Compute surface roughness (standard deviation of elevation in window)."""
        if self._dem_data is None:
            if not self.load():
                return TerrainResult("roughness", None, {}, {}, False, "Failed to load DEM")
        
        if not SCIPY_AVAILABLE:
            return TerrainResult("roughness", None, {}, {}, False, "SciPy not available")
        
        try:
            z = self._dem_data.filled(np.nan) if np.ma.is_masked(self._dem_data) else self._dem_data
            
            # Local standard deviation using uniform filter
            mean = ndimage.uniform_filter(z, size=window_size, mode='reflect')
            sq_mean = ndimage.uniform_filter(z**2, size=window_size, mode='reflect')
            variance = sq_mean - mean**2
            roughness = np.sqrt(np.maximum(variance, 0))
            
            if np.ma.is_masked(self._dem_data):
                roughness = np.ma.masked_where(np.ma.getmaskarray(self._dem_data), roughness)
            
            valid_data = roughness[~np.ma.getmaskarray(roughness)] if np.ma.is_masked(roughness) else roughness.flatten()
            valid_data = valid_data[~np.isnan(valid_data)]
            
            stats = {
                "min": float(np.min(valid_data)) if len(valid_data) > 0 else 0,
                "max": float(np.max(valid_data)) if len(valid_data) > 0 else 0,
                "mean": float(np.mean(valid_data)) if len(valid_data) > 0 else 0,
            }
            
            return TerrainResult(
                analysis_type="roughness",
                data=roughness,
                metadata={"window_size": window_size, "unit": "meters"},
                statistics=stats,
                success=True,
            )
        except Exception as e:
            return TerrainResult("roughness", None, {}, {}, False, str(e))
    
    def compute_curvature(self) -> TerrainResult:
        """Compute profile and plan curvature."""
        if self._dem_data is None:
            if not self.load():
                return TerrainResult("curvature", None, {}, {}, False, "Failed to load DEM")
        
        if not SCIPY_AVAILABLE:
            return TerrainResult("curvature", None, {}, {}, False, "SciPy not available")
        
        try:
            z = self._dem_data.filled(np.nan) if np.ma.is_masked(self._dem_data) else self._dem_data
            cell_size = abs(self._info.resolution[0]) * 111000  # assume square
            
            # Second derivatives
            d2z_dx2 = (np.roll(z, -1, axis=1) - 2*z + np.roll(z, 1, axis=1)) / (cell_size**2)
            d2z_dy2 = (np.roll(z, -1, axis=0) - 2*z + np.roll(z, 1, axis=0)) / (cell_size**2)
            d2z_dxdy = (np.roll(np.roll(z, -1, axis=1), -1, axis=0) 
                       - np.roll(np.roll(z, -1, axis=1), 1, axis=0)
                       - np.roll(np.roll(z, 1, axis=1), -1, axis=0)
                       + np.roll(np.roll(z, 1, axis=1), 1, axis=0)) / (4 * cell_size**2)
            
            dzdx = (np.roll(z, -1, axis=1) - np.roll(z, 1, axis=1)) / (2 * cell_size)
            dzdy = (np.roll(z, -1, axis=0) - np.roll(z, 1, axis=0)) / (2 * cell_size)
            
            p = dzdx
            q = dzdy
            
            # Profile curvature (along slope direction)
            profile = -(p**2 * d2z_dx2 + 2*p*q*d2z_dxdy + q**2 * d2z_dy2) / (p**2 + q**2 + 1e-10)
            # Plan curvature (perpendicular to slope)
            plan = -(q**2 * d2z_dx2 - 2*p*q*d2z_dxdy + p**2 * d2z_dy2) / (p**2 + q**2 + 1e-10)
            
            # Flat areas have undefined curvature
            slope_sq = p**2 + q**2
            profile = np.ma.masked_where(slope_sq < 1e-10, profile)
            plan = np.ma.masked_where(slope_sq < 1e-10, plan)
            
            stats = {
                "profile_min": float(np.min(profile[~profile.mask])) if np.any(~profile.mask) else 0,
                "profile_max": float(np.max(profile[~profile.mask])) if np.any(~profile.mask) else 0,
                "plan_min": float(np.min(plan[~plan.mask])) if np.any(~plan.mask) else 0,
                "plan_max": float(np.max(plan[~plan.mask])) if np.any(~plan.mask) else 0,
            }
            
            return TerrainResult(
                analysis_type="curvature",
                data={"profile": profile, "plan": plan},
                metadata={"unit": "1/meters"},
                statistics=stats,
                success=True,
            )
        except Exception as e:
            return TerrainResult("curvature", None, {}, {}, False, str(e))
    
    def compute_all(self) -> Dict[str, TerrainResult]:
        """Compute all standard terrain analyses."""
        return {
            "slope": self.compute_slope(),
            "aspect": self.compute_aspect(),
            "hillshade": self.compute_hillshade(),
            "roughness": self.compute_roughness(),
            "curvature": self.compute_curvature(),
        }


def analyze_dem_file(dem_path: str) -> Dict[str, Any]:
    """Convenience function to run all analyses on a DEM file."""
    analyzer = TerrainAnalyzer(dem_path)
    if not analyzer.load():
        return {"error": "Failed to load DEM"}
    return {k: v.__dict__ for k, v in analyzer.compute_all().items()}
