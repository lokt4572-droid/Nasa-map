"""Dataset models for MARS EXPLORER."""
from django.contrib.gis.db import models
from django.conf import settings


class DatasetSource(models.TextChoices):
    NASA_TREK = "nasa_trek", "NASA Mars Trek"
    MOLA = "mola", "MOLA (Mars Orbiter Laser Altimeter)"
    HRSC = "hrsc", "HRSC (High Resolution Stereo Camera)"
    HIRISE = "hirise", "HiRISE (High Resolution Imaging Science Experiment)"
    CTX = "ctx", "CTX (Context Camera)"
    THEMIS = "themis", "THEMIS (Thermal Emission Imaging System)"
    CRISM = "crism", "CRISM (Compact Reconnaissance Imaging Spectrometer)"
    SHARAD = "sharad", "SHARAD (Shallow Radar)"
    CUSTOM = "custom", "Custom Upload"


class DatasetType(models.TextChoices):
    DEM = "dem", "Digital Elevation Model"
    ORTHOIMAGE = "orthoimage", "Orthorectified Image"
    SLOPE = "slope", "Slope Map"
    ROUGHNESS = "roughness", "Surface Roughness"
    THERMAL = "thermal", "Thermal Inertia"
    MINERAL = "mineral", "Mineral Map"
    RADAR = "radar", "Radar Data"
    VECTOR = "vector", "Vector Features"


class Dataset(models.Model):
    """Scientific dataset for Mars exploration."""
    name = models.CharField(max_length=200)
    source = models.CharField(max_length=20, choices=DatasetSource.choices)
    dataset_type = models.CharField(max_length=20, choices=DatasetType.choices)
    identifier = models.CharField(max_length=200, help_text="External identifier (e.g., NASA Trek layer ID)")
    description = models.TextField(blank=True)
    coverage = models.PolygonField(srid=4326, null=True, blank=True, help_text="Geographic coverage")
    resolution_meters = models.FloatField(null=True, blank=True, help_text="Resolution in meters per pixel")
    crs = models.CharField(max_length=50, default="EPSG:4326", help_text="Coordinate Reference System")
    file_path = models.CharField(max_length=500, blank=True, help_text="Local file path or URL")
    file_size = models.PositiveBigIntegerField(null=True, blank=True, help_text="Size in bytes")
    bands = models.PositiveIntegerField(default=1)
    bit_depth = models.PositiveIntegerField(default=8)
    no_data_value = models.FloatField(null=True, blank=True)
    min_value = models.FloatField(null=True, blank=True)
    max_value = models.FloatField(null=True, blank=True)
    acquisition_date = models.DateField(null=True, blank=True)
    processing_level = models.CharField(max_length=50, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    is_public = models.BooleanField(default=True)
    is_processed = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="uploaded_datasets")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Dataset"
        verbose_name_plural = "Datasets"

    def __str__(self):
        return f"{self.name} ({self.get_dataset_type_display()})"


class DatasetLayer(models.Model):
    """Pre-configured map layer from dataset."""
    name = models.CharField(max_length=200)
    dataset = models.ForeignKey(Dataset, on_delete=models.CASCADE, related_name="layers")
    layer_type = models.CharField(max_length=50, help_text="e.g., wmts, wms, xyz, geojson")
    url_template = models.CharField(max_length=500, blank=True)
    wmts_layer_id = models.CharField(max_length=200, blank=True)
    wmts_matrix_set = models.CharField(max_length=100, blank=True)
    wmts_style = models.CharField(max_length=100, blank=True)
    wmts_format = models.CharField(max_length=50, default="image/png")
    min_zoom = models.PositiveIntegerField(default=0)
    max_zoom = models.PositiveIntegerField(default=18)
    attribution = models.CharField(max_length=500, blank=True)
    opacity = models.FloatField(default=1.0)
    is_base_layer = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    z_index = models.PositiveIntegerField(default=0)
    color_ramp = models.JSONField(default=dict, blank=True, help_text="For DEM visualization")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["z_index", "name"]
        verbose_name = "Dataset Layer"
        verbose_name_plural = "Dataset Layers"

    def __str__(self):
        return self.name
