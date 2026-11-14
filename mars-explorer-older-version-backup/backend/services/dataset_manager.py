"""
Dataset manager for MARS EXPLORER.

Handles registration, discovery, and management of scientific datasets
including NASA Mars Trek WMTS layers and local DEM files.
"""
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import hashlib

from django.conf import settings
from apps.datasets.models import Dataset, DatasetLayer

from .mars_coordinates import MARS_LAYERS, MARS_TREK_BASE_URL


@dataclass
class LayerConfig:
    """Configuration for a map layer."""
    name: str
    layer_type: str  # wmts, xyz, geojson, etc.
    source: str
    identifier: str
    url_template: str = ""
    wmts_layer_id: str = ""
    wmts_matrix_set: str = "Mars_Equirectangular"
    wmts_style: str = "default"
    wmts_format: str = "image/png"
    min_zoom: int = 0
    max_zoom: int = 18
    attribution: str = ""
    opacity: float = 1.0
    is_base_layer: bool = False
    is_visible: bool = True
    z_index: int = 0
    color_ramp: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DatasetManager:
    """Manage scientific datasets and map layers."""
    
    def __init__(self):
        self.data_dir = Path(getattr(settings, 'MARS_DATA_DIR', 
            Path(settings.BASE_DIR).parent / "data" / "mars"))
        self.raw_dir = self.data_dir / "raw"
        self.processed_dir = self.data_dir / "processed"
        self.metadata_dir = self.data_dir / "metadata"
        
        # Ensure directories exist
        for d in [self.raw_dir, self.processed_dir, self.metadata_dir]:
            d.mkdir(parents=True, exist_ok=True)
    
    # NASA Mars Trek layers
    def get_nasa_trek_layers(self) -> List[Dict[str, Any]]:
        """Get all configured NASA Mars Trek layers."""
        layers = []
        for key, config in MARS_LAYERS.items():
            layer = {
                "key": key,
                "name": config["name"],
                "description": config["description"],
                "type": config["type"],
                "identifier": config["id"],
                "resolution_m": config["resolution_m"],
                "coverage": config["coverage"],
                "attribution": config["attribution"],
                "wmts_url": f"{MARS_TREK_BASE_URL}/{{TileMatrix}}/{{TileCol}}/{{TileRow}}.png",
                "wmts_layer_id": config["id"],
                "wmts_style": config["wmts_style"],
                "wmts_format": config["wmts_format"],
            }
            layers.append(layer)
        return layers
    
    def get_base_layers(self) -> List[Dict[str, Any]]:
        """Get layers suitable as base map layers."""
        return [l for l in self.get_nasa_trek_layers() if l["type"] in ("hillshade", "orthoimage")]
    
    def get_overlay_layers(self) -> List[Dict[str, Any]]:
        """Get layers suitable as overlays."""
        return [l for l in self.get_nasa_trek_layers() if l["type"] not in ("hillshade", "orthoimage")]
    
    def register_nasa_layers_in_db(self) -> List[Dataset]:
        """Register NASA Mars Trek layers in the database."""
        created = []
        for key, config in MARS_LAYERS.items():
            # Create or get dataset
            dataset, created = Dataset.objects.get_or_create(
                identifier=config["id"],
                defaults={
                    "name": config["name"],
                    "source": "nasa_trek",
                    "dataset_type": "orthoimage" if config["type"] == "orthoimage" else "dem",
                    "description": config["description"],
                    "resolution_meters": config["resolution_m"],
                    "crs": "EPSG:4326",
                    "attribution": config["attribution"],
                    "is_public": True,
                    "is_processed": True,
                }
            )
            
            if created:
                created.append(dataset)
                
                # Add coverage if available
                if isinstance(config.get("coverage"), dict):
                    from django.contrib.gis.geos import Polygon
                    cov = config["coverage"]
                    polygon = Polygon.from_bbox((
                        cov["west"], cov["south"], cov["east"], cov["north"]
                    ))
                    dataset.coverage = polygon
                    dataset.save(update_fields=["coverage"])
            
            # Create layer
            layer, layer_created = DatasetLayer.objects.get_or_create(
                dataset=dataset,
                name=config["name"],
                defaults={
                    "layer_type": "wmts",
                    "wmts_layer_id": config["id"],
                    "wmts_matrix_set": "Mars_Equirectangular",
                    "wmts_style": config["wmts_style"],
                    "wmts_format": config["wmts_format"],
                    "attribution": config["attribution"],
                    "opacity": 1.0 if config["type"] == "hillshade" else 0.8,
                    "is_base_layer": config["type"] == "hillshade",
                    "is_visible": True,
                    "z_index": 10 if config["type"] == "hillshade" else 20,
                }
            )
        
        return created
    
    # Local file management
    def scan_local_files(self, pattern: str = "*.tif") -> List[Dict[str, Any]]:
        """Scan for local DEM files and extract metadata."""
        from .dem_reader import DEMReader, find_dem_files
        
        files = find_dem_files(self.raw_dir, pattern)
        results = []
        
        for file_path in files:
            try:
                reader = DEMReader(file_path)
                if reader.open():
                    info = reader.get_info()
                    reader.close()
                    
                    # Generate hash for deduplication
                    with open(file_path, "rb") as f:
                        file_hash = hashlib.sha256(f.read()).hexdigest()[:16]
                    
                    results.append({
                        "path": str(file_path.relative_to(self.raw_dir)),
                        "absolute_path": str(file_path),
                        "size": file_path.stat().st_size,
                        "hash": file_hash,
                        "metadata": {
                            "width": info.width,
                            "height": info.height,
                            "crs": info.crs,
                            "bounds": info.bounds,
                            "resolution": info.resolution,
                            "nodata": info.nodata,
                            "dtype": info.dtype,
                            "band_count": info.band_count,
                        }
                    })
            except Exception as e:
                results.append({
                    "path": str(file_path.relative_to(self.raw_dir)),
                    "error": str(e),
                })
        
        return results
    
    def register_local_file(self, relative_path: str, metadata: Dict[str, Any] = None) -> Dataset:
        """Register a local DEM file as a dataset."""
        absolute_path = self.raw_dir / relative_path
        if not absolute_path.exists():
            raise FileNotFoundError(f"File not found: {absolute_path}")
        
        # Extract metadata if not provided
        if metadata is None:
            reader = DEMReader(absolute_path)
            if reader.open():
                info = reader.get_info()
                reader.close()
                meta = {
                    "width": info.width,
                    "height": info.height,
                    "crs": info.crs,
                    "bounds": info.bounds,
                    "resolution_meters": abs(info.resolution[0]) * 111000,
                    "nodata": info.nodata,
                    "dtype": info.dtype,
                    "band_count": info.band_count,
                }
            else:
                meta = {}
        else:
            meta = metadata
        
        # Create dataset record
        dataset = Dataset.objects.create(
            name=absolute_path.stem,
            source="custom",
            dataset_type="dem",
            identifier=f"local_{absolute_path.stem}",
            description=f"Local DEM file: {relative_path}",
            resolution_meters=meta.get("resolution_meters"),
            crs=meta.get("crs", "EPSG:4326"),
            file_path=str(absolute_path),
            file_size=absolute_path.stat().st_size,
            bands=meta.get("band_count", 1),
            bit_depth=8 if "8" in meta.get("dtype", "") else 16,
            nodata_value=meta.get("nodata"),
            min_value=meta.get("statistics", {}).get("min"),
            max_value=meta.get("statistics", {}).get("max"),
            metadata=meta,
            is_public=True,
            is_processed=False,
        )
        
        return dataset
    
    def get_dataset_layers_for_map(self) -> List[Dict[str, Any]]:
        """Get all layers formatted for frontend map consumption."""
        layers = []
        
        # NASA Trek layers (always available)
        for layer in self.get_nasa_trek_layers():
            layers.append({
                "id": layer["key"],
                "name": layer["name"],
                "type": "wmts",
                "url": layer["wmts_url"],
                "layer_id": layer["wmts_layer_id"],
                "matrix_set": layer["wmts_matrix_set"],
                "style": layer["wmts_style"],
                "format": layer["wmts_format"],
                "attribution": layer["attribution"],
                "opacity": 1.0 if layer["type"] == "hillshade" else 0.8,
                "visible": layer["type"] == "hillshade",
                "z_index": 10 if layer["type"] == "hillshade" else 20,
                "min_zoom": 0,
                "max_zoom": 18,
            })
        
        # Database-registered layers
        db_layers = DatasetLayer.objects.select_related("dataset").filter(is_visible=True)
        for layer in db_layers:
            layers.append({
                "id": f"db_{layer.id}",
                "name": layer.name,
                "type": layer.layer_type,
                "dataset_id": layer.dataset_id,
                "url_template": layer.url_template,
                "wmts_layer_id": layer.wmts_layer_id,
                "wmts_matrix_set": layer.wmts_matrix_set,
                "wmts_style": layer.wmts_style,
                "wmts_format": layer.wmts_format,
                "attribution": layer.attribution,
                "opacity": layer.opacity,
                "visible": layer.is_visible,
                "z_index": layer.z_index,
                "min_zoom": layer.min_zoom,
                "max_zoom": layer.max_zoom,
                "color_ramp": layer.color_ramp,
            })
        
        return layers


# Singleton instance
_dataset_manager = None

def get_dataset_manager() -> DatasetManager:
    """Get singleton dataset manager instance."""
    global _dataset_manager
    if _dataset_manager is None:
        _dataset_manager = DatasetManager()
    return _dataset_manager
