"""
DEM (Digital Elevation Model) reader with graceful GDAL fallback.

Provides elevation data access from GeoTIFF and other raster formats.
If GDAL/rasterio is not available, provides mock/stub implementations
so the application can still run for development.
"""
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
import numpy as np

# Try to import GDAL/rasterio
try:
    import rasterio
    from rasterio.windows import Window
    from rasterio.transform import rowcol, xy
    from rasterio.crs import CRS
    from rasterio.warp import transform_bounds
    RASTERIO_AVAILABLE = True
except ImportError:
    RASTERIO_AVAILABLE = False
    rasterio = None

try:
    from osgeo import gdal, osr
    GDAL_AVAILABLE = True
except ImportError:
    GDAL_AVAILABLE = False
    gdal = None


@dataclass
class DEMInfo:
    """Metadata about a DEM file."""
    path: str
    width: int
    height: int
    crs: str
    bounds: Tuple[float, float, float, float]  # left, bottom, right, top
    resolution: Tuple[float, float]  # x_res, y_res in CRS units
    nodata: Optional[float]
    dtype: str
    band_count: int
    statistics: Optional[Dict[str, float]] = None


@dataclass
class ElevationSample:
    """Single elevation sample point."""
    longitude: float
    latitude: float
    elevation: Optional[float]
    valid: bool


class DEMReader:
    """Read elevation data from DEM files."""
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self._dataset = None
        self._info = None
    
    def open(self) -> bool:
        """Open the DEM file."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"DEM file not found: {self.file_path}")
        
        if RASTERIO_AVAILABLE:
            try:
                self._dataset = rasterio.open(self.file_path)
                return True
            except Exception as e:
                print(f"Rasterio failed to open {self.file_path}: {e}")
        
        if GDAL_AVAILABLE:
            try:
                self._dataset = gdal.Open(str(self.file_path), gdal.GA_ReadOnly)
                return self._dataset is not None
            except Exception as e:
                print(f"GDAL failed to open {self.file_path}: {e}")
        
        # Fallback: create mock dataset for development
        if not self._dataset:
            print(f"Warning: No GDAL/rasterio available. Using mock DEM for {self.file_path}")
            self._dataset = "mock"
        
        return self._dataset is not None
    
    def close(self):
        """Close the dataset."""
        if self._dataset and hasattr(self._dataset, 'close'):
            self._dataset.close()
        elif GDAL_AVAILABLE and self._dataset:
            self._dataset = None
    
    def get_info(self) -> DEMInfo:
        """Get DEM metadata."""
        if self._info:
            return self._info
        
        if not self._dataset:
            self.open()
        
        if self._dataset == "mock":
            # Return mock info for development
            self._info = DEMInfo(
                path=str(self.file_path),
                width=1000,
                height=1000,
                crs="EPSG:4326",
                bounds=(-180, -90, 180, 90),
                resolution=(0.01, 0.01),
                nodata=-9999,
                dtype="float32",
                band_count=1,
                statistics={"min": -8000, "max": 21000, "mean": 1000, "std": 5000}
            )
            return self._info
        
        if RASTERIO_AVAILABLE and hasattr(self._dataset, 'crs'):
            # Rasterio path
            bounds = self._dataset.bounds
            transform = self._dataset.transform
            self._info = DEMInfo(
                path=str(self.file_path),
                width=self._dataset.width,
                height=self._dataset.height,
                crs=str(self._dataset.crs) if self._dataset.crs else "EPSG:4326",
                bounds=(bounds.left, bounds.bottom, bounds.right, bounds.top),
                resolution=(transform.a, abs(transform.e)),
                nodata=self._dataset.nodata,
                dtype=str(self._dataset.dtypes[0]),
                band_count=self._dataset.count,
            )
        elif GDAL_AVAILABLE:
            # GDAL path
            gt = self._dataset.GetGeoTransform()
            proj = self._dataset.GetProjection()
            srs = osr.SpatialReference()
            srs.ImportFromWkt(proj) if proj else srs.ImportFromEPSG(4326)
            
            self._info = DEMInfo(
                path=str(self.file_path),
                width=self._dataset.RasterXSize,
                height=self._dataset.RasterYSize,
                crs=f"EPSG:{srs.GetAuthorityCode(None)}" if srs.GetAuthorityCode(None) else "EPSG:4326",
                bounds=(
                    gt[0],
                    gt[3] + gt[5] * self._dataset.RasterYSize,
                    gt[0] + gt[1] * self._dataset.RasterXSize,
                    gt[3]
                ),
                resolution=(abs(gt[1]), abs(gt[5])),
                nodata=self._dataset.GetRasterBand(1).GetNoDataValue(),
                dtype=gdal.GetDataTypeName(self._dataset.GetRasterBand(1).DataType),
                band_count=self._dataset.RasterCount,
            )
        
        return self._info
    
    def sample_at_coords(self, coords: List[Tuple[float, float]]) -> List[ElevationSample]:
        """Sample elevation at multiple (longitude, latitude) coordinates."""
        if not self._dataset:
            self.open()
        
        results = []
        
        if self._dataset == "mock":
            # Return mock elevation data
            for lon, lat in coords:
                # Simple synthetic Mars elevation
                elevation = self._mock_mars_elevation(lon, lat)
                results.append(ElevationSample(lon, lat, elevation, True))
            return results
        
        if RASTERIO_AVAILABLE and hasattr(self._dataset, 'sample'):
            # Rasterio path
            try:
                rows, cols = [], []
                for lon, lat in coords:
                    r, c = self._dataset.index(lon, lat)
                    rows.append(r)
                    cols.append(c)
                
                # Read all samples at once
                values = self._dataset.read(1, window=Window(0, 0, self._dataset.width, self._dataset.height))
                nodata = self._dataset.nodata
                
                for i, (r, c) in enumerate(zip(rows, cols)):
                    if 0 <= r < self._dataset.height and 0 <= c < self._dataset.width:
                        val = values[r, c]
                        valid = nodata is None or val != nodata
                        results.append(ElevationSample(
                            coords[i][0], coords[i][1], 
                            float(val) if valid else None, valid
                        ))
                    else:
                        results.append(ElevationSample(coords[i][0], coords[i][1], None, False))
                        
        elif GDAL_AVAILABLE:
            # GDAL path
            band = self._dataset.GetRasterBand(1)
            gt = self._dataset.GetGeoTransform()
            
            for lon, lat in coords:
                # Convert to pixel coordinates
                px = int((lon - gt[0]) / gt[1])
                py = int((lat - gt[3]) / gt[5])
                
                if 0 <= px < self._dataset.RasterXSize and 0 <= py < self._dataset.RasterYSize:
                    val = band.ReadAsArray(px, py, 1, 1)[0, 0]
                    nodata = band.GetNoDataValue()
                    valid = nodata is None or val != nodata
                    results.append(ElevationSample(lon, lat, float(val) if valid else None, valid))
                else:
                    results.append(ElevationSample(lon, lat, None, False))
        
        return results
    
    def _mock_mars_elevation(self, lon: float, lat: float) -> float:
        """Generate synthetic Mars elevation for development."""
        # Very simplified synthetic Mars topography
        # Based on rough planetary features
        elevation = 0.0
        
        # Tharsis bulge (roughly -100 to 100 lon, -30 to 30 lat)
        if -130 <= lon <= -80 and -30 <= lat <= 30:
            dist_from_center = ((lon + 105) ** 2 + lat ** 2) ** 0.5
            elevation += max(0, 10000 * (1 - dist_from_center / 30))
        
        # Hellas Basin (roughly 60-80 lon, -50 to -30 lat)
        if 60 <= lon <= 90 and -55 <= lat <= -25:
            dist_from_center = ((lon - 75) ** 2 + (lat + 42) ** 2) ** 0.5
            elevation -= max(0, 7000 * (1 - dist_from_center / 15))
        
        # Valles Marineris (roughly 30-100 lon, -15 to 0 lat)
        if 30 <= lon <= 100 and -15 <= lat <= 5:
            dist_from_center = ((lon - 65) ** 2 + (lat + 7) ** 2) ** 0.5
            if dist_from_center < 5:
                elevation -= 5000
        
        # Add some noise
        import random
        random.seed(int((lon + 180) * 1000 + (lat + 90) * 100))
        elevation += random.uniform(-500, 500)
        
        return max(-10000, min(25000, elevation))
    
    def get_elevation_profile(self, coords: List[Tuple[float, float]], 
                              distances: Optional[List[float]] = None) -> Dict[str, Any]:
        """Get elevation profile along a path."""
        samples = self.sample_at_coords(coords)
        elevations = [s.elevation if s.valid else None for s in samples]
        
        if distances is None:
            # Calculate cumulative distances
            distances = [0.0]
            for i in range(1, len(coords)):
                from .mars_coordinates import MarsCoordinate
                c1 = MarsCoordinate(coords[i-1][0], coords[i-1][1])
                c2 = MarsCoordinate(coords[i][0], coords[i][1])
                distances.append(distances[-1] + c1.distance_to(c2))
        
        valid_elevations = [e for e in elevations if e is not None]
        
        return {
            "coordinates": coords,
            "elevations": elevations,
            "distances_km": distances,
            "min_elevation": min(valid_elevations) if valid_elevations else None,
            "max_elevation": max(valid_elevations) if valid_elevations else None,
            "total_gain": self._calculate_gain(elevations),
            "total_loss": self._calculate_loss(elevations),
            "sample_count": len(samples),
        }
    
    def _calculate_gain(self, elevations: List[Optional[float]]) -> float:
        gain = 0.0
        prev = None
        for e in elevations:
            if e is not None and prev is not None and e > prev:
                gain += e - prev
            if e is not None:
                prev = e
        return gain
    
    def _calculate_loss(self, elevations: List[Optional[float]]) -> float:
        loss = 0.0
        prev = None
        for e in elevations:
            if e is not None and prev is not None and e < prev:
                loss += prev - e
            if e is not None:
                prev = e
        return loss


def find_dem_files(data_dir: Path, pattern: str = "*.tif") -> List[Path]:
    """Find all DEM files in a directory."""
    return list(data_dir.rglob(pattern))


def create_vrt_from_files(file_paths: List[Path], output_path: Path) -> bool:
    """Create a Virtual Raster (VRT) from multiple DEM files."""
    if not GDAL_AVAILABLE:
        print("GDAL not available, cannot create VRT")
        return False
    
    try:
        vrt = gdal.BuildVRT(str(output_path), [str(p) for p in file_paths])
        vrt = None  # Close
        return True
    except Exception as e:
        print(f"Failed to create VRT: {e}")
        return False
